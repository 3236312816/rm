export class Poker extends Phaser.Sprite {

    static PW = 90;
    static PH = 120;

    // 降维打击 special card constants
    static ZMJJKK_IDS = [101, 102, 103, 104, 105, 106];
    static ZMJJKK_CARDS = ['z', 'm', 'j', 'j', 'k', 'k'];
    static KSKBL_IDS = [107, 108, 109, 110, 111];
    static KSKBL_CARDS = ['k', 's', 'k', 'b', 'l'];
    static ZDJD_IDS = [112, 113, 114, 115];
    static ZDJD_CARDS = ['z', 'd', 'j', 'd'];

    // Custom image texture mapping for special cards
    static TEXTURE_MAP = {
        101: 'card_z', 102: 'card_m', 103: 'card_j1', 104: 'card_j2',
        105: 'card_k1', 106: 'card_k2',
        107: 'card_k3', 108: 'card_s', 109: 'card_k4', 110: 'card_b', 111: 'card_l',
        112: 'card_z2', 113: 'card_d1', 114: 'card_j4', 115: 'card_d2',
    };

    static isSpecialId(id) {
        return id >= 101 && id <= 115;
    }

    constructor(game, id, frame) {
        if (id > 54) {
            // Special cards use custom image textures
            const textureKey = Poker.TEXTURE_MAP[id] || '__default';
            super(game, game.world.width / 2, game.world.height * 0.4, textureKey);
            this.width = Poker.PW;
            this.height = Poker.PH;
        } else {
            super(game, game.world.width / 2, game.world.height * 0.4, 'poker', frame - 1);
        }
        this.anchor.set(0.5);
        this.id = id;
    }

    static comparePoker(a, b) {
        if (a instanceof Array) {
            a = a[0];
            b = b[0];
        }
        // Special cards sorted by their ID (101-111 in combo order)
        if (Poker.isSpecialId(a) && Poker.isSpecialId(b)) {
            return a - b;
        }
        if (Poker.isSpecialId(a)) return 1;
        if (Poker.isSpecialId(b)) return -1;
        if (a > 52 || b > 52) {
            return -(a - b);
        }
        a = a % 13;
        b = b % 13;
        if (a <= 2) {
            a += 13;
        }
        if (b <= 2) {
            b += 13;
        }
        return -(a - b);
    }

    static toCards(pokers) {
        let cards = [];
        for (let i = 0; i < pokers.length; i++) {
            let pid = pokers[i];
            if (pid instanceof Array) {
                pid = pid[0];
            }
            if (pid === 53) {
                cards.push('w');
            } else if (pid === 54) {
                cards.push('W');
            } else if (pid >= 101 && pid <= 106) {
                cards.push(Poker.ZMJJKK_CARDS[pid - 101]);
            } else if (pid >= 107 && pid <= 111) {
                cards.push(Poker.KSKBL_CARDS[pid - 107]);
            } else if (pid >= 112 && pid <= 115) {
                cards.push(Poker.ZDJD_CARDS[pid - 112]);
            } else {
                cards.push("KA234567890JQ"[pid % 13]);
            }
        }
        return cards;
    }

    static canCompare(pokersA, pokersB) {
        let cardsA = this.toCards(pokersA);
        let cardsB = this.toCards(pokersB);
        return cardsValue(cardsA)[0] === cardsValue(cardsB)[0];
    }

    static toPokers(pokerInHands, cards) {
        let cardsList = typeof cards === 'string' ? cards.split('') : cards;

        // Direct mapping for special combos
        const zmjjkkSorted = ['j', 'j', 'k', 'k', 'm', 'z'];
        const kskblSorted = ['b', 'k', 'k', 'l', 's'];
        const zdjdSorted = ['j', 'z', 'd', 'd'];
        const sortedInput = [...cardsList].sort();
        if (JSON.stringify(sortedInput) === JSON.stringify(zmjjkkSorted)) {
            return Poker.ZMJJKK_IDS.filter(id => pokerInHands.indexOf(id) !== -1);
        }
        if (JSON.stringify(sortedInput) === JSON.stringify(kskblSorted)) {
            return Poker.KSKBL_IDS.filter(id => pokerInHands.indexOf(id) !== -1);
        }
        if (JSON.stringify(sortedInput) === JSON.stringify(zdjdSorted)) {
            return Poker.ZDJD_IDS.filter(id => pokerInHands.indexOf(id) !== -1);
        }

        let pokers = [];
        for (let i = 0; i < cardsList.length; i++) {
            let candidates = this.toPoker(cardsList[i]);
            for (let j = 0; j < candidates.length; j++) {
                if (pokerInHands.indexOf(candidates[j]) !== -1 && pokers.indexOf(candidates[j]) === -1) {
                    pokers.push(candidates[j]);
                    break
                }
            }
        }
        return pokers;
    }

    static toPoker(card) {
        // 降维打击 special chars
        if (card === 'z') return [101, 112];  // zmjjkk + zdjd
        if (card === 'm') return [102];
        if (card === 'j') return [103, 104, 114];  // zmjjkk (x2) + zdjd
        if (card === 'k') return [105, 106, 109, 110];  // zmjjkk (x2) + kskbl (x2)
        if (card === 's') return [108];
        if (card === 'b') return [107];
        if (card === 'l') return [111];
        if (card === 'd') return [113, 115];  // zdjd (x2)

        const cards = "?A234567890JQK";
        for (let i = 1; i < cards.length; i++) {
            if (card === cards[i]) {
                return [i, i + 13, i + 26, i + 39];
            }
        }
        if (card === 'w') {
            return [53];
        } else if (card === 'W') {
            return [54];
        }
        return [55];
    }
}

export class Rule {
    static RuleList = []

    static cardsAbove(handCards, turnCards) {

        let turnValue = this.cardsValue(turnCards);
        if (turnValue[0] === '') {
            return '';
        }
        handCards.sort(this.sorter);
        let oneRule = Rule.RuleList[turnValue[0]];
        if (oneRule) {
            for (let i = turnValue[1] + 1; i < oneRule.length; i++) {
                if (this.containsAll(handCards, oneRule[i])) {
                    return oneRule[i];
                }
            }
        }

        // 降维打击: zmjjkk beats everything (最高层级)
        const zmjjkkStr = 'jjkkmz';
        if (this.containsAll(handCards, zmjjkkStr)) {
            return zmjjkkStr;
        }

        // zdjd beats kskbl and bomb/normal types (value < 36000)
        if (turnValue[1] < 36000) {
            const zdjdStr = 'jzdd';
            if (this.containsAll(handCards, zdjdStr)) {
                return zdjdStr;
            }
        }

        // kskbl beats bomb/normal types (value < 35000)
        if (turnValue[1] < 35000) {
            const kskblStr = 'bkkls';
            if (this.containsAll(handCards, kskblStr)) {
                return kskblStr;
            }
        }

        if (turnValue[1] < 30000) {
            oneRule = Rule.RuleList['bomb'];
            for (let i = 0; i < oneRule.length; i++) {
                if (this.containsAll(handCards, oneRule[i])) {
                    return oneRule[i];
                }
            }
            if (this.containsAll(handCards, 'wW')) {
                return 'wW';
            }
        }

        // 特殊组合7k7k(37000)/AK47(39000)可以压值比它们小的
        let specialOrder = ['7k7k', 'AK47'];
        let specialValues = [37000, 39000];
        for (let si = 0; si < specialOrder.length; si++) {
            if (specialValues[si] > turnValue[1]) {
                let specRule = Rule.RuleList[specialOrder[si]];
                if (specRule && this.containsAll(handCards, specRule[0])) {
                    return specRule[0];
                }
            }
        }

        return '';
    }

    static bestShot(handCards) {

        handCards.sort(this.sorter);
        let shot = '';

        // 优先检查特殊组合（7k7k, AK47, zmjjkk, kskbl）→ 只要手上有就提示
        let specialTypes = ['7k7k', 'AK47'];
        for (let si = 0; si < specialTypes.length; si++) {
            let specRule = Rule.RuleList[specialTypes[si]];
            if (specRule && this.containsAll(handCards, specRule[0])) {
                return specRule[0];
            }
        }
        // 降维打击 combos
        const zmjjkkStr = 'jjkkmz';
        if (this.containsAll(handCards, zmjjkkStr)) {
            return zmjjkkStr;
        }
        const zdjdStr = 'jzdd';
        if (this.containsAll(handCards, zdjdStr)) {
            return zdjdStr;
        }
        const kskblStr = 'bkkls';
        if (this.containsAll(handCards, kskblStr)) {
            return kskblStr;
        }

        for (let i = 0; i < this._CardsType.length; i++) {
            let oneRule = Rule.RuleList[this._CardsType[i]];
            if (!oneRule) continue;
            for (let j = 0; j < oneRule.length; j++) {
                if (oneRule[j].length > shot.length && this.containsAll(handCards, oneRule[j])) {
                    shot = oneRule[j];
                }
            }
        }

        if (shot === '') {
            let oneRule = Rule.RuleList['bomb'];
            for (let i = 0; i < oneRule.length; i++) {
                if (this.containsAll(handCards, oneRule[i])) {
                    return oneRule[i];
                }
            }
            if (this.containsAll(handCards, 'wW'))
                return 'wW';
        }

        return shot;
    }

    static _CardsType = [
        'single', 'pair', 'trio', 'trio_pair', 'trio_single',
        'seq_single5', 'seq_single6', 'seq_single7', 'seq_single8', 'seq_single9', 'seq_single10', 'seq_single11', 'seq_single12',
        'seq_pair3', 'seq_pair4', 'seq_pair5', 'seq_pair6', 'seq_pair7', 'seq_pair8', 'seq_pair9', 'seq_pair10',
        'seq_trio2', 'seq_trio3', 'seq_trio4', 'seq_trio5', 'seq_trio6',
        'seq_trio_pair2', 'seq_trio_pair3', 'seq_trio_pair4',
        'seq_trio_single2', 'seq_trio_single3', 'seq_trio_single4', 'seq_trio_single5',
        'bomb_pair', 'bomb_single',
        'bomb', 'rocket',
        '7k7k', 'AK47',
        'zmjjkk', 'zdjd', 'kskbl'];

    static sorter(a, b) {
        let card_str = '34567890JQKA2wWbjklmszd';
        return card_str.indexOf(a) - card_str.indexOf(b);
    }

    static index_of(array, ele) {
        if (array[0].length !== ele.length) {
            return -1;
        }
        for (let i = 0, l = array.length; i < l; i++) {
            if (array[i] === ele) {
                return i;
            }
        }
        return -1;
    }

    static containsAll(parent, child) {
        let index = 0;
        for (let i = 0; i < child.length; i++) {
            index = parent.indexOf(child[i], index);
            if (index === -1) {
                return false;
            }
            index += 1;
        }
        return true;
    }

    static cardsValue(cards) {

        if (typeof (cards) != 'string') {
            cards.sort(this.sorter);
            cards = cards.join('');
        }

        // 降维打击 special combos - 按层级赋值
        // zmjjkk(40000) > AK47(39000) > rocket(38000) > 7k7k(37000) > zdjd(36000) > kskbl(35000) > bomb(30000+)
        if (cards === 'jjkkmz') return ['zmjjkk', 40000];
        let specialTypes = ['AK47', '7k7k'];
        let specialValues = [39000, 37000];
        for (let si = 0; si < specialTypes.length; si++) {
            if (Rule.RuleList[specialTypes[si]] && this.containsAll(cards, Rule.RuleList[specialTypes[si]][0])) {
                return [specialTypes[si], specialValues[si]];
            }
        }
        if (cards === 'wW')
            return ['rocket', 38000];
        if (cards === 'jzdd') return ['zdjd', 36000];
        if (cards === 'bkkls') return ['kskbl', 35000];

        let index = this.index_of(Rule.RuleList['bomb'], cards);
        if (index >= 0)
            return ['bomb', 30000 + index];

        let length = this._CardsType.length;
        for (let i = 0; i < length; i++) {
            let typeName = this._CardsType[i];
            let index = this.index_of(Rule.RuleList[typeName], cards);
            if (index >= 0)
                return [typeName, index];
        }
        console.log('Error: UNKNOWN TYPE ', cards);
        return ['', 0];
    }

    static compare(cardsA, cardsB) {

        if (cardsA.length === 0 && cardsB.length === 0) {
            return 0;
        }
        if (cardsA.length === 0) {
            return -1;
        }
        if (cardsB.length === 0) {
            return 1;
        }

        let valueA = this.cardsValue(cardsA);
        let valueB = this.cardsValue(cardsB);

        if ((valueA[1] < 30000 && valueB[1] < 30000) && (valueA[0] !== valueB[0])) {
            console.log('Error: Compare ', cardsA, cardsB);
        }

        return valueA[1] - valueB[1];
    }

    static shufflePoker() {
        let pokers = [];
        for (let i = 0; i < 54; i++) {
            pokers.push(i);
        }

        let currentIndex = pokers.length, temporaryValue, randomIndex;
        while (0 !== currentIndex) {
            randomIndex = Math.floor(Math.random() * currentIndex);
            currentIndex -= 1;

            temporaryValue = pokers[currentIndex];
            pokers[currentIndex] = pokers[randomIndex];
            pokers[randomIndex] = temporaryValue;
        }
        return pokers;
    }

}
