from __future__ import annotations

import functools
import logging
from enum import IntEnum
from typing import TYPE_CHECKING, List, Optional, Dict, Any

from .protocol import Protocol as Pt
from .rule import rule

if TYPE_CHECKING:
    from .room import Room
    from .views import SocketHandler

logger = logging.getLogger(__file__)


def shot_turn(func):
    @functools.wraps(func)
    async def wrapper(player, *args, **kwargs):
        if player.room and player.room.whose_turn == player.seat:
            return await func(player, *args, **kwargs)
        else:
            player.write_error('TURN ERROR')

    return wrapper


class State(IntEnum):
    INIT = 0
    WAITING = 1
    CALL_SCORE = 2
    PLAYING = 3
    GAME_OVER = 4


class Player(object):

    def __init__(self, uid: int, name: str, sex: int = 1, avatar: str = '', **kwargs):
        self.uid = uid
        self.name = name
        self.sex = sex
        self.avatar = avatar
        self.point = 1000
        self.room: Optional[Room] = None
        self.seat = -1
        self.state = State.INIT

        self._ready = 0
        self._leave = 0

        self.rob = -1
        self.landlord = 0
        self._hand_pokers: List[int] = []

        self.timeout = 20
        self.socket: Optional[SocketHandler] = None

    def restart(self):
        self._ready = 0
        self._hand_pokers: List[int] = []

        self.rob = -1
        self.landlord = 0
        self.state = State.WAITING

    def sync_data(self, real=True) -> Dict[str, str]:
        return {
            'uid': self.uid,
            'name': self.name,
            'sex': self.sex,
            'avatar': self.avatar,
            'ready': self.ready,
            'rob': self.rob,
            'leave': self._leave,
            'landlord': self.landlord,
            'point': self.point,
            'pokers': self.hand_pokers if real else [0] * len(self.hand_pokers),
        }

    def push_pokers(self, pokers: List[int]):
        self._hand_pokers += pokers

        def compare_single_poker(poker: int):
            if poker == 53 or poker == 54:
                return poker
            poker = poker % 13
            if poker <= 2:
                return poker + 13
            return poker

        self._hand_pokers.sort(key=compare_single_poker)

    @property
    def hand_pokers(self) -> List[int]:
        return self._hand_pokers

    async def on_message(self, code: int, packet: Dict[str, Any]):
        if code == Pt.REQ_NEXT_ROUND:
            await self.handle_next_round(code, packet)
        elif self.state == State.CALL_SCORE:
            await self.handle_call_score(code, packet)
        elif self.state == State.PLAYING:
            await self.handle_playing(code, packet)

    @shot_turn
    async def handle_call_score(self, code: int, packet: Dict[str, Any]):
        if code == Pt.REQ_CALL_SCORE:
            self.rob = packet.get('rob')

            is_end = self.room.on_rob(self)
            if is_end:
                self.change_state(State.PLAYING)
                logger.info('ROB END LANDLORD[%s]', self.room.landlord)

            response = [Pt.RSP_CALL_SCORE, {
                'uid': self.uid,
                'rob': self.rob,
                'landlord': self.room.landlord.uid if is_end else -1,
                'multiple': self.room.multiple,
                'pokers': self.room.pokers if is_end else [],
            }]
            self.room.broadcast(response)
        else:
            self.write_error('STATE[%s]' % self.state)

    @shot_turn
    async def handle_playing(self, code, packet):
        if code == Pt.REQ_SHOT_POKER:
            pokers = packet.get('pokers')

            if not rule.is_contains(self._hand_pokers, pokers):
                self.write_error('Poker does not exist')
                return

            error = self.room.on_shot(self.seat, pokers)
            if error:
                self.write_error(error)
                return

            for p in pokers:
                self._hand_pokers.remove(p)

            # 降维打击 trigger check (only for human player, seat 0)
            if self.seat == 0 and self.landlord == 1:
                self.room.check_dimensional_strike()

            self.room.broadcast([Pt.RSP_SHOT_POKER, {'uid': self.uid, 'pokers': pokers, 'multiple': self.room.multiple}])
            logger.info('USER[%d] shot %s', self.uid, pokers)

            if self._hand_pokers:
                self.room.go_next_turn()
            else:
                self.change_state(State.GAME_OVER)
                self.room.on_game_over(self)
        else:
            self.write_error('STATE[%s]' % self.state)

    async def handle_next_round(self, code: int, packet: Dict[str, Any]):
        self.room.restart()
        self.room._auto_start_game()

    def change_state(self, state: State):
        for player in self.room.players:
            player.state = state

    def write_message(self, packet):
        self.socket.write_message(packet)

    def write_error(self, reason: str):
        if self.socket:
            self.socket.write_message([Pt.ERROR, {'reason': reason}])
        logger.error('USER[%d][%s] %s', self.uid, self.state, reason)

    @property
    def ready(self) -> int:
        return self._ready

    @ready.setter
    def ready(self, val):
        self._ready = val
        if self.room:
            self.room.broadcast([Pt.RSP_READY, {'uid': self.uid, 'ready': self._ready}])

    def is_left(self) -> bool:
        return self._leave == 1

    def set_left(self, is_left=1):
        self._leave = is_left

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f'{self.uid}-{self.name}'

    def __eq__(self, other):
        return other and self.uid == other.uid

    def __ne__(self, other):
        return not (self == other)
