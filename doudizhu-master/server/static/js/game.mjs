import {Poker, Rule} from '/static/js/rule.mjs'
import {Player, createPlay} from '/static/js/player.mjs'
import {Protocol, Socket} from '/static/js/net.mjs'

class Observer {

    constructor() {
        this.state = {};
        this.subscribers = {};
    }

    get(key) {
        return this.state[key];
    }

    set(key, val) {
        const keys = key.split('.');
        if (keys.length === 1) {
            this.state[key] = val;
        } else {
            this.state[keys[0]][keys[1]] = val;
            key = keys[0];
        }
        const newVal = this.state[key];
        const subscribers = this.subscribers;
        if (subscribers.hasOwnProperty(key)) {
            subscribers[key].forEach(function (cb) {
                if (cb) cb(newVal);
            });
        }
    }

    subscribe(key, cb) {
        const subscribers = this.subscribers;
        if (subscribers.hasOwnProperty(key)) {
            subscribers[key].push(cb);
        } else {
            subscribers[key] = [cb];
        }
    }

    unsubscribe(key, cb) {
        const subscribers = this.subscribers;
        if (subscribers.hasOwnProperty(key)) {
            const index = subscribers.indexOf(cb);
            if (index > -1) {
                subscribers.splice(index, 1);
            }
        }
    }
}

const observer = new Observer();

export class Game {
    constructor(game) {
        this.players = [];

        this.tablePoker = [];
        this.tablePokerPic = {};

        this.lastShotPlayer = null;

        this.whoseTurn = 0;
        this._gameStarted = false;
        this._bgMusic = null;
    }

    init(baseScore) {
        observer.set('baseScore', baseScore);
    }

    create() {
        Rule.RuleList = this.cache.getJSON('rule');

        // 牌桌背景
        let bg = this.game.add.image(0, 0, 'bg');
        bg.width = this.game.world.width;
        bg.height = this.game.world.height;

        this.players.push(createPlay(0, this));
        this.players.push(createPlay(1, this));
        this.players.push(createPlay(2, this));
        this.players[0].updateInfo(1, '玩家');
        this.players[1].updateInfo(10001, '机器人-A');
        this.players[2].updateInfo(10002, '机器人-B');

        const protocol = location.protocol.startsWith("https") ? "wss://" : "ws://";
        this.socket = new Socket(protocol + location.host + "/ws");
        this.socket.connect(this.onopen.bind(this), this.onmessage.bind(this), this.onerror.bind(this));

        const width = this.game.world.width;
        const height = this.game.world.height;

        const titleBar = this.game.add.text(width / 2, 0, `底分: 10  倍数: 1`, {
            font: "22px",
            fill: "#fff",
            align: "center"
        });
        titleBar.anchor.set(0.5, 0);
        observer.subscribe('room', function (room) {
            titleBar.text = `底分: ${room.origin}  倍数: ${room.multiple}`;
        });

        // 创建抢地主按钮
        const group = this.game.add.group();
        let pass = this.game.make.button(width * 0.4, height * 0.6, "btn", function () {
            this.game.add.audio('f_score_0').play();
            this.send_message([Protocol.REQ_CALL_SCORE, {"rob": 0}]);
        }, this, 'score_0.png', 'score_0.png', 'score_0.png');
        pass.anchor.set(0.5, 0);
        group.add(pass);

        const rob = this.game.make.button(width * 0.6, height * 0.6, "btn", function () {
            this.game.add.audio('f_score_1').play();
            this.send_message([Protocol.REQ_CALL_SCORE, {"rob": 1}]);
        }, this, 'score_1.png', 'score_1.png', 'score_1.png');
        rob.anchor.set(0.5, 0);
        group.add(rob);
        group.visible = false;

        observer.subscribe('rob', function (is_rob) {
            group.visible = is_rob;
        });
        
        // 游戏结束遮罩
        this._gameOverText = this.game.add.text(width / 2, height / 2 - 60, '', {
            font: "48px Arial",
            fill: "#FFD700",
            align: "center",
            stroke: "#000",
            strokeThickness: 4
        });
        this._gameOverText.anchor.set(0.5);
        this._gameOverText.visible = false;

        this._gameOverDetail = this.game.add.text(width / 2, height / 2, '', {
            font: "28px Arial",
            fill: "#fff",
            align: "center"
        });
        this._gameOverDetail.anchor.set(0.5);
        this._gameOverDetail.visible = false;
        
        // 游戏结束按钮组（继续/退出）
        this._nextRoundGroup = this.game.add.group();
        let continueBtn = this.game.make.button(width / 2 - 160, height / 2 + 110, "btn", function () {
            this.send_message([Protocol.REQ_NEXT_ROUND, {}]);
            this._nextRoundGroup.visible = false;
            this._gameOverText.visible = false;
            this._gameOverDetail.visible = false;
            this._gameStarted = false;
            this.cleanWorld();
        }, this, 'quick.png', 'quick.png', 'quick.png');
        continueBtn.anchor.set(0.5, 0);
        this._nextRoundGroup.add(continueBtn);

        let exitBtn = this.game.make.button(width / 2 + 160, height / 2 + 110, "btn", function () {
            window.close();
        }, this, 'exit.png', 'exit.png', 'exit.png');
        exitBtn.anchor.set(0.5, 0);
        this._nextRoundGroup.add(exitBtn);
        this._nextRoundGroup.visible = false;
    }

    onopen() {
        console.log('socket onopen');
        this._reconnect_count = 0;
    }

    onerror() {
        if (this._reconnect_count === undefined) {
            this._reconnect_count = 0;
        }
        this._reconnect_count++;
        if (this._reconnect_count > 3) {
            console.log('socket reconnect failed after 3 attempts.');
            return;
        }
        console.log('socket onerror, try reconnect, attempt ' + this._reconnect_count);
        setTimeout(() => {
            this.socket.connect(this.onopen.bind(this), this.onmessage.bind(this), this.onerror.bind(this));
        }, 2000);
    }

    send_message(request) {
        this.socket.send(request);
    }

    onmessage(message) {
        const code = message[0], packet = message[1];
        switch (code) {
            case Protocol.RSP_JOIN_ROOM:
                observer.set('room', packet['room']);
                break;
            case Protocol.RSP_DEAL_POKER: {
                this._gameStarted = true;
                // 开始/重新开始循环背景音乐
                if (this._bgMusic) {
                    this._bgMusic.stop();
                }
                this._bgMusic = this.game.add.audio('music_bg');
                this._bgMusic.loop = true;
                this._bgMusic.volume = 0.33;
                this._bgMusic.play();
                const playerId = packet['uid'];
                const pokers = packet['pokers'];
                this._nextRoundGroup.visible = false;
                this.cleanWorld();
                this.dealPoker(pokers);
                this.whoseTurn = this.uidToSeat(playerId);
                this.startCallScore();
                break;
            }
            case Protocol.RSP_CALL_SCORE: {
                const playerId = packet['uid'];
                const rob = packet['rob'];
                const landlord = packet['landlord'];
                this.whoseTurn = this.uidToSeat(playerId);

                const hanzi = ['不抢', "抢地主"];
                this.players[this.whoseTurn].say(hanzi[rob]);

                observer.set('rob', false);
                if (landlord === -1) {
                    this.whoseTurn = (this.whoseTurn + 1) % 3;
                    this.startCallScore();
                } else {
                    this.whoseTurn = this.uidToSeat(landlord);
                    this.players[this.whoseTurn].setLandlord();
                    this.showLastThreePoker(packet['pokers']);
                }
                observer.set('room.multiple', packet['multiple']);
                break;
            }
            case Protocol.RSP_SHOT_POKER:
                this.handleShotPoker(packet);
                observer.set('room.multiple', packet['multiple']);
                break;
            case Protocol.RSP_DIMENSIONAL_REDUCTION:
                this.showDimensionalStrike(packet);
                break;
            case Protocol.RSP_GAME_OVER: {
                // 停止循环背景音乐
                if (this._bgMusic) {
                    this._bgMusic.stop();
                    this._bgMusic = null;
                }
                const winner = packet['winner'];
                const landlordUid = packet['landlord_uid'];
                const that = this;

                // 使用服务端下发的 landlord_uid，不依赖前端 isLandlord 状态
                this.whoseTurn = this.uidToSeat(winner);
                const winnerIsLandlord = (winner === landlordUid);
                const humanIsLandlord = (that.players[0].uid === landlordUid);
                const isHumanWin = humanIsLandlord === winnerIsLandlord;
                // 播放胜负音效
                this.game.add.audio(isHumanWin ? 'music_win' : 'music_lose').play();
                const winnerRole = winnerIsLandlord ? "地主" : "农民";

                // 显示所有玩家手牌（先重置再重建精灵）
                this.players.forEach(function (player) {
                    player.isLandlord = false;
                });
                packet['players'].forEach(function (player) {
                    const seat = that.uidToSeat(player['uid']);
                    if (seat >= 0) {
                        const p = that.players[seat];
                        p.cleanPokers();
                        p.pokerInHand = player['pokers'].slice();
                        p._buildPokerSprites();
                        p.reDealPoker();
                    }
                });

                this._gameOverText.text = winnerRole + "获胜!";
                this._gameOverText.visible = true;
                
                // 显示得分（取玩家自己的得分，不是赢家的）
                const humanPoint = packet['players'][0]?.point || 0;
                const yourResult = isHumanWin ? "你赢了" : "你输了";
                this._gameOverDetail.text = yourResult + "  得分: " + (humanPoint > 0 ? "+" : "") + humanPoint;
                this._gameOverDetail.visible = true;

                // 显示继续/退出按钮
                this._nextRoundGroup.visible = true;
                break;
            }
            default:
                console.log("UNKNOWN PACKET:", packet)
        }
    }

    cleanWorld() {
        this.players.forEach(function (player) {
            player.cleanPokers();
            player.isLandlord = false;
            player.uiHead.frameName = 'icon_farmer.png';
        });
        for (let i = 0; i < this.tablePoker.length; i++) {
            let p = this.tablePokerPic[this.tablePoker[i]];
            if (p) p.destroy();
        }
        this.tablePoker = [];
        this.tablePokerPic = {};
        this.lastShotPlayer = null;
    }

    update() {
    }

    uidToSeat(uid) {
        for (let i = 0; i < 3; i++) {
            if (uid === this.players[i].uid)
                return i;
        }
        console.log('ERROR uidToSeat:' + uid);
        return -1;
    }

    dealPoker(pokers) {
        // 添加一张底牌占位
        let p = new Poker(this, 0, 55);
        this.tablePokerPic[55] = p;
        this.game.world.add(p);

        for (let i = 0; i < 17; i++) {
            this.players[2].pokerInHand.push(55);
            this.players[1].pokerInHand.push(55);
            this.players[0].pokerInHand.push(pokers.pop());
        }

        this.players[0].dealPoker();
        this.players[1].dealPoker();
        this.players[2].dealPoker();
    }

    showLastThreePoker(lastThreePokers) {
        // 保存底牌供 dealLastThreePoker 使用
        this._lastThreePokers = lastThreePokers;

        // 删除底牌占位
        if (this.tablePokerPic[55]) {
            this.tablePokerPic[55].destroy();
            delete this.tablePokerPic[55];
        }

        for (let i = 0; i < 3; i++) {
            let pokerId = lastThreePokers[i];
            let p = new Poker(this, pokerId, pokerId);
            this.tablePokerPic[pokerId] = p;
            this.game.world.add(p);
            this.game.add.tween(p).to({x: this.game.world.width / 2 + (i - 1) * 60}, 600, Phaser.Easing.Default, true);
        }
        this.game.time.events.add(1500, this.dealLastThreePoker, this);
    }

    dealLastThreePoker() {
        let turnPlayer = this.players[this.whoseTurn];
        let lastThree = this._lastThreePokers || [];

        for (let i = 0; i < lastThree.length; i++) {
            let pid = lastThree[i];
            let poker = this.tablePokerPic[pid];
            if (poker) {
                turnPlayer.pokerInHand.push(pid);
                turnPlayer.pushAPoker(poker);
            }
        }
        turnPlayer.sortPoker();
        if (this.whoseTurn === 0) {
            turnPlayer.arrangePoker();
            const that = this;
            for (let i = 0; i < lastThree.length; i++) {
                let pid = lastThree[i];
                let p = this.tablePokerPic[pid];
                if (p) {
                    let tween = this.game.add.tween(p).to({y: this.game.world.height - Poker.PH * 0.8}, 400, Phaser.Easing.Default, true);
                    tween.onComplete.add(function(p) {
                        that.game.add.tween(p).to({y: that.game.world.height - Poker.PH / 2}, 400, Phaser.Easing.Default, true, 400);
                    }, this, p);
                }
            }
        } else {
            let first = turnPlayer.findAPoker(55);
            for (let i = 0; i < lastThree.length; i++) {
                let pid = lastThree[i];
                let p = this.tablePokerPic[pid];
                if (p) {
                    p.frame = 55 - 1;
                    if (first) {
                        this.game.add.tween(p).to({x: first.x, y: first.y}, 200, Phaser.Easing.Default, true);
                    }
                }
            }
        }

        this.tablePoker = [];
        this.lastShotPlayer = turnPlayer;
        if (this.whoseTurn === 0) {
            this.game.time.events.add(500, this.startPlay, this);
        }
    }

    handleShotPoker(packet) {
        this.whoseTurn = this.uidToSeat(packet['uid']);
        let turnPlayer = this.players[this.whoseTurn];
        let pokers = packet['pokers'];
        if (pokers.length === 0) {
            this.players[this.whoseTurn].say("不出");
            // 随机播放过牌音效
            let passKey = Math.random() < 0.5 ? 'sound_pass1' : 'sound_pass2';
            this.game.add.audio(passKey).play();
        } else {
            let pokersPic = {};
            pokers.sort(Poker.comparePoker);
            let count = pokers.length;
            let gap = Math.min((this.game.world.width - Poker.PW * 2) / count, Poker.PW * 0.36);

            // 清理旧牌桌
            for (let i = 0; i < this.tablePoker.length; i++) {
                let p = this.tablePokerPic[this.tablePoker[i]];
                if (p) p.destroy();
            }

            for (let i = 0; i < count; i++) {
                let p = turnPlayer.findAPoker(pokers[i]);
                if (p) {
                    // 手牌中有对应精灵（人类玩家），直接移到桌面
                    // 特殊牌纹理已在构造函数中设定，无需改frame
                    if (!Poker.isSpecialId(pokers[i])) {
                        p.frame = pokers[i] - 1;
                    }
                    p.bringToTop();
                } else {
                    // 手牌中无对应精灵（机器人玩家），新建牌桌精灵
                    p = new Poker(this.game, pokers[i], pokers[i]);
                    this.game.world.add(p);
                }
                turnPlayer.removeAPoker(pokers[i]);
                this.game.add.tween(p).to({
                    x: this.game.world.width / 2 + (i - count / 2) * gap,
                    y: this.game.world.height * 0.4
                }, 500, Phaser.Easing.Default, true);
                pokersPic[p.id] = p;
            }

            // 牌型音效 + 压制音效
            // 必须在更新 this.tablePoker/this.lastShotPlayer 之前保存旧值
            let prevTablePoker = this.tablePoker;
            let prevLastShotPlayer = this.lastShotPlayer;

            this.tablePoker = pokers;
            this.tablePokerPic = pokersPic;
            this.lastShotPlayer = turnPlayer;

            let curCards = Poker.toCards(pokers);
            let curCardInfo = Rule.cardsValue(curCards);
            let curCardType = curCardInfo[0];

            // 判断是否是压制（有上家牌且不是同一人领出）
            let isSuppression = prevTablePoker.length > 0 && prevLastShotPlayer !== turnPlayer;

            // ---- 音效播放规则 ----
            // 炸弹/火箭音效优先，且不播放压制音效
            if (curCardType === 'bomb') {
                this.game.add.audio('sound_zhadan').play();
            } else if (curCardType === 'rocket') {
                this.game.add.audio('sound_wzha').play();
            } else if (isSuppression) {
                // 压制场景：只播压制音效（yasi/dani），不播牌型音效
                if (curCardType !== 'single' && curCardType !== 'pair') {
                    let prevIsLandlord = prevLastShotPlayer ? prevLastShotPlayer.isLandlord : false;
                    if (turnPlayer.isLandlord && !prevIsLandlord) {
                        // 地主压制农民 → dani
                        this.game.add.audio('sound_dani').play();
                    } else if (!turnPlayer.isLandlord && prevIsLandlord) {
                        // 农民压制地主 → yasi
                        this.game.add.audio('sound_yasi').play();
                    }
                    // 农民压制农民 → 无音效
                }
            } else {
                // 领出场景：只播牌型音效，不播压制音效
                if (curCardType.startsWith('seq_single')) {
                    this.game.add.audio('sound_shunzi').play();
                } else if (curCardType.startsWith('seq_pair')) {
                    this.game.add.audio('sound_liandui').play();
                } else if (curCardType.startsWith('seq_trio')) {
                    this.game.add.audio('sound_feiji').play();
                } else if (curCardType === 'trio_single') {
                    this.game.add.audio('sound_31').play();
                } else if (curCardType === 'trio_pair') {
                    this.game.add.audio('sound_32').play();
                }
            }
            turnPlayer.arrangePoker();
        }
        if (turnPlayer.pokerInHand.length > 0) {
            this.whoseTurn = (this.whoseTurn + 1) % 3;
            if (this.whoseTurn === 0) {
                this.game.time.events.add(1000, this.startPlay, this);
            }
        }
    }

    showDimensionalStrike(packet) {
        const width = this.game.world.width;
        const height = this.game.world.height;

        // 1. Screen shake
        this.game.camera.shake(0.03, 500);

        // 2. White flash overlay (fades quickly to reveal text)
        const flash = this.game.add.graphics(0, 0);
        flash.beginFill(0xffffff, 0.9);
        flash.drawRect(0, 0, width, height);
        flash.endFill();
        this.game.add.tween(flash).to({alpha: 0}, 400, Phaser.Easing.Exponential.Out, true)
            .onComplete.add(() => flash.destroy());

        // 3. "降维打击" text (added AFTER flash to render on top)
        const title = this.game.add.text(width / 2, height / 2 - 30, '降 维 打 击', {
            font: 'bold 48px Arial',
            fill: '#FF00FF',
            align: 'center',
            stroke: '#000000',
            strokeThickness: 6,
        });
        title.anchor.set(0.5);
        title.scale.set(0.1);
        // Scale up from tiny to large
        this.game.add.tween(title).to({scale: {x: 1.8, y: 1.8}}, 700, Phaser.Easing.Back.Out, true);
        // Subtitle
        const subtitle = this.game.add.text(width / 2, height / 2 + 40, 'AI 农民获得特殊牌组！', {
            font: 'bold 22px Arial',
            fill: '#FFFF00',
            align: 'center',
            stroke: '#000000',
            strokeThickness: 3,
        });
        subtitle.anchor.set(0.5);
        subtitle.alpha = 0;
        this.game.add.tween(subtitle).to({alpha: 1}, 500, Phaser.Easing.Default, true, 600);
        // Hold visible then fade out
        this.game.time.events.add(2500, () => {
            this.game.add.tween(title).to({alpha: 0, scale: {x: 2.2, y: 2.2}}, 600,
                Phaser.Easing.Exponential.In, true)
                .onComplete.add(() => title.destroy());
            this.game.add.tween(subtitle).to({alpha: 0}, 600, Phaser.Easing.Exponential.In, true)
                .onComplete.add(() => subtitle.destroy());
        });

        // 4. Particle burst
        for (let i = 0; i < 20; i++) {
            const particle = this.game.add.graphics(
                width / 2 + (Math.random() - 0.5) * 200,
                height / 2 + (Math.random() - 0.5) * 100
            );
            particle.beginFill(
                [0xFF00FF, 0x00FFFF, 0xFFFF00, 0xFF0000][Math.floor(Math.random() * 4)], 1);
            particle.drawCircle(0, 0, 4 + Math.random() * 6);
            particle.endFill();
            this.game.add.tween(particle).to({
                x: particle.x + (Math.random() - 0.5) * 400,
                y: particle.y + (Math.random() - 0.5) * 300,
                alpha: 0
            }, 1200, Phaser.Easing.Quadratic.Out, true)
                .onComplete.add(() => particle.destroy());
        }

        // 5. Add special cards to robot hands (preserve existing cards!)
        const robotA = this.players[1];
        const robotB = this.players[2];
        const human = this.players[0];
        const robotACards = packet['robot_a_cards'] || [];
        const robotBCards = packet['robot_b_cards'] || [];
        const humanCards = packet['human_cards'] || [];

        // Save original cards BEFORE cleanPokers() wipes them
        const robotAOriginal = robotA.pokerInHand.slice();
        const robotBOriginal = robotB.pokerInHand.slice();
        const humanOriginal = human.pokerInHand.slice();

        // Rebuild robot A: clean, then add original + special, rebuild sprites
        robotA.cleanPokers();
        robotAOriginal.forEach(id => robotA.pokerInHand.push(id));
        robotACards.forEach(id => { if (!robotA.pokerInHand.includes(id)) robotA.pokerInHand.push(id); });
        robotA._buildPokerSprites();
        robotA.reDealPoker();
        robotA.updateLeftPoker();

        // Rebuild robot B: clean, then add original + special, rebuild sprites
        robotB.cleanPokers();
        robotBOriginal.forEach(id => robotB.pokerInHand.push(id));
        robotBCards.forEach(id => { if (!robotB.pokerInHand.includes(id)) robotB.pokerInHand.push(id); });
        robotB._buildPokerSprites();
        robotB.reDealPoker();
        robotB.updateLeftPoker();

        // Rebuild human hand: add zdjd cards
        human.cleanPokers();
        humanOriginal.forEach(id => human.pokerInHand.push(id));
        humanCards.forEach(id => { if (!human.pokerInHand.includes(id)) human.pokerInHand.push(id); });
        human.sortPoker();
        human._buildPokerSprites();
        human.reDealPoker();
    }

    startCallScore() {
        if (this.whoseTurn === 0) {
            observer.set('rob', true);
        }
    }

    startPlay() {
        if (this.isLastShotPlayer()) {
            this.players[0].playPoker([]);
        } else {
            this.players[0].playPoker(this.tablePoker);
        }
    }

    finishPlay(pokers) {
        this.send_message([Protocol.REQ_SHOT_POKER, {"pokers": pokers}]);
    }

    isLastShotPlayer() {
        return this.players[this.whoseTurn] === this.lastShotPlayer;
    }
}
