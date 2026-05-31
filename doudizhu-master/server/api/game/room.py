from __future__ import annotations

import logging
import random
from functools import reduce
from operator import mul
from typing import Optional, List, Dict
from typing import TYPE_CHECKING

from tornado.ioloop import IOLoop

from .player import State
from .protocol import Protocol as Pt
from .rule import rule, Rule
from .timer import Timer
from .ai.robot import AIBrain

if TYPE_CHECKING:
    from .player import Player


class Room(object):
    robot_no = 0

    def __init__(self, room_id, level=1, allow_robot=True):
        self.room_id = room_id
        self.level = level
        self._multiple_details: Dict[str, int] = {
            'origin': 10,
            'origin_multiple': 15,
            'di': 1,
            'ming': 1,
            'bomb': 1,
            'rob': 1,
            'spring': 1,
            'landlord': 1,
            'farmer': 1,
        }

        self.players: List[Optional[Player]] = [None, None, None]
        self.pokers: List[int] = []

        self.timer = Timer(self.on_timeout)
        self.ai_brain = AIBrain()
        self.whose_turn = 0
        self.landlord_seat = 0
        self.bomb_multiple = 2

        self.last_shot_seat = 0
        self.last_shot_poker: List[int] = []
        self.shot_round: List[List[int]] = []

        self._rob_step = 0               # 叫地主轮次计数（0=无人决定）
        self._first_bidder_seat = -1     # 第一个叫地主的人的座位号

        self.allow_robot = allow_robot
        self._dimensional_strike_triggered = False

    def restart(self, rotate_landlord=True):
        for key, val in self._multiple_details.items():
            if key.startswith('origin'):
                continue
            self._multiple_details[key] = 1

        self.pokers: List[int] = []

        self.timer.stop_timing()
        self.ai_brain.reset()
        self.whose_turn = 0
        if rotate_landlord:
            self.landlord_seat = (self.landlord_seat + 1) % 3
        self.bomb_multiple = 2

        self.last_shot_seat = 0
        self.last_shot_poker = []
        self.shot_round = []
        self._rob_record = []
        self._rob_step = 0
        self._first_bidder_seat = -1
        self._dimensional_strike_triggered = False

        for player in self.players:
            if player:
                player.restart()

    @property
    def room_state(self):
        for player in self.players:
            if player and not player.is_left():
                return player.state
        return State.INIT

    def sync_data(self):
        return {
            'id': self.room_id,
            'origin': self._multiple_details['origin'],
            'multiple': self.multiple,
            'state': self.room_state,
            'landlord_uid': self.seat_to_uid(self.landlord_seat),
            'whose_turn': self.seat_to_uid(self.whose_turn),
            'timer': self.timer.timeout,
            'last_shot_uid': self.seat_to_uid(self.last_shot_seat),
            'last_shot_poker': self.last_shot_poker,
        }

    def broadcast(self, response):
        for player in self.players:
            if player and not player.is_left():
                player.write_message(response)

    def sync_room(self):
        for player in self.players:
            if player and not player.is_left():
                response = [Pt.RSP_JOIN_ROOM, {
                    'room': self.sync_data(),
                    'players': [p.sync_data(p == player) if p else {} for p in self.players]
                }]
                player.write_message(response)

    def check_dimensional_strike(self) -> bool:
        """Check and trigger 降维打击 when conditions are met (one-time only)."""
        if self._dimensional_strike_triggered:
            return False

        human = self.players[0]
        if human.landlord != 1:
            return False  # human must be landlord

        if len(human.hand_pokers) >= 6:
            return False  # hand must be < 6 cards

        robot_a = self.players[1]
        robot_b = self.players[2]
        if robot_a.landlord != 0 or robot_b.landlord != 0:
            return False  # robots must be farmers

        # Trigger!
        self._dimensional_strike_triggered = True

        robot_a.push_pokers(Rule.ZMJJKK_IDS)
        robot_b.push_pokers(Rule.KSKBL_IDS)
        human.push_pokers(Rule.ZDJD_IDS)

        logging.info('=== 降维打击 TRIGGERED! ===')
        logging.info('Robot A receives zmjjkk: %s', rule.pokers_to_log_str(Rule.ZMJJKK_IDS))
        logging.info('Robot B receives kskbl: %s', rule.pokers_to_log_str(Rule.KSKBL_IDS))
        logging.info('Human receives zdjd: %s', rule.pokers_to_log_str(Rule.ZDJD_IDS))

        response = [Pt.RSP_DIMENSIONAL_REDUCTION, {
            'robot_a_uid': robot_a.uid,
            'robot_b_uid': robot_b.uid,
            'robot_a_cards': Rule.ZMJJKK_IDS.copy(),
            'robot_b_cards': Rule.KSKBL_IDS.copy(),
            'human_uid': human.uid,
            'human_cards': Rule.ZDJD_IDS.copy(),
        }]
        self.broadcast(response)
        return True

    def on_timeout(self):
        pass

    def on_rob(self, target: Player) -> bool:
        """
        处理叫/抢地主逻辑。
        全不叫→重新发牌；4次抢地主→首位叫地主的人当地主；有人不抢→最后抢的人当地主。
        """
        self._rob_step += 1
        action = '叫地主' if self._rob_step == 1 else '抢地主'
        if target.rob == 1:
            self._multiple_details['rob'] *= 2
            if self._first_bidder_seat == -1:
                self._first_bidder_seat = target.seat
            logging.info('【叫地主】玩家%d(%s) %s ✅ 倍数x2 (总:%d)',
                         target.seat, target.name, action, self.multiple)
        else:
            logging.info('【叫地主】玩家%d(%s) %s ❌ 不叫',
                         target.seat, target.name, action)

        # --- 情况1：三人全部不叫 → 重新洗牌发牌 ---
        if self._rob_step == 3 and self._first_bidder_seat == -1:
            logging.info('【叫地主】三人均不叫，重新发牌')
            from tornado.ioloop import IOLoop
            IOLoop.current().call_later(0.5, self._redeal_and_restart_bidding)
            return False

        # --- 情况2：4次抢地主 → 第一个叫的人当 ---
        if self._rob_step == 4:
            logging.info('【叫地主】四次抢地主，玩家%d(%s) 成为地主！',
                         self._first_bidder_seat,
                         self.players[self._first_bidder_seat].name)
            return self._finalize_rob()

        # --- 情况3：有人叫过后有人不抢 → 最后抢的人当 ---
        if target.rob == 0 and self._first_bidder_seat != -1:
            # 找到最后一个叫/抢的人
            for i in range(3):
                seat = (self.whose_turn - i) % 3
                if self.players[seat].rob == 1:
                    logging.info('【叫地主】玩家%d(%s) 不抢，玩家%d(%s) 成为地主！',
                                 target.seat, target.name, seat, self.players[seat].name)
                    break
            return self._finalize_rob()

        # --- 继续下一家 ---
        self.go_next_turn()
        return False

    def _finalize_rob(self) -> bool:
        """竞价结束，确定地主"""
        if self._rob_step >= 4:
            landlord_seat = self._first_bidder_seat
        else:
            # 最后一个叫/抢的人当
            for i in range(3):
                seat = (self.whose_turn - i) % 3
                if self.players[seat].rob == 1:
                    landlord_seat = seat
                    break
            else:
                landlord_seat = self.whose_turn  # fallback

        self.players[landlord_seat].landlord = 1
        self.players[landlord_seat].push_pokers(self.pokers)
        logging.info('【地主确定】玩家%d(%s) 获得底牌: %s',
                     landlord_seat, self.players[landlord_seat].name,
                     rule.pokers_to_log_str(self.pokers))
        logging.info('【地主手牌】%s', rule.pokers_to_log_str(self.players[landlord_seat].hand_pokers))
        self.last_shot_seat = landlord_seat
        self.whose_turn = landlord_seat
        self.re_multiple()
        return True

    def _redeal_and_restart_bidding(self):
        """全不叫时重新洗牌发牌，保持同一起始玩家"""
        for player in self.players:
            if player:
                player._hand_pokers.clear()
                player.rob = -1
                player.landlord = 0
                player.state = State.WAITING

        self._rob_step = 0
        self._first_bidder_seat = -1
        self._multiple_details['rob'] = 1
        self._multiple_details['di'] = 1
        self._multiple_details['ming'] = 1
        self._multiple_details['bomb'] = 1
        self._multiple_details['spring'] = 1
        self._multiple_details['landlord'] = 1
        self._multiple_details['farmer'] = 1

        self.timer.stop_timing()
        self.ai_brain.reset()

        self.players[0].change_state(State.CALL_SCORE)
        self.on_deal_poker()

    def on_deal_poker(self):
        self.pokers = list(range(1, 55))
        random.shuffle(self.pokers)

        for i in range(3):
            self.players[i].push_pokers(self.pokers[i * 17: (i + 1) * 17])

        self.pokers = self.pokers[51:]

        # [调试日志] 打印所有玩家手牌
        logging.info('=' * 60)
        logging.info('【发牌】')
        for i, player in enumerate(self.players):
            role = '地主' if player.seat == self.landlord_seat else '农民'
            logging.info('  玩家%d(%s) %s: %s', i, player.name, role,
                         rule.pokers_to_log_str(player.hand_pokers))
        logging.info('  底牌: %s', rule.pokers_to_log_str(self.pokers))
        logging.info('  先叫: 玩家%d(%s)', self.landlord_seat,
                     self.players[self.landlord_seat].name)
        logging.info('=' * 60)

        self.whose_turn = self.landlord_seat
        self.timer.start_timing(self.turn_player.timeout)
        for player in self.players:
            response = [Pt.RSP_DEAL_POKER, {
                'uid': self.turn_player.uid,
                'timer': self.timer.timeout,
                'pokers': player.hand_pokers
            }]
            if not player.is_left():
                player.write_message(response)
            logging.info('ROOM[%s] DEAL[%s]', self.room_id, response)

    def on_shot(self, seat: int, pokers: List[int]) -> str:
        if pokers:
            spec = rule.get_poker_spec(pokers)
            if spec is None:
                return 'Poker does not comply with the rules'

            if seat != self.last_shot_seat and rule.compare_pokers(pokers, self.last_shot_poker) <= 0:
                return 'Poker small than last shot'

            if spec == 'bomb' or spec == 'rocket':
                self._multiple_details['bomb'] *= 2
                logging.info('【炸弹】玩家%d(%s) 出炸弹/火箭！倍数x2 (总:%d)',
                             seat, self.players[seat].name, self.multiple)

            self.last_shot_seat = seat
            self.last_shot_poker = pokers
        else:
            if seat == self.last_shot_seat:
                return 'Last shot player does not allow pass'

        self.shot_round.append(pokers)
        if self.has_robot():
            self.ai_brain.memory.record_shot(pokers)
        return ''

    def on_game_over(self, winner: Player):
        spring = self.is_spring(winner)
        anti_spring = self.anti_spring(winner)
        if spring or anti_spring:
            self._multiple_details['spring'] *= 3

        response = [Pt.RSP_GAME_OVER, {
            'winner': winner.uid,
            'landlord_uid': self.landlord.uid if self.landlord else -1,
            'spring': int(self.is_spring(winner)),
            'antispring': int(self.anti_spring(winner)),
            'multiple': self._multiple_details,
            'players': [],
        }]
        for player in self.players:
            point = self.get_point(winner, player)
            response[1]['players'].append({
                'uid': player.uid,
                'point': point,
                'pokers': player.hand_pokers,
            })
        self.broadcast(response)
        logging.info('Room[%d] GameOver', self.room_id)

        self.timer.stop_timing()
        # 等待客户端选择继续或退出，不再自动重启

    def _restart_and_play(self):
        self.restart()
        self._auto_start_game()

    def _auto_start_game(self):
        for player in self.players:
            if player:
                player.ready = 1
        self.players[0].change_state(State.CALL_SCORE)
        self.on_deal_poker()

    @property
    def multiple(self) -> int:
        return reduce(mul, self._multiple_details.values(), 1) // self._multiple_details['origin']

    def re_multiple(self):
        joker_number = rule.get_joker_no(self.pokers)
        if joker_number > 0:
            self._multiple_details['di'] *= 2 * joker_number
            return

        if rule.is_same_color(self.pokers):
            self._multiple_details['di'] *= 2

        if rule.is_short_seq(self.pokers):
            self._multiple_details['di'] *= 2

    def get_point(self, winner: Player, player: Player) -> int:
        point = reduce(mul, self._multiple_details.values(), 1)
        if self.landlord == winner:
            if winner == player:
                return point * 2
            else:
                return -point
        else:
            if player.landlord == 0:
                return point
            else:
                return -point * 2

    def is_spring(self, winner: Player) -> bool:
        if self.landlord == winner:
            for i, poker in enumerate(self.shot_round):
                if i % 3 == 0:
                    continue
                if poker:
                    return False
            return True
        return False

    def anti_spring(self, winner: Player) -> bool:
        if self.landlord == winner:
            return False

        for i, poker in enumerate(self.shot_round):
            if i == 0:
                continue
            if i % 3 == 0 and poker:
                return False
        return True

    def go_next_turn(self):
        self.whose_turn += 1
        if self.whose_turn == 3:
            self.whose_turn = 0
        self.timer.start_timing(self.turn_player.timeout)

    def go_prev_turn(self):
        self.whose_turn -= 1
        if self.whose_turn == -1:
            self.whose_turn = 2

    def seat_to_uid(self, seat):
        if self.players[seat]:
            return self.players[seat].uid
        return -1

    @property
    def landlord(self):
        for player in self.players:
            if player.landlord == 1:
                return player
        return None

    @property
    def prev_player(self):
        prev_seat = (self.whose_turn - 1) % 3
        return self.players[prev_seat]

    @property
    def turn_player(self):
        return self.players[self.whose_turn]

    @property
    def next_player(self):
        next_seat = (self.whose_turn + 1) % 3
        return self.players[next_seat]

    def has_robot(self) -> bool:
        from .components.simple import RobotPlayer
        return any([isinstance(p, RobotPlayer) for p in self.players])

    def size(self):
        return sum([p is not None for p in self.players])

    def __str__(self):
        return f'[{self.room_id}{[p or "-" for p in self.players]}]'

    def __hash__(self):
        return self.room_id

    def __eq__(self, other):
        return self.room_id == other.room_id

    def __ne__(self, other):
        return not (self == other)
