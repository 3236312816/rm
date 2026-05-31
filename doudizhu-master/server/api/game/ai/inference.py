"""
对手推理模块 - OpponentModel
基于公共出牌信息，推理对手可能持有的牌面。
为出牌决策提供风险评估。
"""

from typing import List, Optional

from .memory import CardMemory


class OpponentModel:
    """
    对手手牌推理模型。
    使用 CardMemory 的剩余牌信息，结合手牌大小进行概率估算。
    """

    def __init__(self, memory: CardMemory):
        self.memory = memory

    def estimate_holds_bomb(self, player_hand_size: int) -> float:
        """
        估算某个玩家手中有炸弹的概率（0.0~1.0）。

        根据该玩家手牌数占剩余未出牌张数的比例，
        以及还有几个炸弹可能存活（各面值4张全在）。
        """
        remaining = self.memory.remaining
        total_unseen = sum(remaining.values())
        if total_unseen <= 0 or player_hand_size <= 0:
            return 0.0

        # 统计还有几个面值可以形成炸弹（4张全未出）
        possible_bomb_ranks = []
        for r in '34567890JQKA2':
            if remaining.get(r, 0) == 4:
                possible_bomb_ranks.append(r)

        if not possible_bomb_ranks:
            return 0.0

        # 手牌太小不可能有炸弹（需要至少4张相同面值）
        if player_hand_size < 4:
            return 0.0

        # 概率 ≈ 1 - (该玩家手牌中没有炸弹的概率)
        # 简化：假设每个面值的4张牌随机分配到三人的概率相等
        # 该玩家拿到全部4张的概率为 (hand_size / total_unseen) 的近似
        hand_ratio = player_hand_size / total_unseen
        # 对于每个可能的炸弹面值，该玩家持有的概率 ≈ hand_ratio^3（保守估计）
        prob_has_any = 1.0
        for _ in possible_bomb_ranks:
            prob_has_any *= (1 - hand_ratio)
        prob_has_any = 1.0 - prob_has_any

        return min(prob_has_any, 1.0)

    def estimate_max_single_rank(self, player_hand_size: int) -> str:
        """
        估算对手手中最大的单牌牌面值。

        基于剩余牌分布和该玩家的手牌占比。
        返回牌面字符，如 '2', 'W', 'A' 等。
        """
        remaining = self.memory.remaining
        total_unseen = sum(remaining.values())
        if total_unseen <= 0 or player_hand_size <= 0:
            return '3'

        hand_ratio = player_hand_size / total_unseen
        order = '34567890JQKA2wW'

        # 从大到小找第一个可能持有的牌面
        for rank in reversed(order):
            expected = remaining.get(rank, 0) * hand_ratio
            if expected > 0.4:
                return rank
        return '3'

    def estimate_holds_rocket(self, player_hand_size: int) -> bool:
        """估算某玩家是否可能持有火箭（大小王）"""
        if not self.memory.rocket_remaining():
            return False
        remaining = self.memory.remaining
        total_unseen = sum(remaining.values())
        if total_unseen <= 0:
            return False

        hand_ratio = player_hand_size / total_unseen
        # 需要两张都在这家手中
        prob_w = remaining.get('w', 0) / total_unseen
        prob_w_in_hand = min(prob_w * player_hand_size * 2, 1.0)
        prob_W = remaining.get('W', 0) / total_unseen
        prob_W_in_hand = min(prob_W * player_hand_size * 2, 1.0)

        return (prob_w_in_hand * prob_W_in_hand) > 0.3

    def can_opponent_beat_rank(self, rank: str, opponents: List) -> float:
        """
        估算至少一个对手能压制某牌面的概率。
        用于评估出某张牌被压制的风险。
        """
        order = '34567890JQKA2wW'
        idx = order.index(rank)
        if idx >= len(order) - 1:
            return 0.0  # 大王无人能压制

        remaining = self.memory.remaining
        total_unseen = sum(remaining.values())
        if total_unseen <= 0:
            return 0.0

        higher_ranks = order[idx + 1:]
        unseen_above = sum(remaining.get(r, 0) for r in higher_ranks)
        if unseen_above <= 0:
            return 0.0

        opponent_total = sum(len(p.hand_pokers) for p in opponents)
        if opponent_total <= 0:
            return 0.0

        # 概率 ≈ 1 - (没有被压制)
        # 简化模型：对手手牌数 / 所有未出牌数
        ratio = opponent_total / total_unseen
        # 所有大牌都在对手手中的概率
        prob_opponent_has_any = 1.0 - (1.0 - ratio) ** unseen_above
        return min(prob_opponent_has_any, 1.0)

    def estimate_bomb_threat(self, my_seat: int, players: List) -> float:
        """
        综合炸弹威胁评估（0.0~1.0）。
        所有对手可能持有炸弹的聚合概率。
        """
        total_threat = 0.0
        for i, p in enumerate(players):
            if i == my_seat:
                continue
            if p and hasattr(p, 'hand_pokers'):
                total_threat += self.estimate_holds_bomb(len(p.hand_pokers))
        return min(total_threat, 1.0)
