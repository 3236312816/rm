import json
import logging
import os
import random
from functools import reduce
from operator import mul
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Iterable, Optional

'''
# A 2 3 4 5 6 7 8 9 0 J Q K w W
'''

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, '..', '..', 'static')

CARD_TYPES = (
    'single', 'pair', 'trio', 'trio_pair', 'trio_single',
    'seq_single5', 'seq_single6', 'seq_single7', 'seq_single8', 'seq_single9', 'seq_single10', 'seq_single11',
    'seq_single12',
    'seq_pair3', 'seq_pair4', 'seq_pair5', 'seq_pair6', 'seq_pair7', 'seq_pair8', 'seq_pair9', 'seq_pair10',
    'seq_trio2', 'seq_trio3', 'seq_trio4', 'seq_trio5', 'seq_trio6',
    'seq_trio_pair2', 'seq_trio_pair3', 'seq_trio_pair4',
    'seq_trio_single2', 'seq_trio_single3', 'seq_trio_single4', 'seq_trio_single5',
    'bomb_pair', 'bomb_single',
    'bomb', 'rocket',
    '7k7k', 'AK47',
)


class Rule(object):
    # 降维打击 special card definitions
    ZMJJKK_CARDS = ['z', 'm', 'j', 'j', 'k', 'k']
    KSKBL_CARDS = ['k', 's', 'k', 'b', 'l']
    ZDJD_CARDS = ['z', 'd', 'j', 'd']
    ZMJJKK_IDS = [101, 102, 103, 104, 105, 106]
    KSKBL_IDS = [107, 108, 109, 110, 111]
    ZDJD_IDS = [112, 113, 114, 115]
    ZMJJKK_SORTED = 'jjkkmz'
    KSKBL_SORTED = 'bkkls'
    ZDJD_SORTED = 'jzdd'

    def __init__(self, rules: Dict[str, List[str]]):
        self.rules = rules
        self.cnt_to_specs: Dict[int, List[str]] = defaultdict(list)
        for name, specs_list in rules.items():
            self.cnt_to_specs[len(specs_list[0])].append(name)

    def get_poker_spec(self, pokers: List[int]) -> Optional[str]:
        # Fast-path for 降维打击 special combos
        sorted_pokers = sorted(pokers)
        if sorted_pokers == Rule.ZMJJKK_IDS:
            return 'zmjjkk'
        if sorted_pokers == Rule.KSKBL_IDS:
            return 'kskbl'
        if sorted_pokers == Rule.ZDJD_IDS:
            return 'zdjd'
        cards = ''.join(self._to_cards(pokers))
        for spec in self.cnt_to_specs.get(len(cards), []):
            if cards in self.rules[spec]:
                return spec
        return None

    def find_best_shot(self, hand_pokers: List[int]) -> List[int]:
        hand_cards = self._to_cards(hand_pokers)
        best_shot = self._find_best_shot(hand_cards)
        return self._to_pokers(hand_pokers, best_shot)

    def find_best_follow(self, hand_pokers: List[int], turn_pokers: List[int], ally=True) -> List[int]:
        hand_cards = self._to_cards(hand_pokers)
        turn_cards = self._to_cards(turn_pokers)
        best_follow = self._find_follow_shot(hand_cards, turn_cards, ally)
        return self._to_pokers(hand_pokers, best_follow)

    def _find_follow_shot(self, hand_cards: List[str], turn_cards: List[str], ally=True) -> str:
        turn_card_type, turn_card_value = self._get_cards_value(turn_cards)
        if not turn_card_type:
            return ''

        def _reduce_single_number() -> int:
            n = 0
            if 'seq_single' in turn_card_type or 'seq_trio_single' in turn_card_type:
                n = int(turn_card_type[-2:]) // 2 if turn_card_type[-2].isdigit() else int(turn_card_type[-1]) // 2
            elif 'single' in turn_card_type:
                n = 1
            return max(n if ally else n//2, 0)

        rockets, bombs, big_cards, small_cards = self._get_basic_cards(hand_cards)

        total_single_no = self.get_single_no(small_cards)
        reduce = _reduce_single_number()

        for cards in (small_cards, hand_cards):
            for i, spec in enumerate(self.rules[turn_card_type]):
                if i > turn_card_value and self.is_contains(cards, spec):
                    left_cards = self.minus(cards, spec)
                    if self._find_one_shot(left_cards):
                        return spec
                    if total_single_no - self.get_single_no(left_cards) >= reduce:
                        return spec
            if ally and len(hand_cards) - len(turn_cards) >= 2:
                break

        if ally:
            return ''

        for cards in (big_cards, hand_cards):
            for i, spec in enumerate(self.rules[turn_card_type]):
                if i > turn_card_value and self.is_contains(cards, spec):
                    return spec

        # 降维打击特殊组合（仅对敌人）：按值从低到高检查
        # zmjjkk(40000) > AK47(39000) > rocket(38000) > 7k7k(37000) > zdjd(36000) > kskbl(35000) > bomb(30000+)
        if turn_card_value < 35000 and self.is_contains(hand_cards, Rule.KSKBL_CARDS):
            return Rule.KSKBL_SORTED
        if turn_card_value < 36000 and self.is_contains(hand_cards, Rule.ZDJD_CARDS):
            return Rule.ZDJD_SORTED
        if turn_card_value < 37000:
            for spec in self.rules.get('7k7k', []):
                if self.is_contains(hand_cards, spec):
                    return spec
        if turn_card_value < 38000 and rockets:
            return rockets[0]
        if turn_card_value < 39000:
            for spec in self.rules.get('AK47', []):
                if self.is_contains(hand_cards, spec):
                    return spec
        if turn_card_value < 40000 and self.is_contains(hand_cards, Rule.ZMJJKK_CARDS):
            return Rule.ZMJJKK_SORTED

        if bombs:
            return bombs[0]

        if rockets:
            return rockets[0]
        return ''

    def _find_best_shot(self, hand_cards: List[str]) -> str:
        one_shot = self._find_one_shot(hand_cards)
        if one_shot:
            return one_shot

        rockets, bombs, big_cards, small_cards = self._get_basic_cards(hand_cards)
        if small_cards or big_cards:
            one_shot = self._find_one_shot(small_cards or big_cards)
            if one_shot:
                return one_shot
        else:
            return bombs[0]

        total_single = self.get_single_no(small_cards)

        best_seq_single, left_cards = self._find_best_seq(small_cards)
        if best_seq_single:
            return best_seq_single[0]

        shot_order = (
            (['trio_single', 'single', 'pair', 'trio_single'], -1),
            (['seq_trio_single4', 'seq_trio_single3', 'seq_trio_single2'], -1),
            (['seq_trio_pair3', 'seq_trio_pair2', 'trio_pair'], 0),
            (['seq_pair9', 'seq_pair8', 'seq_pair7', 'seq_pair6', 'seq_pair5', 'seq_pair4', 'seq_pair3'], 0)
        )

        abs_small_cards = [card for card in small_cards if card in '34567890']

        for cards in (abs_small_cards, small_cards):
            for specs, single_reduce in shot_order:
                best_shot = self._find_spec_shot(cards, specs, total_single + single_reduce)
                if best_shot:
                    return best_shot

        if small_cards:
            if len(small_cards) == 1:
                return small_cards[0]
            if small_cards[0] == small_cards[1]:
                return small_cards[0] + small_cards[1]
            return small_cards[0]

        for specs, single_reduce in shot_order:
            best_shot = self._find_spec_shot(hand_cards, specs, total_single + single_reduce)
            if best_shot:
                return best_shot

        for spec in ['pair', 'trio', 'single']:
            trio, after_cards = self._find_spec_type(hand_cards, spec)
            if trio and self.get_single_no(after_cards) <= total_single:
                return trio[0]

        # 降维打击特殊组合（作为出牌选项）
        if self.is_contains(hand_cards, Rule.ZMJJKK_CARDS):
            return Rule.ZMJJKK_SORTED
        if self.is_contains(hand_cards, Rule.ZDJD_CARDS):
            return Rule.ZDJD_SORTED
        if self.is_contains(hand_cards, Rule.KSKBL_CARDS):
            return Rule.KSKBL_SORTED
        for spec in self.rules.get('7k7k', []):
            if self.is_contains(hand_cards, spec):
                return spec
        for spec in self.rules.get('AK47', []):
            if self.is_contains(hand_cards, spec):
                return spec

        return hand_cards[0]

    def _find_one_shot(self, hand_cards: List[str]):
        cards_no = len(hand_cards)
        for spec in self.cnt_to_specs.get(cards_no, []):
            if spec == 'bomb_single' or spec == 'bomb_pair':
                continue
            results, left_cards = self._find_spec_type(hand_cards, spec)
            if not left_cards:
                return results[0]
        return None

    def _get_basic_cards(self, hand_cards: List[str]):
        rockets, left_cards = self._find_spec_type(hand_cards, 'rocket')
        bombs, left_cards = self._find_spec_type(left_cards, 'bomb')
        return rockets, bombs, self.get_big_cards(left_cards), self.get_small_cards(left_cards)

    def _find_best_seq(self, hand_cards: List[str]) -> Tuple[List[str], List[str]]:
        total_single_no = self.get_single_no(hand_cards)
        best_shot, best_left_cards, best_single_no = [], [], total_single_no

        seq_specs = [f'seq_single{n}' for n in (12, 11, 10, 9, 8, 7, 6, 5)]
        for seq_spec in seq_specs:
            seq_single, left_cards = self._find_spec_type(hand_cards, seq_spec)
            single_num = total_single_no - self.get_single_no(left_cards)
            if single_num < best_single_no:
                best_shot = seq_single
                best_left_cards = left_cards
                best_single_no = single_num

        if total_single_no - best_single_no > 2:
            return best_shot, best_left_cards
        return [], hand_cards

    def _find_spec_shot(self, hand_cards: List[str], specs: List[str], single: int) -> Optional[str]:
        for spec in specs:
            seq, left_cards = self._find_spec_type(hand_cards, spec)
            if seq and self.get_single_no(left_cards) <= single:
                return seq[0]
        return None

    def _find_spec_type(self, hand_cards: List[str], card_type: str) -> Tuple[List[str], List[str]]:
        left_cards = [c for c in hand_cards]
        result = []
        for spec in self.rules[card_type]:
            if self.is_contains(left_cards, spec):
                for sp in spec:
                    left_cards.remove(sp)
                result.append(spec)
        return result, left_cards

    def _expand_seq_multiple(self, seq: str, available: List[str]) -> Tuple[str, List[str]]:
        while len(available) > 0:
            size = len(available)
            seq, available = self._expand_seq_once(seq, available)
            if len(available) == size:
                break
        return seq, available

    def _expand_seq_once(self, seq: str, available: List[str]) -> Tuple[str, List[str]]:
        spec = f'seq_single{len(seq) + 1}'
        if spec not in self.rules:
            return seq, available

        for card in available:
            if self.safe_index_of(self.rules[spec], seq + card) < 0:
                continue
            available.remove(card)
            return seq + card, available
        return seq, available

    def compare_pokers(self, a_pokers: List[int], b_pokers: List[int]) -> int:
        if not a_pokers or not b_pokers:
            if a_pokers == b_pokers:
                return 0
            if a_pokers:
                return 1
            if b_pokers:
                return 1

        a_card_type, a_card_value = self._get_cards_value(self._to_cards(a_pokers))
        b_card_type, b_card_value = self._get_cards_value(self._to_cards(b_pokers))
        if a_card_type == b_card_type:
            return a_card_value - b_card_value

        # Both are special (炸弹/kskbl/zdjd/7k7k/火箭/AK47/zmjjkk) → 直接比值
        if a_card_value >= 30000 and b_card_value >= 30000:
            return a_card_value - b_card_value
        # Only a is special
        if a_card_value >= 30000:
            return 1
        # Neither or only b is special
        return -1

    def _get_cards_value(self, cards: List[str]) -> Tuple[str, int]:
        cards_str = ''.join(cards)
        if cards_str == Rule.ZMJJKK_SORTED:
            return 'zmjjkk', 40000
        if cards_str in self.rules.get('AK47', []):
            return 'AK47', 39000
        if cards_str == 'wW':
            return 'rocket', 38000
        if cards_str in self.rules.get('7k7k', []):
            return '7k7k', 37000
        if cards_str == Rule.ZDJD_SORTED:
            return 'zdjd', 36000
        if cards_str == Rule.KSKBL_SORTED:
            return 'kskbl', 35000

        value = self.safe_index_of(self.rules['bomb'], cards_str)
        if value >= 0:
            return 'bomb', 30000 + value

        return self._get_card_value(cards_str)

    def _get_card_value(self, cards: str) -> Tuple[str, int]:
        specs = self.cnt_to_specs.get(len(cards), [])
        for spec in specs:
            value = self.safe_index_of(self.rules[spec], cards)
            if value >= 0:
                return spec, value
        logging.error('Unknown Card Type: %s', cards)
        return '', 0

    @staticmethod
    def _to_cards(pokers) -> List[str]:
        cards = []
        for p in pokers:
            if p == 53:
                cards.append('w')
            elif p == 54:
                cards.append('W')
            elif 101 <= p <= 106:
                cards.append(Rule.ZMJJKK_CARDS[p - 101])
            elif 107 <= p <= 111:
                cards.append(Rule.KSKBL_CARDS[p - 107])
            elif 112 <= p <= 115:
                cards.append(Rule.ZDJD_CARDS[p - 112])
            else:
                cards.append('KA234567890JQ'[p % 13])
        return Rule._sort_card(cards)

    @staticmethod
    def pokers_to_log_str(pokers) -> str:
        """扑克ID列表转日志可读字符串，如 'S3 H5 w C9' 或 'Z1 Z2 Z3' (特殊牌)"""
        suit_names = ['S', 'H', 'C', 'D']
        rank_names = 'KA234567890JQ'
        parts = []
        for p in sorted(pokers):
            if p == 53:
                parts.append('w')
            elif p == 54:
                parts.append('W')
            elif 101 <= p <= 106:
                parts.append(f'Z{p-100}')
            elif 107 <= p <= 111:
                parts.append(f'K{p-106}')
            elif 112 <= p <= 115:
                parts.append(f'D{p-111}')
            else:
                s = (p - 1) // 13
                r = rank_names[p % 13]
                parts.append(f'{suit_names[s]}{r}')
        return ' '.join(parts)

    @staticmethod
    def _to_poker(card: str) -> List[int]:
        if card == 'w':
            return [53]
        if card == 'W':
            return [54]

        # 降维打击 special chars
        if card == 'z': return [101, 112]  # zmjjkk + zdjd
        if card == 'm': return [102]
        if card == 'j': return [103, 104, 114]  # zmjjkk (x2) + zdjd
        if card == 'k': return [105, 106, 109, 110]  # zmjjkk (x2) + kskbl (x2)
        if card == 's': return [108]
        if card == 'b': return [107]
        if card == 'l': return [111]
        if card == 'd': return [113, 115]  # zdjd (x2)

        cards = '?A234567890JQK'
        for i, c in enumerate(cards):
            if c == card:
                return [i, i + 13, i + 26, i + 39]
        return [55]

    @staticmethod
    def _to_pokers(hand_pokers: List[int], cards: Iterable) -> List[int]:
        cards_list = list(cards)
        # Direct mapping for special combos
        if sorted(cards_list) == sorted(Rule.ZMJJKK_CARDS):
            return [pid for pid in Rule.ZMJJKK_IDS if pid in hand_pokers]
        if sorted(cards_list) == sorted(Rule.KSKBL_CARDS):
            return [pid for pid in Rule.KSKBL_IDS if pid in hand_pokers]
        if sorted(cards_list) == sorted(Rule.ZDJD_CARDS):
            return [pid for pid in Rule.ZDJD_IDS if pid in hand_pokers]
        pokers = []
        for card in cards_list:
            candidates = Rule._to_poker(card)
            for cd in candidates:
                if cd in hand_pokers and cd not in pokers:
                    pokers.append(cd)
                    break
        return pokers

    @staticmethod
    def get_small_cards(hand_cards: Iterable) -> List[str]:
        return [c for c in hand_cards if c not in '2wW']

    @staticmethod
    def get_big_cards(hand_cards: Iterable) -> List[str]:
        return [c for c in hand_cards if c in '2wW']

    @staticmethod
    def get_single_no(hand_cards: List[str]) -> int:
        return sum(v for _, v in Counter(hand_cards).items() if v == 1)

    @staticmethod
    def is_same_color(hand_pokers: List[int]) -> bool:
        colors = map(lambda poker: (poker - 1) // 13, hand_pokers)
        return len(set(colors)) == 1

    @staticmethod
    def is_short_seq(hand_pokers: List[int]) -> bool:
        if any(map(lambda p: p in hand_pokers,  [2, 15, 28, 41, 53, 54])):
            return False
        pokers = []
        for poker in hand_pokers:
            poker = poker % 13
            if poker == 0 or poker == 1:
                poker += 13
            pokers.append(poker)
        pokers.sort()
        return sum(pokers) == (pokers[0] + pokers[-1]) * len(pokers) // 2

    @staticmethod
    def get_joker_no(hand_pokers: List[str]) -> int:
        cnt = 0
        if 53 in hand_pokers:
            cnt += 1
        if 54 in hand_pokers:
            cnt += 1
        return cnt

    @staticmethod
    def _sort_card(cards: List[str]):
        cards.sort(key=lambda ch: '34567890JQKA2wWbjklmszd'.index(ch))
        return cards

    @staticmethod
    def safe_index_of(array: List[str], ele: str) -> int:
        if len(array[0]) != len(ele):
            return -1
        try:
            return array.index(ele)
        except ValueError:
            return -1

    @staticmethod
    def is_contains(parent: List, child: Iterable) -> bool:
        parent, child = Counter(parent), Counter(child)
        for k, cnt in child.items():
            if k not in parent or cnt > parent[k]:
                return False
        return True

    @staticmethod
    def minus(hand_cards: List[str], shot_cards: Iterable) -> List[str]:
        hand_cards = [card for card in hand_cards]
        for card in shot_cards:
            hand_cards.remove(card)
        return hand_cards


rule_json_path = os.path.join(STATIC_DIR, 'rule.json')
if not os.path.exists(rule_json_path):
    rule_json_path = os.path.join(BASE_DIR, '..', '..', '..', 'static', 'rule.json')

with open(rule_json_path, 'r') as f:
    rule = Rule(json.load(f))
