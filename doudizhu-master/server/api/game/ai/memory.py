"""
牌记忆模块 - CardMemory
追踪所有已公开出的牌，统计每种牌面值剩余张数。
为其他 AI 子系统提供公共信息。
"""

from typing import Dict, List, Set


class CardMemory:
    """
    追踪当前局中所有已出过的牌。
    同一 Room 内的机器人共享同一个 CardMemory 实例。

    初始状态：每种牌面值 3~2 各 4 张，小王 1 张，大王 1 张。
    """

    RANK_ORDER = '34567890JQKA2wW'

    def __init__(self):
        self.remaining: Dict[str, int] = {}
        self._played_history: List[List[int]] = []
        self.reset()

    def reset(self):
        """重置为初始状态（新牌局开始）"""
        self.remaining = {r: 4 for r in '34567890JQKA2'}
        self.remaining['w'] = 1
        self.remaining['W'] = 1
        self._played_history.clear()

    def record_shot(self, pokers: List[int]):
        """记录一次出牌（包括空列表 = pass）"""
        if not pokers:
            return
        from ..rule import rule
        cards = rule._to_cards(pokers)
        for c in cards:
            if c in self.remaining and self.remaining[c] > 0:
                self.remaining[c] -= 1
        self._played_history.append(pokers)

    def unseen_ranks(self) -> Set[str]:
        """返回还有至少 1 张未出的牌面值集合"""
        return {r for r, n in self.remaining.items() if n > 0}

    def unseen_count(self, rank: str) -> int:
        """某牌面值还有几张未出"""
        return self.remaining.get(rank, 0)

    def bombs_remaining(self) -> int:
        """估算还有多少个炸弹（含火箭）的可能"""
        count = 0
        for r in '34567890JQKA2':
            if self.remaining[r] == 4:
                count += 1
        if self.remaining.get('w', 0) == 1 and self.remaining.get('W', 0) == 1:
            count += 1
        return count

    def rocket_remaining(self) -> bool:
        """火箭（大小王）是否仍在未出状态"""
        return self.remaining.get('w', 0) == 1 and self.remaining.get('W', 0) == 1

    def cards_above_rank(self, rank_char: str) -> int:
        """比某牌面大的牌还剩多少张（用于判断压制风险）"""
        idx = self.RANK_ORDER.index(rank_char)
        higher = self.RANK_ORDER[idx + 1:]
        return sum(self.remaining.get(r, 0) for r in higher)

    def rank_count_above(self, rank_char: str) -> int:
        """比某牌面大的牌还剩几个牌面值（非张数）"""
        idx = self.RANK_ORDER.index(rank_char)
        higher = self.RANK_ORDER[idx + 1:]
        return sum(1 for r in higher if self.remaining.get(r, 0) > 0)

    def all_2s_played(self) -> bool:
        """所有 2 是否已出完"""
        return self.remaining.get('2', 0) == 0

    def all_As_played(self) -> bool:
        """所有 A 是否已出完"""
        return self.remaining.get('A', 0) == 0

    def get_played_history(self) -> List[List[int]]:
        """获取出牌历史记录"""
        return list(self._played_history)
