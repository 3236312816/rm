"""
AIBrain - AI 总控胶水类
将记忆、评估、推理、策略各子系统串联为单一的决策入口。
"""

import logging
from typing import List, Optional

from .memory import CardMemory
from .evaluator import HandEvaluator
from .inference import OpponentModel
from .strategy import BiddingStrategy, LeadingStrategy, FollowingStrategy, EndgameStrategy

logger = logging.getLogger(__file__)


class AIBrain:
    """
    AI 大脑。
    每个 Room 一个实例，由所有机器人共享。
    """

    def __init__(self):
        self.memory = CardMemory()
        self.evaluator = HandEvaluator()
        self.inference = OpponentModel(self.memory)
        self.bidding = BiddingStrategy(self.evaluator)
        self.leading = LeadingStrategy(self.evaluator, self.memory)
        self.following = FollowingStrategy(self.evaluator, self.memory)
        self.endgame = EndgameStrategy(self.memory)

    def reset(self):
        """开始新牌局时重置"""
        self.memory.reset()

    def decide_bid(self, hand_pokers: List[int], position_index: int, is_grab: bool = False) -> bool:
        """
        决定是否叫/抢地主。

        Args:
            hand_pokers: 手牌
            position_index: 叫地主顺序（0=先叫, 1=中间, 2=末家）
            is_grab: True=抢地主模式（更低阈值）

        Returns:
            True=叫/抢地主, False=不叫
        """
        return self.bidding.should_bid(hand_pokers, position_index, is_grab)

    def decide_shot(self, hand_pokers: List[int], my_seat: int,
                    is_landlord: bool, room) -> List[int]:
        """
        主要出牌决策入口。

        Args:
            hand_pokers: 手牌
            my_seat: 自己座位号
            is_landlord: 是否是地主
            room: Room 实例（访问状态和其他玩家）

        Returns:
            要出的牌列表，空列表 = pass
        """
        from ..rule import rule, Rule

        if not hand_pokers:
            return []

        players = room.players
        last_shot = room.last_shot_poker
        last_seat = room.last_shot_seat

        # Step 0: 降维打击 special combo — play if leading or vs opponent
        hand_cards = rule._to_cards(hand_pokers)
        is_following_ally = (last_shot and last_seat != my_seat and
                             players[last_seat].landlord == players[my_seat].landlord)
        if not is_following_ally:
            if all(c in hand_cards for c in Rule.ZMJJKK_CARDS):
                logger.info('  -> AIBrain: 降维打击 — 出 zmjjkk!')
                return rule._to_pokers(hand_pokers, Rule.ZMJJKK_CARDS)
            if all(c in hand_cards for c in Rule.KSKBL_CARDS):
                logger.info('  -> AIBrain: 降维打击 — 出 kskbl!')
                return rule._to_pokers(hand_pokers, Rule.KSKBL_CARDS)

        # Step 1: 终局策略覆盖检查
        endgame_override = self.endgame.check_endgame(
            hand_pokers, my_seat, players, last_shot, last_seat
        )
        if endgame_override is not None:
            logger.info('  -> AIBrain: 终局覆盖出牌: %s', rule.pokers_to_log_str(endgame_override) if endgame_override else 'pass')
            return endgame_override

        # Step 2: 判断是领出还是跟牌
        if not last_shot or last_seat == my_seat:
            # 领出
            logger.info('  -> AIBrain: 领出模式 (地主=%s)', is_landlord)
            return self.leading.choose_lead(hand_pokers, is_landlord, my_seat, players)
        else:
            # 跟牌
            is_ally = (players[last_seat].landlord == players[my_seat].landlord)
            last_player_size = len(players[last_seat].hand_pokers)
            logger.info('  -> AIBrain: 跟牌模式 (队友=%s, 上家剩%d张)', is_ally, last_player_size)

            result = self.following.choose_follow(
                hand_pokers, last_shot, is_ally, is_landlord,
                last_player_size, players, my_seat
            )

            # 火箭保护：对手还有很多牌时不用火箭
            if result and 53 in result and 54 in result and last_player_size > 10:
                logger.info('  -> AIBrain: 火箭保护(对手剩%d张), 保留火箭', last_player_size)
                return []

            return result
