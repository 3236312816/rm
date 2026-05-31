
function get(url, payload, callback) {
    http('GET', url, payload, callback);
}

function http(method, url, payload, callback) {
    const xhr = new XMLHttpRequest();
    xhr.withCredentials = true;
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            const response = JSON.parse(xhr.responseText);
            callback(xhr.status, response);
        }
    };
    xhr.send(JSON.stringify(payload));
}

export class Boot {
    preload() {
        this.load.image('preloaderBar', 'static/i/preload.png');
    }

    create() {
        this.input.maxPointers = 1;
        this.stage.disableVisibilityChange = true;
        this.scale.scaleMode = Phaser.ScaleManager.SHOW_ALL;
        this.scale.enterIncorrectOrientation.add(this.enterIncorrectOrientation, this);
        this.scale.leaveIncorrectOrientation.add(this.leaveIncorrectOrientation, this);
        this.onSizeChange();
        this.state.start('Preloader');
    }

    onSizeChange() {
        this.scale.minWidth = 480;
        this.scale.minHeight = 270;
        let device = this.game.device;
        if (device.android || device.iOS) {
            this.scale.maxWidth = window.innerWidth;
            this.scale.maxHeight = window.innerHeight;
        } else {
            this.scale.maxWidth = 960;
            this.scale.maxHeight = 540;
        }
        this.scale.pageAlignHorizontally = true;
        this.scale.pageAlignVertically = true;
        this.scale.forceOrientation(true);
    }

    enterIncorrectOrientation() {
        document.getElementById('orientation').style.display = 'block';
    }

    leaveIncorrectOrientation() {
        document.getElementById('orientation').style.display = 'none';
    }
}

export class Preloader {

    preload() {
        this.preloadBar = this.game.add.sprite(120, 200, 'preloaderBar');
        this.load.setPreloadSprite(this.preloadBar);

        this.load.audio('music_room', 'static/audio/bg_room.mp3');
        this.load.audio('music_game', 'static/audio/bg_game.ogg');
        this.load.audio('music_bg', 'static/audio/bg.mp3');
        this.load.audio('music_deal', 'static/audio/deal.mp3');
        this.load.audio('music_win', 'static/audio/end_win.mp3');
        this.load.audio('music_lose', 'static/audio/end_lose.mp3');
        this.load.audio('f_score_0', 'static/audio/f_score_0.mp3');
        this.load.audio('f_score_1', 'static/audio/f_score_1.mp3');
        this.load.audio('sound_yasi', 'static/audio/yasi.mp3');
        this.load.audio('sound_dani', 'static/audio/dani.mp3');
        this.load.audio('sound_shunzi', 'static/audio/shunzi.mp3');
        this.load.audio('sound_feiji', 'static/audio/feiji.mp3');
        this.load.audio('sound_liandui', 'static/audio/liandui.mp3');
        this.load.audio('sound_31', 'static/audio/31.mp3');
        this.load.audio('sound_32', 'static/audio/32.mp3');
        this.load.audio('sound_zhadan', 'static/audio/zhadan.mp3');
        this.load.audio('sound_wzha', 'static/audio/wzha.mp3');
        this.load.audio('sound_pass1', 'static/audio/pass1.mp3');
        this.load.audio('sound_pass2', 'static/audio/pass2.mp3');
        this.load.atlas('btn', 'static/i/btn.png', 'static/i/btn.json');
        this.load.image('bg', 'static/i/tabel.jpg');
        this.load.spritesheet('poker', 'static/i/poker.png', 90, 120);
        this.load.json('rule', 'static/rule.json');
        // 降维打击特殊牌牌面图片
        this.load.image('card_z', 'static/i/z1.png');
        this.load.image('card_m', 'static/i/m.png');
        this.load.image('card_j1', 'static/i/j1.png');
        this.load.image('card_j2', 'static/i/j2.png');
        this.load.image('card_k1', 'static/i/k1.png');
        this.load.image('card_k2', 'static/i/k2.png');
        this.load.image('card_k3', 'static/i/k3.png');
        this.load.image('card_s', 'static/i/s.png');
        this.load.image('card_k4', 'static/i/k4.png');
        this.load.image('card_b', 'static/i/b.jpg');
        this.load.image('card_l', 'static/i/l.png');
        // zdjd 特殊牌牌面图片
        this.load.image('card_z2', 'static/i/z2.png');
        this.load.image('card_d1', 'static/i/d1.png');
        this.load.image('card_j4', 'static/i/j4.png');
        this.load.image('card_d2', 'static/i/d2.png');
    }

    create() {
        window.playerInfo = {uid: 1, name: '玩家'};
        this.state.start('GameScene');
    }
}

export class GameScene {
    create() {
        this.state.start('Game', true, false, 1);
    }
}
