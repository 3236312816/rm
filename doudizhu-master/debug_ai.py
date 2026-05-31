"""
斗地主 AI 调试工具
- 发牌展示所有机器人手牌
- 显示每个 AI 的叫地主决策（评分明细）
- 模拟一轮出牌，展示 AI 的跟牌/领出决策

用法: python debug_ai.py
"""

import sys
import os
import random
from collections import Counter

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.api.game.rule import rule
from server.api.game.ai.evaluator import HandEvaluator
from server.api.game.ai.memory import CardMemory
from server.api.game.ai.strategy import BiddingStrategy, LeadingStrategy, FollowingStrategy, EndgameStrategy
from server.api.game.ai.robot import AIBrain

# ============================================================
# 扑克显示工具
# ============================================================

SUITS = ['[S]', '[H]', '[C]', '[D]']
RANKS = 'KA234567890JQ'


def poker_to_str(poker: int) -> str:
    """单个扑克 ID -> 可读字符串 (如 [S]K)"""
    if poker == 53:
        return '  SJ'  # Small Joker
    if poker == 54:
        return '  BJ'  # Big Joker
    suit = (poker - 1) // 13
    rank = RANKS[poker % 13]
    return f'{SUITS[suit]}{rank}'


def card_to_str(card: str) -> str:
    """牌面值转显示 (w->小王, W->大王)"""
    mapping = {'w': 'w(小王)', 'W': 'W(大王)'}
    return mapping.get(card, card)


def hand_str(pokers) -> str:
    """手牌列表 -> 可读字符串"""
    return '  '.join(poker_to_str(p) for p in sorted(pokers))


def card_list_str(cards) -> str:
    """牌面值列表 -> 可读字符串"""
    return ' '.join(card_to_str(c) for c in cards)


def shot_info(pokers):
    """出牌信息：类型 + 牌面值"""
    if not pokers:
        return 'pass'
    cards = rule._to_cards(pokers)
    ctype, cval = rule._get_cards_value(cards)
    return f'{ctype}({card_list_str(cards)})'


# ============================================================
# 模拟游戏
# ============================================================

class DummyPlayer:
    """最小化玩家对象，供 AI 策略使用"""
    def __init__(self, hand_pokers, seat, landlord=0, name=''):
        self.hand_pokers = hand_pokers
        self.seat = seat
        self.landlord = landlord
        self.name = name or f'P{seat}'


class DummyRoom:
    """最小化房间对象，供 AI 决策使用"""
    def __init__(self, players):
        self.players = players
        self.last_shot_poker = []
        self.last_shot_seat = -1
        self.ai_brain = AIBrain()


def print_hand_analysis(hand_pokers, player_name, ai_brain, position, is_grab=False):
    """打印一手牌的完整分析"""
    evaluator = ai_brain.evaluator
    cards = rule._to_cards(hand_pokers)
    score, breakdown = evaluator.evaluate(cards)
    effective = score

    print(f'\n{player_name}  手牌({len(hand_pokers)}张):')
    print(f'  {hand_str(hand_pokers)}')
    print(f'  牌面: {card_list_str(cards)}')

    # 评分明细
    print(f'  +-- 综合评分: {score:.1f}')
    print(f'  |  明细:')
    for k, v in sorted(breakdown.items()):
        if v != 0:
            label = {'rocket': '火箭', 'bombs': '炸弹', 'premium': '高牌(王2A)',
                     'structure': '结构(三张/对子)', 'sequence': '顺子',
                     'singles_penalty': '孤立单牌扣分', 'no_pair_penalty': '无对子扣分',
                     'size_bonus': '手牌少加分', 'total': '总分'}.get(k, k)
            print(f'  |    {label}: {v:+.1f}')

    # 叫地主判断
    bid = ai_brain.decide_bid(hand_pokers, position, is_grab)
    bid_text = '叫地主' if not is_grab else '抢地主'
    # 计算有效分和阈值
    bomb_count = round(breakdown.get('bombs', 0) / 12.0)
    if breakdown.get('rocket', 0) >= 30:
        effective += ai_brain.bidding.ROCKET_BONUS
    effective -= (2 - position) * ai_brain.bidding.POSITION_PENALTY / 2
    hand_size = len(cards)
    if hand_size <= 6:
        effective += (6 - hand_size) * 5.0
    threshold = ai_brain.bidding.GRAB_THRESHOLD if is_grab else ai_brain.bidding.BID_THRESHOLD

    print(f'  +-- 叫地主决策:')
    print(f'  |    position={position}, is_grab={is_grab}')
    print(f'  |    有效分={effective:.1f}, 阈值={threshold:.1f}')
    print(f'  |    结果: {"[V] " + bid_text if bid else "[X] 不叫"}')
    if bomb_count >= 2:
        print(f'  |    炸弹检测: {bomb_count}个炸弹, 自动叫地主')

    # 推荐领出（假设是自己先出）
    players = [DummyPlayer(hand_pokers, 0, 0)]
    for j in range(1, 3):
        other_hand = list(range(1 + j, 55, 3))[:17]
        players.append(DummyPlayer(other_hand, j, 0))
    players[0].landlord = 0
    room = DummyRoom(players)

    lead = ai_brain.decide_shot(hand_pokers, 0, False, room)
    if lead:
        cards = rule._to_cards(lead)
        ctype, _ = rule._get_cards_value(cards)
        print(f'  +-- 推荐领出: {hand_str(lead)} ({ctype})')
    else:
        print(f'  +-- 推荐领出: pass')


def simulate_one_round(hand0, hand1, hand2, ai_brain, landlord_seat):
    """模拟一轮出牌：地主领出 -> 农民1跟 -> 农民2跟"""
    players = [
        DummyPlayer(hand0[:], 0, 1 if landlord_seat == 0 else 0, '地主' if landlord_seat == 0 else '农民1'),
        DummyPlayer(hand1[:], 1, 1 if landlord_seat == 1 else 0, '地主' if landlord_seat == 1 else '农民2'),
        DummyPlayer(hand2[:], 2, 1 if landlord_seat == 2 else 0, '地主' if landlord_seat == 2 else '农民3'),
    ]
    room = DummyRoom(players)
    ai_brain.memory.reset()

    print(f'\n{"=" * 65}')
    print(f'[出牌模拟] 地主=玩家{landlord_seat}')
    print(f'{"=" * 65}')

    current_seat = landlord_seat
    last_shot = []
    last_shooter = -1
    pass_count = 0

    # 最多模拟 8 轮出牌，避免死循环
    for turn in range(8):
        p = players[current_seat]
        is_landlord = (p.landlord == 1)

        # 检查是否能一手出完（终局检查）
        hand_cards_tmp = rule._to_cards(p.hand_pokers)
        one_shot = rule._find_one_shot(hand_cards_tmp)
        if one_shot:
            print(f'\n  *** 玩家{current_seat}({p.name}) 一手出完!')
            print(f'    牌: {hand_str(p.hand_pokers)}')
            break

        print(f'\n  第{turn+1}轮  -- 轮到 玩家{current_seat}({p.name}) --')
        print(f'    手牌({len(p.hand_pokers)}张): {hand_str(p.hand_pokers)}')
        print(f'    牌面: {card_list_str(rule._to_cards(p.hand_pokers))}')

        if last_shot and last_shooter != current_seat:
            # 跟牌
            turn_pokers = last_shot
            turn_cards_ = rule._to_cards(turn_pokers)
            turn_type, turn_val = rule._get_cards_value(turn_cards_)
            is_ally = (players[last_shooter].landlord == p.landlord)
            print(f'    对手: 玩家{last_shooter} 出了 {shot_info(turn_pokers)}')
            print(f'    关系: {"队友" if is_ally else "对手"}')

            if is_ally:
                # 显示跟队友逻辑
                follow = ai_brain.following.choose_follow(
                    p.hand_pokers, turn_pokers, is_ally, is_landlord,
                    len(players[last_shooter].hand_pokers), players, current_seat
                )
                if follow:
                    print(f'    => 跟牌(队友): {hand_str(follow)} ({shot_info(follow)})')
                    # 更新状态
                    for pk in follow:
                        p.hand_pokers.remove(pk)
                    last_shot = follow
                    last_shooter = current_seat
                else:
                    print(f'    => pass (不压队友)')
                    pass_count += 1
            else:
                follow = ai_brain.following.choose_follow(
                    p.hand_pokers, turn_pokers, is_ally, is_landlord,
                    len(players[last_shooter].hand_pokers), players, current_seat
                )
                if follow:
                    print(f'    => 压牌: {hand_str(follow)} ({shot_info(follow)})')
                    for pk in follow:
                        p.hand_pokers.remove(pk)
                    last_shot = follow
                    last_shooter = current_seat
                else:
                    print(f'    => pass')
                    pass_count += 1
        else:
            # 领出
            lead = ai_brain.decide_shot(p.hand_pokers, current_seat, is_landlord, room)
            if lead:
                lead_cards = rule._to_cards(lead)
                lead_type, _ = rule._get_cards_value(lead_cards)
                print(f'    => 领出: {hand_str(lead)} ({lead_type})')
                for pk in lead:
                    p.hand_pokers.remove(pk)
                last_shot = lead
                last_shooter = current_seat
                room.last_shot_poker = lead
                room.last_shot_seat = current_seat
                pass_count = 0
            else:
                print(f'    => pass (领出为pass:异常)')
                pass_count += 1

        # 更新 AI 记忆
        if last_shot and current_seat == last_shooter:
            ai_brain.memory.record_shot(last_shot)

        # 检查是否手上没牌了
        if not p.hand_pokers:
            print(f'\n  *** 玩家{current_seat}({p.name}) 出完所有牌! 胜利!')
            break

        # 连续三人 pass -> 换领出
        if pass_count >= 2:
            pass_count = 0
            last_shot = []
            last_shooter = -1
            print(f'    [三人均pass, 换领出]')
            continue

        # 下一位
        current_seat = (current_seat + 1) % 3

    # 打印剩余的牌
    print(f'\n{"=" * 65}')
    print('[剩余手牌]')
    for i in range(3):
        if players[i].hand_pokers:
            print(f'  玩家{i}({players[i].name}): {hand_str(players[i].hand_pokers)}')
        else:
            print(f'  玩家{i}({players[i].name}): 已出完')


# ============================================================
# 主程序
# ============================================================

def main():
    random.seed()
    evaluator = HandEvaluator()
    ai_brain = AIBrain()

    # 发牌
    pokers = list(range(1, 55))
    random.shuffle(pokers)
    hands = [
        sorted(pokers[0:17]),
        sorted(pokers[17:34]),
        sorted(pokers[34:51]),
    ]
    bottom = sorted(pokers[51:54])

    print('=' * 65)
    print('                斗地主 AI 调试工具')
    print('=' * 65)
    print(f'\n底牌(3张): {hand_str(bottom)}  牌面: {card_list_str(rule._to_cards(bottom))}\n')

    # ============================================================
    # 第一部分：叫地主分析
    # ============================================================
    print('-' * 30 + ' 叫地主分析 ' + '-' * 30)

    for i in range(3):
        print_hand_analysis(hands[i], f'++ 玩家{i}', ai_brain, i, is_grab=False)
        print()

    # 叫地主结果模拟
    print('-' * 30 + ' 叫地主结果模拟 ' + '-' * 30)
    print()
    print('按新叫地主规则模拟（最多4轮）:\n')

    first_bidder = -1
    bid_history = []
    current = 0  # start from player 0

    for step in range(4):
        # 重置 AI 状态（clean state for each decision）
        ai_tmp = AIBrain()
        pos = (current - 0) % 3

        # 判断是否为抢地主
        is_grab = first_bidder != -1

        bid = ai_tmp.decide_bid(hands[current], pos, is_grab)
        status = f'[V] 叫/抢' if bid else '[X] 不叫'
        print(f'  第{step+1}轮: 玩家{current}  {"(抢地主)" if is_grab else "(叫地主)"}  {status}')

        if bid:
            bid_history.append(current)
            if first_bidder == -1:
                first_bidder = current

        # 检查结束条件
        if step < 3 and first_bidder == -1 and step == 2:
            print(f'\n  => 三人都不叫, 重新发牌')
            break

        if bid == 0 and first_bidder != -1:
            landlord = bid_history[-1]
            print(f'\n  => 地主: 玩家{landlord} (最后一个叫/抢的人)')
            break

        if step == 3:
            print(f'\n  => 地主: 玩家{first_bidder} (四次抢地主, 第一个叫的人)')
            break

        current = (current + 1) % 3

    # ============================================================
    # 第二部分：跟牌分析
    # ============================================================
    print(f'\n\n')
    print('-' * 30 + ' 跟牌分析 ' + '-' * 30)

    # 模拟多种跟牌场景
    print('\n场景: 玩家0出一张 3 单牌, 分析玩家1如何跟牌')
    single_3 = rule._to_pokers(hands[0], ['3'])
    if single_3:
        turn_cards = rule._to_cards(single_3)
        turn_type, turn_val = rule._get_cards_value(turn_cards)
        print(f'  上家出: 3 (single, val={turn_val})')

        # 玩家1是队友的情况
        players_ally = [
            DummyPlayer(hands[0], 0, 1, '地主'),
            DummyPlayer(hands[1], 1, 0, '农民'),
            DummyPlayer(hands[2], 2, 0, '农民'),
        ]
        room_ally = DummyRoom(players_ally)

        follow_ally = ai_brain.following.choose_follow(
            hands[1], single_3, True, False,
            len(players_ally[0].hand_pokers), players_ally, 1
        )
        if follow_ally:
            print(f'  玩家1(与上家是队友): => 跟 {hand_str(follow_ally)} ({shot_info(follow_ally)})')
        else:
            print(f'  玩家1(与上家是队友): => pass')

        # 玩家1是对手的情况
        follow_enemy = ai_brain.following.choose_follow(
            hands[1], single_3, False, False,
            len(players_ally[0].hand_pokers), players_ally, 1
        )
        if follow_enemy:
            print(f'  玩家1(与上家是对手): => 压 {hand_str(follow_enemy)} ({shot_info(follow_enemy)})')
        else:
            print(f'  玩家1(与上家是对手): => pass')

    # ============================================================
    # 第三部分：完整一轮出牌模拟
    # ============================================================
    print(f'\n\n')
    print('-' * 30 + ' 出牌模拟 ' + '-' * 30)
    simulate_one_round(hands[0][:], hands[1][:], hands[2][:], AIBrain(), 0)

    print(f'\n\n')
    print('=' * 65)
    print('调试完成')
    print('=' * 65)


if __name__ == '__main__':
    main()
