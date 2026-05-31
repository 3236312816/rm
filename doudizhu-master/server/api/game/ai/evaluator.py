"""
手牌强度评估模块 - HandEvaluator
为手牌打 0~100+ 的综合分，用于叫地主决策和出牌选择。

评估维度：
- 火箭/炸弹数量
- 高级控制牌（王、2、A）
- 手牌结构（顺子、三张、对子）
- 孤立单牌扣分
"""

from typing import Dict, List, Tuple
from collections import Counter


class HandEvaluator:
    """
    手牌强度评估器。

    所有权重均为类常量，便于调参。
    """

    # === 权重常量（可调） ===
    W_ROCKET = 30.0         # 火箭
    W_BOMB = 12.0            # 每个炸弹
    W_BIG_BOMB = 5.0         # 高位炸弹（J~2）额外加分
    W_KING_SMALL = 6.0       # 小王
    W_KING_BIG = 8.0         # 大王
    W_TWO = 3.0              # 每张 2
    W_ACE = 1.5              # 每张 A
    W_TRIO = 1.0             # 每个三张
    W_PAIR_HIGH = 0.8        # 每个高位对子（J~A）
    W_PAIR_TWO = 1.5         # 对2额外加成
    W_SEQ_PER_CARD = 1.5     # 顺子每张牌
    W_BOMB_SINGLE_PER = 0.5  # 四带二/对中的踢脚每张
    PENALTY_SINGLE = -1.0    # 每个孤立单牌扣分（原-2.0太严，导致AI几乎从不叫地主）
    PENALTY_ZERO_PAIR = -1.0  # 无对子扣分（缺乏弹性）

    def evaluate(self, hand_cards: List[str]) -> Tuple[float, Dict]:
        """
        综合评估手牌强度。

        Args:
            hand_cards: 牌面值字符列表，如 ['3','3','K','2','w']

        Returns:
            (score, breakdown) 元组，score 为浮点数（0~100+），
            breakdown 为各维度得分明细字典。
        """
        if not hand_cards:
            return 0.0, {'total': 0.0}

        counter = Counter(hand_cards)
        score = 0.0
        breakdown: Dict[str, float] = {}

        # 1. 火箭检测
        has_w = 'w' in counter
        has_W = 'W' in counter
        rocket_score = self.W_ROCKET if (has_w and has_W) else 0.0
        score += rocket_score
        breakdown['rocket'] = rocket_score

        # 2. 炸弹检测
        bombs = [r for r, cnt in counter.items() if cnt == 4]
        bomb_score = len(bombs) * self.W_BOMB
        for b in bombs:
            if b in 'JQKA2':
                bomb_score += self.W_BIG_BOMB
        score += bomb_score
        breakdown['bombs'] = bomb_score

        # 3. 高级牌（王、2、A）
        premium = 0.0
        premium += counter.get('w', 0) * self.W_KING_SMALL
        premium += counter.get('W', 0) * self.W_KING_BIG
        premium += counter.get('2', 0) * self.W_TWO
        premium += counter.get('A', 0) * self.W_ACE
        score += premium
        breakdown['premium'] = premium

        # 4. 结构分
        struct = 0.0
        # 三张
        trios = [r for r, cnt in counter.items() if cnt == 3]
        struct += len(trios) * self.W_TRIO
        # 高位对子
        for r, cnt in counter.items():
            if cnt == 2:
                if r in 'JQKA':
                    struct += self.W_PAIR_HIGH
                elif r == '2':
                    struct += self.W_PAIR_TWO
        score += struct
        breakdown['structure'] = struct

        # 5. 顺子
        seq_len = self._longest_single_seq(hand_cards)
        seq_score = seq_len * self.W_SEQ_PER_CARD if seq_len >= 5 else 0.0
        score += seq_score
        breakdown['sequence'] = seq_score

        # 6. 孤立单牌扣分
        single_count = sum(1 for r, cnt in counter.items() if cnt == 1)
        single_penalty = single_count * self.PENALTY_SINGLE
        score += single_penalty
        breakdown['singles_penalty'] = single_penalty

        # 7. 无对子扣分（灵活性差）
        pair_count = sum(1 for r, cnt in counter.items() if cnt >= 2)
        if pair_count <= 1:
            no_pair_penalty = self.PENALTY_ZERO_PAIR
            score += no_pair_penalty
            breakdown['no_pair_penalty'] = no_pair_penalty
        else:
            breakdown['no_pair_penalty'] = 0.0

        # 8. 总可控性评分
        # 手牌长度补偿——牌越少越好（接近胜利）
        hand_size = len(hand_cards)
        if hand_size <= 6:
            size_bonus = (6 - hand_size) * 3.0  # 剩 1 张加 15 分
            score += size_bonus
            breakdown['size_bonus'] = size_bonus
        else:
            breakdown['size_bonus'] = 0.0

        breakdown['total'] = round(score, 1)
        return score, breakdown

    def evaluate_as_landlord(self, hand_cards: List[str]) -> float:
        """作为地主的手牌评分：更看重炸弹和高控制牌"""
        score, bd = self.evaluate(hand_cards)
        score += bd.get('bombs', 0) * 0.3
        score += bd.get('premium', 0) * 0.2
        return round(score, 1)

    def evaluate_as_farmer(self, hand_cards: List[str]) -> float:
        """作为农民的手牌评分：更看重结构和配合"""
        score, bd = self.evaluate(hand_cards)
        score += bd.get('structure', 0) * 0.3
        score += bd.get('sequence', 0) * 0.2
        return round(score, 1)

    def _longest_single_seq(self, hand_cards: List[str]) -> int:
        """查找最长单顺长度（需要至少5张才算有效顺子）"""
        ranks = set(hand_cards)
        order = '34567890JQKA'
        max_len = 0
        current = 0
        for r in order:
            if r in ranks:
                current += 1
                max_len = max(max_len, current)
            else:
                current = 0
        return max_len

    def estimate_bomb_advantages(self, hand_cards: List[str]) -> int:
        """估算手牌中炸弹的'优势'——高位炸弹数量"""
        counter = Counter(hand_cards)
        bombs = [r for r, cnt in counter.items() if cnt == 4]
        advantage = 0
        for b in bombs:
            if b in 'JQKA2':
                advantage += 1
        # 火箭也算优势
        if 'w' in counter and 'W' in counter:
            advantage += 2
        return advantage
