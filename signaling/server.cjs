// server.cjs (CommonJS)
const http = require("http");
const WebSocket = require("ws");

const host = process.env.SIGNAL_HOST || "0.0.0.0";
const port = Number(process.env.SIGNAL_PORT || process.env.PORT || 3001);

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

function safeJsonParse(raw) {
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

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

      console.log(`👥 Client ${sender} joined room ${roomId}`);

      // 같은 방의 기존 클라이언트에게 "새 피어 등장" 알림
      rooms.get(roomId).forEach((client) => {
        if (client !== ws && client.readyState === WebSocket.OPEN) {
          client.send(
            JSON.stringify({
              type: "new-peer",
              roomId,
              sender,
            })
          );
        }
      });
      return;
    }

    // 타겟(target)이 지정된 경우 해당 대상에게만 1:1 유니캐스트 전달 (Glare & 다자간 충돌 방지)
    if (ws.roomId && rooms.has(ws.roomId)) {
      const roomClients = rooms.get(ws.roomId);
      if (target) {
        for (const client of roomClients) {
          if (client.clientId === target && client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(msg));
            break;
          }
        }
      } else {
        // 타겟이 없는 경우 같은 방의 다른 사용자들에게 브로드캐스트
        roomClients.forEach((client) => {
          if (client !== ws && client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(msg));
          }
        });
      }
    }
  });

  ws.on("close", () => {
    if (ws.roomId && rooms.has(ws.roomId)) {
      const roomId = ws.roomId;
      const sender = ws.clientId;

      rooms.get(roomId).delete(ws);

      console.log(`👋 Client ${sender} left room ${roomId}`);

      // 퇴장 알림 전파
      rooms.get(roomId).forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(
            JSON.stringify({
              type: "peer-left",
              roomId,
              sender,
            })
          );
        }
      });

      if (rooms.get(roomId).size === 0) rooms.delete(roomId);
    }
  });
});

server.listen(port, host, () => {
  console.log(`🚀 Signaling server running on ${host}:${port} (health: /health)`);
});
