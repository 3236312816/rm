# 斗地主 - 人机对战

基于 Python + Tornado + Phaser2 的斗地主游戏，支持单人玩家与两个 AI 机器人对战。

## 快速开始

```shell
pip install -r requirements.txt
cd server
python app.py
```

打开浏览器访问 `http://127.0.0.1:8080`

## 技术栈

- **后端**: Python 3.8+ / Tornado 6 (WebSocket)
- **前端**: Phaser 2 (HTML5 游戏引擎)

## 功能

- 54张标准斗地主牌，完整发牌/抢地主/出牌流程
- 全面牌型识别（单张、对子、三张、顺子、连对、飞机、炸弹、王炸等）
- AI 机器人自动叫分、自动出牌
- 倍数计算（抢地主、炸弹、春天/反春、底牌翻倍）
- 出牌提示功能
- 音效、动画

## 项目结构

```
server/
  app.py              # 服务器入口
  config.py           # 配置
  templates/
    poker.html        # 游戏页面
  static/
    js/               # 前端游戏脚本 (Phaser2)
    i/                # 图片资源
    audio/            # 音效资源
    rule.json         # 牌型规则数据
  api/game/
    views.py          # WebSocket 连接处理
    room.py           # 房间逻辑
    player.py         # 玩家逻辑
    rule.py           # 牌型规则引擎 + AI 出牌策略
    timer.py          # 回合计时器
    protocol.py       # 通信协议
    globalvar.py      # 房间管理器
    components/
      simple.py       # AI 机器人
```
