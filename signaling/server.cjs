// server.cjs (CommonJS)
// 시그널링 서버: HTTP 헬스체크 + 같은 포트의 WebSocket 시그널링(방 단위, 1:1 타겟 유니캐스트)
const http = require("http");
const WebSocket = require("ws");

function safeJsonParse(raw) {
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function send(client, payload) {
  if (client.readyState === WebSocket.OPEN) {
    client.send(JSON.stringify(payload));
  }
}

/**
 * 시그널링 서버를 생성한다(listen은 호출자가 수행).
 * @param {{ log?: (msg: string) => void }} [options]
 * @returns {{ server: http.Server, wss: WebSocket.Server, rooms: Map<string, Set<WebSocket>> }}
 */
function createSignalingServer(options = {}) {
  const log = options.log || console.log;

  // 1) HTTP 서버 (EB/ALB 헬스체크용)
  const server = http.createServer((req, res) => {
    if (req.url === "/health") {
      res.writeHead(200, { "Content-Type": "text/plain" });
      return res.end("ok");
    }

    // 기본 루트도 200으로 두면 안정적
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("signaling-ok");
  });

  // 2) 같은 포트에서 WebSocket 업그레이드 처리
  const wss = new WebSocket.Server({ server });

  // 방 구조: { roomId: Set of sockets }
  const rooms = new Map();

  wss.on("connection", (ws) => {
    ws.on("message", (raw) => {
      const msg = safeJsonParse(raw);
      if (!msg || typeof msg !== "object") return;

      const { type, roomId, sender, target } = msg;

      if (type === "join-room") {
        if (!roomId || !sender) return;

        if (!rooms.has(roomId)) rooms.set(roomId, new Set());
        rooms.get(roomId).add(ws);

        ws.roomId = roomId;
        ws.clientId = sender;

        log(`👥 Client ${sender} joined room ${roomId}`);

        // 같은 방의 기존 클라이언트에게 "새 피어 등장" 알림
        rooms.get(roomId).forEach((client) => {
          if (client !== ws) send(client, { type: "new-peer", roomId, sender });
        });
        return;
      }

      // 타겟(target)이 지정된 경우 해당 대상에게만 1:1 유니캐스트 전달 (Glare & 다자간 충돌 방지)
      if (ws.roomId && rooms.has(ws.roomId)) {
        const roomClients = rooms.get(ws.roomId);
        if (target) {
          for (const client of roomClients) {
            if (client.clientId === target) {
              send(client, msg);
              break;
            }
          }
        } else {
          // 타겟이 없는 경우 같은 방의 다른 사용자들에게 브로드캐스트
          roomClients.forEach((client) => {
            if (client !== ws) send(client, msg);
          });
        }
      }
    });

    ws.on("close", () => {
      if (ws.roomId && rooms.has(ws.roomId)) {
        const roomId = ws.roomId;
        const sender = ws.clientId;

        rooms.get(roomId).delete(ws);

        log(`👋 Client ${sender} left room ${roomId}`);

        // 퇴장 알림 전파
        rooms.get(roomId).forEach((client) => {
          send(client, { type: "peer-left", roomId, sender });
        });

        if (rooms.get(roomId).size === 0) rooms.delete(roomId);
      }
    });
  });

  return { server, wss, rooms };
}

module.exports = { createSignalingServer };

if (require.main === module) {
  const host = process.env.SIGNAL_HOST || "0.0.0.0";
  const port = Number(process.env.SIGNAL_PORT || process.env.PORT || 3001);
  const { server } = createSignalingServer();
  server.listen(port, host, () => {
    console.log(`🚀 Signaling server running on ${host}:${port} (health: /health)`);
  });
}
