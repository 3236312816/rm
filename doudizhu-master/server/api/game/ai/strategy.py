"""
AI 出牌策略模块
包含叫地主、出牌、跟牌、终局四个策略类。
"""

import logging
from typing import List, Optional, Tuple

from ..rule import rule, Rule
from .evaluator import HandEvaluator
from .memory import CardMemory

logger = logging.getLogger(__file__)


# ============================================================
# 1. 叫地主策略
# ============================================================

class BiddingStrategy:
    """
    叫地主策略：基于手牌综合评分 + 位置调整。
    不再简单检查 4/6 张特定牌。
    """

    BID_THRESHOLD = 14.0       # 基础叫地主阈值（原35太高）
    GRAB_THRESHOLD = 8.0       # 抢地主阈值（更低，鼓励抢）
    POSITION_PENALTY = 2.0     # 先叫扣分（原5.0）
    ROCKET_BONUS = 10.0        # 有火箭加分
    THREE_BOMBS_AUTO = True    # 3个炸弹自动叫

    def __init__(self, evaluator: HandEvaluator):
        self.evaluator = evaluator

    def should_bid(self, hand_pokers: List[int], position_index: int, is_grab: bool = False) -> bool:
        """
        判断是否叫/抢地主。

        Args:
            hand_pokers: 手牌（整数ID列表）
            position_index: 叫地主顺序（0=先叫, 1=中间, 2=末家）
            is_grab: True=抢地主(更低阈值), False=首次叫地主

        Returns:
            True=叫/抢地主, False=不叫
        """
        hand_cards = rule._to_cards(hand_pokers)
        score, breakdown = self.evaluator.evaluate(hand_cards)

        effective = score

        # 炸弹数量加成：3个以上炸弹必叫
        bomb_count = round(breakdown.get('bombs', 0) / 12.0)
        if bomb_count >= 2 and self.THREE_BOMBS_AUTO:
            logger.info('BID: %d bombs, auto-bid (score=%.1f)', bomb_count, score)
            return True

        # 火箭加成
        if breakdown.get('rocket', 0) >= 30:
            effective += self.ROCKET_BONUS

        # 位置调整：先叫地主需要更好的手牌
        effective -= (2 - position_index) * self.POSITION_PENALTY / 2

        # 手牌最小化加分（牌少更容易赢）
        hand_size = len(hand_cards)
        if hand_size <= 6:
            effective += (6 - hand_size) * 5.0

        # 选择阈值：抢地主使用更低阈值
        threshold = self.GRAB_THRESHOLD if is_grab else self.BID_THRESHOLD

        logger.debug('BID score=%.1f effective=%.1f threshold=%.1f(grab=%s) => %s',
                     score, effective, threshold, is_grab, effective >= threshold)
        return effective >= threshold


# ============================================================
# 2. 主动出牌策略（领出）
# ============================================================

class LeadingStrategy:
    """
    主动出牌策略。
    区分地主和农民角色，考虑终局压力。
    """

    def __init__(self, evaluator: HandEvaluator, memory: CardMemory):
        self.evaluator = evaluator
        self.memory = memory

    def choose_lead(self, hand_pokers: List[int], is_landlord: bool,
                    my_seat: int, players: List) -> List[int]:
        """
        选择领出牌。

        Args:
            hand_pokers: 手牌整数ID列表
            is_landlord: 是否是地主
            my_seat: 自己的座位号
            players: 所有玩家列表

        Returns:
            要出的牌（整数ID列表），空列表表示pass（通常不会）
        """
        hand_cards = rule._to_cards(hand_pokers)
        if not hand_cards:
            return []

        # 优先级1：一手出完
        one_shot = rule._find_one_shot(hand_cards)
        if one_shot:
            logger.info('  -> 策略: 一手出完 %s', ''.join(one_shot))
            return rule._to_pokers(hand_pokers, one_shot)

        # 优先级1b：降维打击 special combos
        if all(c in hand_cards for c in Rule.ZMJJKK_CARDS):
            logger.info('  -> 策略: 领出 zmjjkk!')
            return rule._to_pokers(hand_pokers, Rule.ZMJJKK_CARDS)
        if all(c in hand_cards for c in Rule.KSKBL_CARDS):
            logger.info('  -> 策略: 领出 kskbl!')
            return rule._to_pokers(hand_pokers, Rule.KSKBL_CARDS)

        rockets, bombs, big_cards, small_cards = rule._get_basic_cards(hand_cards)

        # 优先级2：终局压力——对手快赢了
        for i, p in enumerate(players):
            if i == my_seat or p is None:
                continue
            p_count = len(p.hand_pokers)
            if 1 <= p_count <= 2 and not self._is_ally(p, players, my_seat):
                logger.info('  -> 策略: 终局阻断 (对手剩%d张)', p_count)
                return self._endgame_block(hand_pokers, hand_cards, big_cards, small_cards, bombs)

        # 优先级3：农民特殊组合领出（仅人类是地主时可用，趣味彩蛋）
        if not is_landlord and players and players[0].landlord == 1:
            for spec_name, spec_cards in [('7k7k', '77KK'), ('AK47', '47KA')]:
                spec_list = list(spec_cards)
                if rule.is_contains(hand_cards, spec_list):
                    logger.info('  -> 策略: 农民特殊组合领出 %s', spec_name)
                    return rule._to_pokers(hand_pokers, spec_list)

        # 按角色选择不同策略
        if is_landlord:
            logger.info('  -> 策略: 地主领出')
            return self._landlord_lead(hand_pokers, hand_cards, rockets, bombs, big_cards, small_cards)
        else:
            logger.info('  -> 策略: 农民领出')
            return self._farmer_lead(hand_pokers, hand_cards, rockets, bombs, big_cards, small_cards)

    def _is_ally(self, player, players, my_seat):
        """判断是否为队友（都是农民则互为队友）"""
        my_landlord = players[my_seat].landlord
        return player.landlord == my_landlord

    def _endgame_block(self, hand_pokers, hand_cards, big_cards, small_cards, bombs):
        """终局阻断：对手快赢时出最大牌拦截"""
        if big_cards:
            # 出最大的单牌
            biggest = max(big_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            return rule._to_pokers(hand_pokers, biggest)
        if bombs:
            return rule._to_pokers(hand_pokers, bombs[0])
        if small_cards:
            return rule._to_pokers(hand_pokers, small_cards[-1])
        return rule._to_pokers(hand_pokers, hand_cards[-1])

    def _landlord_lead(self, hand_pokers, hand_cards, rockets, bombs, big_cards, small_cards):
        """地主领出策略：清小牌 -> 保持控制"""
        total_single = rule.get_single_no(hand_cards)

        # 1. 尝试长顺子清牌
        best_seq, seq_left = rule._find_best_seq(small_cards)
        if best_seq:
            return rule._to_pokers(hand_pokers, best_seq[0])

        # 2. 三带一（用孤立单牌当踢脚）
        if total_single >= 1:
            shot = rule._find_spec_shot(small_cards, ['trio_single'], total_single - 1)
            if shot:
                return rule._to_pokers(hand_pokers, shot)

        # 3. 出单牌回手，优先选不成对的孤立单牌
        if small_cards:
            real_singles = [c for c in small_cards if small_cards.count(c) == 1]
            if real_singles:
                idx = min(len(real_singles) - 1, max(0, len(real_singles) // 3))
                return rule._to_pokers(hand_pokers, real_singles[idx])
            # 所有小牌都成对 → 出最小对子，不拆对
            pair_cards = [c for c in small_cards if small_cards.count(c) >= 2]
            if pair_cards:
                unique_pairs = list(set(pair_cards))
                unique_pairs.sort(key=lambda c: '34567890JQKA2wW'.index(c))
                return rule._to_pokers(hand_pokers, unique_pairs[0] * 2)

        # 4. 出对子
        if small_cards:
            pair_cards = [c for c in small_cards if len([x for x in small_cards if x == c]) >= 2]
            if pair_cards:
                unique_pairs = list(set(pair_cards))
                unique_pairs.sort(key=lambda c: '34567890JQKA2wW'.index(c))
                return rule._to_pokers(hand_pokers, unique_pairs[0] * 2)

        # 5. 有小牌出最小的单张，不拆炸弹
        if small_cards:
            return rule._to_pokers(hand_pokers, small_cards[0])
        if big_cards:
            biggest = max(big_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            return rule._to_pokers(hand_pokers, biggest)
        # 6. 退化为原来的 find_best_shot（极少数情况）
        return rule.find_best_shot(hand_pokers)

    def _farmer_lead(self, hand_pokers, hand_cards, rockets, bombs, big_cards, small_cards):
        """农民领出策略：打地主难跟的组合，保留大牌"""
        total_single = rule.get_single_no(hand_cards)

        # 1. 出中等长度顺子（仅从小牌中找，不拆炸弹/火箭）
        for seq_len in (8, 7, 6, 5):
            seq_spec = f'seq_single{seq_len}'
            if seq_spec in rule.rules:
                seqs, _ = rule._find_spec_type(small_cards, seq_spec)
                if seqs:
                    for s in seqs:
                        last_rank = s[-1]
                        if last_rank in 'JQKA':
                            return rule._to_pokers(hand_pokers, s)
                    return rule._to_pokers(hand_pokers, seqs[0])

        # 2. 三带对（强力但不过分）
        shot = rule._find_spec_shot(small_cards, ['trio_pair'], total_single)
        if shot:
            return rule._to_pokers(hand_pokers, shot)

        # 3. 出中等单牌（测试地主），优先选不成对的孤立单牌
        if small_cards:
            real_singles = [c for c in small_cards if small_cards.count(c) == 1]
            if real_singles:
                idx = min(len(real_singles) - 1, 2)
                return rule._to_pokers(hand_pokers, real_singles[idx])
            # 所有小牌都成对 → 出最小对子，不拆对
            pair_cards = [c for c in small_cards if small_cards.count(c) >= 2]
            if pair_cards:
                unique_pairs = list(set(pair_cards))
                unique_pairs.sort(key=lambda c: '34567890JQKA2wW'.index(c))
                return rule._to_pokers(hand_pokers, unique_pairs[0] * 2)

        # 4. 出对子（仅从小牌中找，不拆炸弹）
        if small_cards:
            pair_cards = [c for c in small_cards if small_cards.count(c) >= 2]
            if pair_cards:
                unique_pairs = list(set(pair_cards))
                unique_pairs.sort(key=lambda c: '34567890JQKA2wW'.index(c))
                return rule._to_pokers(hand_pokers, unique_pairs[0] * 2)

        # 5. 无小牌可出时，使用大牌
        if big_cards:
            pair_cards = [c for c in big_cards if big_cards.count(c) >= 2]
            if pair_cards:
                unique_pairs = list(set(pair_cards))
                unique_pairs.sort(key=lambda c: '34567890JQKA2wW'.index(c))
                return rule._to_pokers(hand_pokers, unique_pairs[0] * 2)
            # 出最大的单张大牌控制局面
            biggest = max(big_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            return rule._to_pokers(hand_pokers, biggest)

        # 6. 退化为原始策略（极少数情况）
        return rule.find_best_shot(hand_pokers)


# ============================================================
# 3. 跟牌策略
# ============================================================

class FollowingStrategy:
    """
    跟牌策略：根据是对手还是队友，采用不同的成本收益分析。
    """

    def __init__(self, evaluator: HandEvaluator, memory: CardMemory):
        self.evaluator = evaluator
        self.memory = memory

    def choose_follow(self, hand_pokers: List[int], turn_pokers: List[int],
                      is_ally: bool, is_landlord: bool,
                      last_player_size: int, players: List,
                      my_seat: int) -> List[int]:
        """
        选择跟牌。

        Returns:
            要出的牌列表（空列表=不要）
        """
        if not turn_pokers:
            return []

        hand_cards = rule._to_cards(hand_pokers)
        turn_cards = rule._to_cards(turn_pokers)
        turn_type, turn_value = rule._get_cards_value(turn_cards)

        if not turn_type:
            return []

        if turn_type == 'rocket':
            return []  # 火箭无法压制

        # 降维打击 special combos in follow mode (only vs opponent, not ally)
        if not is_ally:
            if all(c in hand_cards for c in Rule.ZMJJKK_CARDS):
                logger.info('  -> 策略: 跟牌 zmjjkk!')
                return rule._to_pokers(hand_pokers, Rule.ZMJJKK_CARDS)
            if all(c in hand_cards for c in Rule.ZDJD_CARDS):
                if turn_value < 36000:
                    logger.info('  -> 策略: 跟牌 zdjd!')
                    return rule._to_pokers(hand_pokers, Rule.ZDJD_CARDS)
            if all(c in hand_cards for c in Rule.KSKBL_CARDS):
                if turn_value < 35000:
                    logger.info('  -> 策略: 跟牌 kskbl!')
                    return rule._to_pokers(hand_pokers, Rule.KSKBL_CARDS)

        if is_ally:
            return self._follow_ally(hand_pokers, hand_cards, turn_cards,
                                     turn_type, turn_value, last_player_size)
        else:
            return self._follow_enemy(hand_pokers, hand_cards, turn_cards,
                                      turn_type, turn_value, last_player_size,
                                      is_landlord, players, my_seat)

    def _follow_ally(self, hand_pokers, hand_cards, turn_cards,
                     turn_type, turn_value, ally_size):
        """跟队友：允许用小牌接队友出的小牌，但不使用炸弹"""
        rockets, bombs, big_cards, small_cards = rule._get_basic_cards(hand_cards)

        # 队友快赢了（1-2张）→ 绝不出
        if ally_size <= 2:
            logger.info('  -> 跟队友: 队友快赢(剩%d张), pass', ally_size)
            return []

        # 队友剩3-5张，仅当能一手赢时才出
        if ally_size <= 5:
            beater = self._find_minimal_beater(small_cards, turn_type, turn_value)
            if beater:
                left = rule.minus(small_cards, beater)
                if rule._find_one_shot(left):
                    logger.info('  -> 跟队友: 队友剩%d张, 能一手赢, 接牌', ally_size)
                    return rule._to_pokers(hand_pokers, beater)
            logger.info('  -> 跟队友: 队友剩%d张, 自己不能一手赢, pass', ally_size)
            return []

        # 自己手牌很弱且队友还有不少牌 → 保存实力
        if not big_cards and len(hand_cards) > ally_size * 2 + 3:
            logger.info('  -> 跟队友: 手牌弱(%d张), 保存实力, pass', len(hand_cards))
            return []

        total_single = rule.get_single_no(hand_cards)
        best_beater = None
        best_reduction = 0

        if turn_type in rule.rules:
            # 优先级1：找能减少孤立单牌的最小跟牌（仅从 small_cards 中找，不拆炸弹）
            for i, spec in enumerate(rule.rules[turn_type]):
                if i <= turn_value or not rule.is_contains(small_cards, spec):
                    continue
                test_type, _ = rule._get_cards_value(list(spec))
                if test_type in ('bomb', 'rocket'):
                    continue
                left = rule.minus(small_cards, spec)
                reduction = total_single - rule.get_single_no(left)
                if reduction > best_reduction:
                    best_reduction = reduction
                    best_beater = spec

            if best_beater and best_reduction > 0:
                logger.info('  -> 跟队友: 减少孤立单牌(%d→%d), 接牌',
                            total_single, total_single - best_reduction)
                return rule._to_pokers(hand_pokers, best_beater)

            # 优先级2：队友出小牌时用稍大的牌接过来继续打（不拆炸弹）
            max_rank = max(turn_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            if max_rank in '34567890J':  # 队友出 <= J 的小牌
                for i, spec in enumerate(rule.rules[turn_type]):
                    if i <= turn_value or not rule.is_contains(small_cards, spec):
                        continue
                    test_type, _ = rule._get_cards_value(list(spec))
                    if test_type in ('bomb', 'rocket'):
                        continue
                    # 只接稍大一点点的（差值 <= 3 个 rank）
                    if i - turn_value <= 3:
                        logger.info('  -> 跟队友: 队友出小牌(%s), 接牌(+%d rank)',
                                    max_rank, i - turn_value)
                        return rule._to_pokers(hand_pokers, spec)
                    break  # 最小能压的牌差距太大，不接

        logger.info('  -> 跟队友: 没有合适的牌, pass')
        return []  # 默认不出，让队友继续

    def _follow_enemy(self, hand_pokers, hand_cards, turn_cards,
                      turn_type, turn_value, enemy_size,
                      is_landlord, players, my_seat):
        """跟敌人（地主或对方农民）：成本收益分析"""
        rockets, bombs, big_cards, small_cards = rule._get_basic_cards(hand_cards)
        my_size = len(hand_cards)

        # ---- 优先级1：敌人快赢，不惜代价拦截 ----
        # 先用非炸弹牌拦截（从 small_cards 中找最小能压的），拦截失败再用炸弹
        if enemy_size <= 2:
            blocker = self._find_minimal_beater(small_cards, turn_type, turn_value)
            if blocker:
                logger.info('  -> 跟对手: 敌人快赢(%d张), 最小拦截', enemy_size)
                return rule._to_pokers(hand_pokers, blocker)
            if bombs:
                logger.info('  -> 跟对手: 敌人快赢(%d张), 用炸弹拦截', enemy_size)
                return rule._to_pokers(hand_pokers, bombs[0])
            if rockets:
                logger.info('  -> 跟对手: 敌人快赢(%d张), 用火箭', enemy_size)
                return rule._to_pokers(hand_pokers, rockets[0])
            if big_cards:
                result = rule._to_pokers(hand_pokers, big_cards[-1])
                # 验证回退牌是否真能压过上家（特殊组合不在 rule.rules 中时，
                # 单张大牌可能压不住，需过滤）
                if rule.compare_pokers(result, turn_pokers) > 0:
                    return result
            return []

        # ---- 优先级2：自己接近胜利，推进 ----
        if my_size <= 5:
            blocker = self._find_minimal_beater(small_cards, turn_type, turn_value)
            if blocker:
                left = rule.minus(small_cards, blocker)
                if rule._find_one_shot(left):
                    logger.info('  -> 跟对手: 自己接近胜利(%d张), 推进', my_size)
                    return rule._to_pokers(hand_pokers, blocker)
            # 用炸弹抢牌权
            if bombs and my_size <= 6:
                logger.info('  -> 跟对手: 自己剩%d张, 用炸弹抢牌权', my_size)
                return rule._to_pokers(hand_pokers, bombs[0])

        # ---- 优先级2.5：敌人剩3-4张，危险局面，有牌就压 ----
        if enemy_size <= 4:
            non_bomb = self._find_non_bomb_beater(small_cards, turn_type, turn_value, big_cards)
            if non_bomb:
                logger.info('  -> 跟对手: 敌人剩%d张, 危险! 有牌就压', enemy_size)
                return rule._to_pokers(hand_pokers, non_bomb)
            # 没有非炸弹能压的, 看炸弹
            if bombs:
                logger.info('  -> 跟对手: 敌人剩%d张, 用炸弹拦截', enemy_size)
                return rule._to_pokers(hand_pokers, bombs[0])
            if rockets:
                logger.info('  -> 跟对手: 敌人剩%d张, 用火箭', enemy_size)
                return rule._to_pokers(hand_pokers, rockets[0])

        # ---- 优先级2.7：特殊组合压制敌人（_follow_enemy 只会被敌人场景调用）----
        # zdjd(36000) — 所有角色可用
        if all(c in hand_cards for c in Rule.ZDJD_CARDS) and turn_value < 36000:
            logger.info('  -> 跟对手: 用 zdjd 压制')
            return rule._to_pokers(hand_pokers, Rule.ZDJD_CARDS)
        # 7k7k(37000), AK47(39000) — 仅农民压制地主时用
        if not is_landlord and players and players[0].landlord == 1:
                for spec_name, spec_cards, spec_value in [
                    ('7k7k', '77KK', 37000),
                    ('AK47', '47KA', 39000),
                ]:
                    if spec_value > turn_value:
                        spec_list = list(spec_cards)
                        if rule.is_contains(hand_cards, spec_list):
                            logger.info('  -> 跟对手(农民特殊组合): 用%s', spec_name)
                            return rule._to_pokers(hand_pokers, spec_list)

        # ---- 优先级3：常规跟牌，成本收益分析 ----
        # 非炸弹跟（从 small_cards 中找，不拆炸弹）
        non_bomb = self._find_non_bomb_beater(small_cards, turn_type, turn_value, big_cards)
        if non_bomb:
            trial_left = rule.minus(hand_cards, non_bomb)
            cur_singles = rule.get_single_no(hand_cards)
            after_singles = rule.get_single_no(trial_left)

            # 获取对手出牌的最大面值
            max_rank = max(turn_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            beater_max = max(non_bomb, key=lambda c: '34567890JQKA2wW'.index(c))

            # 条件A：对手出小牌（≤J），且自己能压的牌也不大（≤A），值得跟
            if max_rank in '34567890J' and beater_max in '34567890JQKA':
                logger.info('  -> 跟对手: 对方出小牌(%s), 用%s压', max_rank, beater_max)
                return rule._to_pokers(hand_pokers, non_bomb)

            # 条件B：如果能减少单牌，值得跟
            if after_singles < cur_singles:
                logger.info('  -> 跟对手: 减少单牌(%d→%d)', cur_singles, after_singles)
                return rule._to_pokers(hand_pokers, non_bomb)
            # 条件C：如果有很多大牌可消耗，值得跟
            if len(big_cards) >= 2:
                logger.info('  -> 跟对手: 大牌多(%d张), 消耗', len(big_cards))
                return rule._to_pokers(hand_pokers, non_bomb)
            # 条件D：如果对方出的牌价值不高（面值小），值得跟
            if max_rank in '34567890J':
                logger.info('  -> 跟对手: 对方出小牌(%s), 接', max_rank)
                return rule._to_pokers(hand_pokers, non_bomb)

        # ---- 优先级3.5：农民配合压制地主（成本收益不满足时仍尝试配合） ----
        if not is_landlord and non_bomb:
            trial_left = rule.minus(hand_cards, non_bomb)
            cur_singles = rule.get_single_no(hand_cards)
            after_singles = rule.get_single_no(trial_left)
            beater_max = max(non_bomb, key=lambda c: '34567890JQKA2wW'.index(c))
            # 农民合作原则：
            #   - 不用2和王来压普通牌（保留关键资源）
            #   - 不破坏牌型（不出完牌时增加≤1个孤立单牌）
            #   - 地主快赢时（剩≤6张），放宽限制，尽量拦截
            if beater_max not in '2wW':
                allow_block = (after_singles <= cur_singles + 1) or (enemy_size <= 6)
                if allow_block:
                    reason = '敌危(%d张)' % enemy_size if enemy_size <= 6 else '护牌型'
                    logger.info('  -> 跟对手(农民配合): 用%s压地主(%s)', beater_max, reason)
                    return rule._to_pokers(hand_pokers, non_bomb)

        # ---- 优先级4：炸弹使用评估 ----
        if bombs:
            # 对方牌数 <=8 说明威胁较大，值得用炸弹
            if enemy_size <= 8:
                logger.info('  -> 跟对手: 对方剩%d张, 用炸弹', enemy_size)
                return rule._to_pokers(hand_pokers, bombs[0])
            # 自己牌较少（可回收牌权）
            if my_size <= 10:
                logger.info('  -> 跟对手: 自己剩%d张, 用炸弹抢牌权', my_size)
                return rule._to_pokers(hand_pokers, bombs[0])

        # ---- 优先级5：火箭极度保守 ----
        if rockets:
            trial_left = rule.minus(hand_cards, rockets[0])
            if rule._find_one_shot(trial_left):
                logger.info('  -> 跟对手: 用火箭可一手赢')
                return rule._to_pokers(hand_pokers, rockets[0])

        logger.info('  -> 跟对手: 无合适牌, pass')
        return []  # 不要

    def _find_minimal_beater(self, small_cards: List[str], turn_type: str, turn_value: int) -> Optional[str]:
        """找到能压住对方的最小车牌组合（非炸弹），从 small_cards 中找，不拆炸弹"""
        if turn_type not in rule.rules:
            return None
        for i, spec in enumerate(rule.rules[turn_type]):
            if i > turn_value and rule.is_contains(small_cards, spec):
                test_type, _ = rule._get_cards_value(list(spec))
                if test_type not in ('bomb', 'rocket'):
                    return spec
        return None

    def _find_non_bomb_beater(self, small_cards: List[str], turn_type: str,
                               turn_value: int, big_cards: List[str]) -> Optional[str]:
        """在指定牌池中找到非炸弹的压制组合（从 small_cards 中找，不拆炸弹）"""
        if turn_type not in rule.rules:
            return None
        # 先在大牌中搜索，再从小牌中搜索（均不包含炸弹/火箭）
        for cards in (big_cards, small_cards):
            for i, spec in enumerate(rule.rules[turn_type]):
                if i > turn_value and rule.is_contains(cards, spec):
                    test_type, _ = rule._get_cards_value(list(spec))
                    if test_type not in ('bomb', 'rocket'):
                        return spec
        return None


# ============================================================
# 4. 终局策略
# ============================================================

class EndgameStrategy:
    """
    终局策略：在所有正常策略前检查特殊终局条件。
    返回 None 表示不需要终局覆盖，交由正常策略处理。
    """

    def __init__(self, memory: CardMemory):
        self.memory = memory

    def check_endgame(self, hand_pokers: List[int], my_seat: int,
                      players: List, last_shot: List[int] = None,
                      last_shot_seat: int = -1) -> Optional[List[int]]:
        """
        检查终局条件。如果命中，返回要出的牌；否则返回 None。

        Args:
            last_shot: 当前桌面的出牌（用于跟牌场景）
            last_shot_seat: 最后出牌的玩家座位

        Returns:
            List[int] = 覆盖出牌，None = 继续正常策略
        """
        hand_cards = rule._to_cards(hand_pokers)
        if not hand_cards:
            return []

        # 条件0：降维打击 special combos — 有就出（按值从高到低检查，出最强的）
        if all(c in hand_cards for c in Rule.ZMJJKK_CARDS):
            result_pokers = rule._to_pokers(hand_pokers, Rule.ZMJJKK_CARDS)
            if last_shot and last_shot_seat != my_seat:
                if rule.compare_pokers(result_pokers, last_shot) < 0:
                    logger.info('  -> [终局] 有zmjjkk但压不过上家')
                    return None
            logger.info('  -> [终局] 出 zmjjkk!')
            return result_pokers
        # zdjd(36000) - 终局可用
        if all(c in hand_cards for c in Rule.ZDJD_CARDS):
            result_pokers = rule._to_pokers(hand_pokers, Rule.ZDJD_CARDS)
            if last_shot and last_shot_seat != my_seat:
                last_cards = rule._to_cards(last_shot)
                _, last_value = rule._get_cards_value(last_cards)
                if last_value >= 36000:
                    return None
            logger.info('  -> [终局] 出 zdjd!')
            return result_pokers
        if all(c in hand_cards for c in Rule.KSKBL_CARDS):
            if last_shot and last_shot_seat != my_seat:
                last_cards = rule._to_cards(last_shot)
                _, last_value = rule._get_cards_value(last_cards)
                if last_value >= 35000:
                    return None
            result_pokers = rule._to_pokers(hand_pokers, Rule.KSKBL_CARDS)
            logger.info('  -> [终局] 出 kskbl!')
            return result_pokers

        # 条件1：能一手赢
        one_shot = rule._find_one_shot(hand_cards)
        if one_shot:
            result_pokers = rule._to_pokers(hand_pokers, one_shot)
            # 如果是跟牌场景，必须能压过上家的牌
            if last_shot and last_shot_seat != my_seat:
                if rule.compare_pokers(result_pokers, last_shot) < 0:
                    logger.info('  -> [终局] 能一手出完 %s, 但压不过上家, pass',
                                ''.join(one_shot))
                    return None  # 不能压过，不覆盖
            logger.info('  -> [终局] 能一手出完: %s', ''.join(one_shot))
            return result_pokers

        # 条件2：对手快要赢了（剩1-2张）
        for i, p in enumerate(players):
            if i == my_seat or p is None:
                continue
            p_count = len(p.hand_pokers)
            if 1 <= p_count <= 2:
                # 判断是敌是友
                is_ally = (p.landlord == players[my_seat].landlord)
                if not is_ally:
                    # 敌人快赢，需要阻断
                    logger.info('  -> [终局] 敌人(玩家%d)剩%d张, 阻断!', i, p_count)
                    result = self._block_enemy(hand_pokers, hand_cards, last_shot, last_shot_seat, my_seat)
                    if result:
                        return result
                    logger.info('  -> [终局] 无法阻断, pass')
                else:
                    logger.info('  -> [终局] 队友(玩家%d)剩%d张, 不出', i, p_count)

        return None

    def _block_enemy(self, hand_pokers, hand_cards, last_shot=None, last_shot_seat=-1, my_seat=-1):
        """阻断敌人：出最大牌或炸弹，必须能压过上家"""
        rockets, bombs, big_cards, small_cards = rule._get_basic_cards(hand_cards)

        # 如果大牌中有能单出的，出最大的（需验证能压过上家）
        for rank in reversed('wW2A'):
            if rank in hand_cards:
                if hand_cards.count(rank) == 1 and rank not in 'wW':
                    candidate = rule._to_pokers(hand_pokers, [rank])
                    if last_shot and last_shot_seat != my_seat:
                        if rule.compare_pokers(candidate, last_shot) < 0:
                            continue  # 压不过，试下一张
                    return candidate
                if rank in 'wW':
                    candidate = rule._to_pokers(hand_pokers, [rank])
                    if last_shot and last_shot_seat != my_seat:
                        if rule.compare_pokers(candidate, last_shot) < 0:
                            continue
                    return candidate

        # 出炸弹（炸弹一定能压过非炸弹）
        if bombs:
            # 如果上家出的是火箭，炸弹也压不过
            if last_shot and last_shot_seat != my_seat:
                last_cards = rule._to_cards(last_shot)
                last_type, _ = rule._get_cards_value(last_cards)
                if last_type == 'rocket':
                    return None
            return rule._to_pokers(hand_pokers, bombs[0])

        if big_cards:
            biggest = max(big_cards, key=lambda c: '34567890JQKA2wW'.index(c))
            candidate = rule._to_pokers(hand_pokers, biggest)
            if last_shot and last_shot_seat != my_seat:
                if rule.compare_pokers(candidate, last_shot) < 0:
                    return None  # 最大牌都压不过
            return candidate

        return None
