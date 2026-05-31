import json
import logging
from typing import Optional, Any, Dict, List, Union

from tornado.websocket import WebSocketHandler, WebSocketClosedError

from .globalvar import GlobalVar
from .player import Player, State
from .protocol import Protocol as Pt
from .room import Room


class SocketHandler(WebSocketHandler):

    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.player: Optional[Player] = None
        self._test_dim_mode = False

    @property
    def room(self) -> Optional[Room]:
        return self.player.room if self.player else None

    async def open(self):
        """当客户端连接时，自动创建/获取房间并开始游戏"""
        # Check for test mode: ?test=dim
        query = self.request.uri.split('?', 1)[-1] if '?' in self.request.uri else ''
        self._test_dim_mode = 'test=dim' in query

        room = GlobalVar.get_or_create_room()

        # 创建人类玩家
        self.player = Player(1, '玩家', 1, '')
        self.player.socket = self

        # 如果房间已满或游戏中，创建新房间
        if room.size() == 3:
            from .globalvar import GlobalVar as GV
            GV.clear_room()
            room = GV.get_or_create_room()

        # 将人类玩家加入房间（座位0）
        self.player.seat = 0
        room.players[0] = self.player
        self.player.state = State.WAITING
        self.player.room = room

        # 创建2个机器人并加入房间
        from .components.simple import RobotPlayer
        if room.players[1] is None:
            robot1 = RobotPlayer(10001, '机器人-A', 0, '', room)
            robot1.seat = 1
            room.players[1] = robot1
            robot1.state = State.WAITING
            room.robot_no += 1
        if room.players[2] is None:
            robot2 = RobotPlayer(10002, '机器人-B', 0, '', room)
            robot2.seat = 2
            room.players[2] = robot2
            robot2.state = State.WAITING
            room.robot_no += 1

        # 发送房间信息给客户端
        room.sync_room()

        # 自动开始游戏
        from tornado.ioloop import IOLoop
        IOLoop.current().add_callback(self._auto_start_game)

        logging.info('Player connected, game started')

    async def _auto_start_game(self):
        """自动准备所有玩家并开始发牌"""
        import asyncio
        await asyncio.sleep(0.3)  # 等待客户端初始化完成
        
        room = self.room
        if not room:
            return

        # 所有玩家准备
        for p in room.players:
            if p:
                p.ready = 1

        # 开始发牌和叫地主流程
        room.players[0].change_state(State.CALL_SCORE)
        room.on_deal_poker()

        # 降维打击测试模式：固定玩家手牌 < 6，固定为地主，机器人为农民
        if self._test_dim_mode:
            self.player._hand_pokers = [3, 4, 5, 6, 7]
            self.player.landlord = 1
            room.landlord_seat = 0
            room.last_shot_seat = 0
            room.pokers = []  # 底牌清空，防止加入地主手牌
            for p in room.players:
                if p and p != self.player:
                    p.landlord = 0
            logging.info('【测试模式】降维打击测试: 玩家固定为地主,手牌=%s', self.player.hand_pokers)
            # 重新广播各玩家手牌
            for p in room.players:
                if p:
                    p.write_message([
                        Pt.RSP_DEAL_POKER,
                        {'uid': p.uid, 'timer': room.timer.timeout, 'pokers': p.hand_pokers}
                    ])

    async def on_message(self, message):
        if message == 'ping':
            self._write_message('pong')
            return

        code, packet = self.decode_message(message)
        if code is None:
            self.write_message([Pt.ERROR, {'reason': 'Protocol cannot be resolved'}])
            return

        logging.info('REQ: %s', message)

        if self.player:
            await self.player.on_message(code, packet)

    def on_close(self):
        if self.player:
            logging.info('Player DISCONNECTED')
            self.player.socket = None

    def check_origin(self, origin: str) -> bool:
        return True

    def write_message(self, message: List[Union[Pt, Dict[str, Any]]], binary=False) -> Optional[None]:
        packet = json.dumps(message)
        self._write_message(packet, binary)

    def _write_message(self, message, binary=False):
        if self.ws_connection is None:
            return
        try:
            self.ws_connection.write_message(message, binary=binary)
            logging.info('RSP: %s', message)
        except WebSocketClosedError:
            logging.error('WebSocketClosed')

    @staticmethod
    def decode_message(message):
        try:
            code, packet = json.loads(message)
            if isinstance(code, int) and isinstance(packet, dict):
                return code, packet
        except (json.decoder.JSONDecodeError, ValueError):
            logging.error('ERROR MESSAGE: %s', message)
        return None, None
