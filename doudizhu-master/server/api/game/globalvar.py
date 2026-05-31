import logging
from typing import Optional

from .player import Player
from .room import Room


class GlobalVar(object):
    total_room_count = 0
    __room__: Optional[Room] = None

    @classmethod
    def get_or_create_room(cls) -> Room:
        if cls.__room__ is None:
            cls.__room__ = Room(1, 1, True)
            logging.info('Room created')
        return cls.__room__

    @classmethod
    def clear_room(cls):
        cls.__room__ = None
        logging.info('Room cleared')
