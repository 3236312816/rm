export const Protocol = {
    ERROR: 0,
    REQ_CALL_SCORE: 2005,
    RSP_CALL_SCORE: 2006,
    RSP_JOIN_ROOM: 1006,
    RSP_READY: 2002,
    RSP_DEAL_POKER: 2004,
    REQ_SHOT_POKER: 3001,
    RSP_SHOT_POKER: 3002,
    RSP_DIMENSIONAL_REDUCTION: 3003,
    RSP_GAME_OVER: 4002,
    REQ_NEXT_ROUND: 5001,
};

function pretty_log(tag, packet) {
    for (let key in Protocol) {
        if (packet[0] === Protocol[key])
            console.log(`${tag}: ${key} ${JSON.stringify(packet.slice(1))}`)
    }
}

export class Socket {
    constructor(url) {
        this.url = url;
        this.websocket = null;
    }
    connect(onopen, onmessage, onerror) {
        const ws = new WebSocket(this.url);
        ws.binaryType = "arraybuffer";

        ws.onopen = function (evt) {
            console.log("CONNECTED");
            onopen();
        };

        ws.onerror = function (evt) {
            console.log("CONNECT ERROR");
            onerror();
        };

        ws.onclose = function (evt) {
            console.log("DISCONNECTED");
            onerror();
        };

        ws.onmessage = function (evt) {
            const packet = JSON.parse(evt.data);
            pretty_log("RSP", packet);
            onmessage(packet);
        };

        this.websocket = ws;
    }

    send (packet) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            pretty_log("REQ", packet);
            this.websocket.send(JSON.stringify(packet));
        } else {
            console.log("SOCKET NOT OPEN, drop packet:", packet);
        }
    }

}
