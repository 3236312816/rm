from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tornado.ioloop import IOLoop

from ..player import Player
from ..protocol import Protocol as Pt
from ..rule import rule

if TYPE_CHECKING:
    from ..room import Room

logger = logging.getLogger(__file__)


class RobotPlayer(Player):

    def __init__(self, uid: int, name: str, sex: int = 1, avatar: str = 0, room: Room = None, **kwargs):
        super().__init__(uid, name, sex, avatar, **kwargs)
        self.room = room

    def to_server(self, code, packet):
        IOLoop.current().add_callback(self.on_message, code, packet)

    def write_message(self, packet):
        IOLoop.current().add_callback(self._write_message, packet)

    def _write_message(self, packet):
        code = packet[0]
        if code == Pt.ERROR:
            # 服务端拒绝了出牌 → 自动过牌（防止机器人卡死）
            if self.room and self.room.turn_player == self:
                logger.warning('  -> 出牌被拒(%s), 自动过牌', packet[1].get('reason', ''))
                IOLoop.current().call_later(0.5, self.to_server, Pt.REQ_SHOT_POKER, {'pokers': []})
        elif code == Pt.RSP_DEAL_POKER:
            if self.uid == packet[1]['uid']:
                self.auto_rob()
        elif code == Pt.RSP_CALL_SCORE:
            if self.room.turn_player == self:
                landlord = packet[1]['landlord']
                if landlord == -1:
                    self.auto_rob()
                elif self.room.turn_player == self:
                    IOLoop.current().call_later(1, self.auto_shot)
        elif code == Pt.RSP_SHOT_POKER:
            if self.room.turn_player == self and self.hand_pokers:
                self.auto_shot()

    def auto_rob(self):
        """叫地主决策：优先使用 AIBrain，否则回退到旧逻辑"""
        if self.room and hasattr(self.room, 'ai_brain'):
            try:
                position = (self.seat - self.room.landlord_seat) % 3
                is_grab = self.room._first_bidder_seat != -1
                action = '叫地主' if not is_grab else '抢地主'

                # 打印手牌和分析
                from ..rule import rule
                cards = rule._to_cards(self.hand_pokers)
                score, breakdown = self.room.ai_brain.evaluator.evaluate(cards)
                effective = score
                if breakdown.get('rocket', 0) >= 30:
                    effective += self.room.ai_brain.bidding.ROCKET_BONUS
                effective -= (2 - position) * self.room.ai_brain.bidding.POSITION_PENALTY / 2

                logger.info('【AI决策】%s %s 手牌: %s', self.name, action,
                            rule.pokers_to_log_str(self.hand_pokers))
                logger.info('  -> 牌面: %s', ''.join(sorted(cards)))
                logger.info('  -> 评分: %.1f, 有效分=%.1f, position=%d',
                            score, effective, position)
                # 评分明细
                label_map = {'rocket': '火箭', 'bombs': '炸弹', 'premium': '高牌(王2A)',
                             'structure': '结构(三张/对子)', 'sequence': '顺子',
                             'singles_penalty': '孤立单牌扣分', 'no_pair_penalty': '无对子扣分',
                             'size_bonus': '手牌少加分'}
                for k, v in sorted(breakdown.items()):
                    if v != 0:
                        lbl = label_map.get(k, k)
                        logger.info('  ->   %s: %+.1f', lbl, v)

                should = self.room.ai_brain.decide_bid(self.hand_pokers, position, is_grab)
                rob = 1 if should else 0
                threshold = self.room.ai_brain.bidding.GRAB_THRESHOLD if is_grab else self.room.ai_brain.bidding.BID_THRESHOLD
                logger.info('  => 结果: %s (阈值=%.1f, 有效分=%.1f)',
                            '叫/抢' if rob else '不叫', threshold, effective)
                IOLoop.current().call_later(1.5, self.to_server, Pt.REQ_CALL_SCORE, {'rob': rob})
                return
            except Exception as e:
                logger.error('AIBrain bid error, fallback: %s', e)

        # 旧逻辑：检查特定高级牌
        pokers = [poker for poker in (54, 53, 2, 15, 28, 41) if poker in self.hand_pokers]
        rob = int(len(pokers) >= 4)
        IOLoop.current().call_later(1.5, self.to_server, Pt.REQ_CALL_SCORE, {'rob': rob})

    def auto_shot(self):
        """出牌决策：优先使用 AIBrain，否则回退到旧逻辑"""
        if self.room and hasattr(self.room, 'ai_brain'):
            try:
                from ..rule import rule
                is_landlord = (self.landlord == 1)
                last_shot = self.room.last_shot_poker
                last_shooter = self.room.last_shot_seat
                role = '地主' if is_landlord else '农民'

                # 判断领出还是跟牌
                if not last_shot or last_shooter == self.seat:
                    action = '领出'
                else:
                    is_ally = (self.room.players[last_shooter].landlord == self.landlord)
                    action = f'跟牌({"队友" if is_ally else "对手"})'

                logger.info('【AI决策】%s(%s) %s 手牌(%d张): %s',
                            self.name, role, action, len(self.hand_pokers),
                            rule.pokers_to_log_str(self.hand_pokers))

                if last_shot and last_shooter != self.seat:
                    # 跟牌场景，显示上家出的牌
                    is_ally = (self.room.players[last_shooter].landlord == self.landlord)
                    spec = rule.get_poker_spec(last_shot)
                    logger.info('  -> 上家(玩家%d)出: %s (%s)',
                                last_shooter, rule.pokers_to_log_str(last_shot), spec)

                pokers = self.room.ai_brain.decide_shot(
                    self.hand_pokers, self.seat, is_landlord, self.room
                )

                if pokers:
                    spec = rule.get_poker_spec(pokers)
                    logger.info('  => 出牌: %s (%s)', rule.pokers_to_log_str(pokers), spec)
                else:
                    logger.info('  => pass')
                IOLoop.current().call_later(2, self.to_server, Pt.REQ_SHOT_POKER, {'pokers': pokers})
                return
            except Exception as e:
                logger.error('AIBrain shot error, fallback: %s', e)

        # 旧逻辑：保留原有出牌逻辑
        self._legacy_auto_shot()

    def _check_special_combo(self, hand_cards):
        """Check if hand contains a complete zmjjkk or kskbl combo."""
        from ..rule import Rule
        if all(c in hand_cards for c in Rule.ZMJJKK_CARDS):
            logger.info('  -> Robot plays zmjjkk combo!')
            return ''.join(Rule.ZMJJKK_CARDS)
        if all(c in hand_cards for c in Rule.KSKBL_CARDS):
            logger.info('  -> Robot plays kskbl combo!')
            return ''.join(Rule.KSKBL_CARDS)
        return None

    def _legacy_auto_shot(self):
        """原始出牌逻辑（作为回退）"""
        hand_cards = rule._to_cards(self.hand_pokers)

        # 降维打击 special combo check (high priority)
        special_shot = self._check_special_combo(hand_cards)
        if special_shot:
            pokers = rule._to_pokers(self.hand_pokers, special_shot)
            IOLoop.current().call_later(2, self.to_server, Pt.REQ_SHOT_POKER, {'pokers': pokers})
            return

        if not self.room.last_shot_poker or self.room.last_shot_seat == self.seat:
            pokers = rule.find_best_shot(self.hand_pokers)
        else:
            ally = self.room.players[self.room.last_shot_seat].landlord == 0
            left_pokers = len(self.room.players[self.room.last_shot_seat].hand_pokers)
            if ally and left_pokers <= 4 and len(self.hand_pokers) - len(self.room.last_shot_poker) > 4:
                pokers = []
            else:
                pokers = rule.find_best_follow(self.hand_pokers, self.room.last_shot_poker, ally)
                if 53 in pokers and 54 in pokers and left_pokers > 10:
                    pokers = []

        IOLoop.current().call_later(2, self.to_server, Pt.REQ_SHOT_POKER, {'pokers': pokers})
