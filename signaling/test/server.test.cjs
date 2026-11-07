const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const WebSocket = require("ws");
const { createSignalingServer } = require("../server.cjs");

let server;
let rooms;
let baseUrl;
let wsUrl;

before(async () => {
  ({ server, rooms } = createSignalingServer({ log: () => {} }));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  baseUrl = `http://127.0.0.1:${port}`;
  wsUrl = `ws://127.0.0.1:${port}`;
});

after(async () => {
  await new Promise((resolve) => server.close(resolve));
});

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.inbox = [];
    ws.waiters = [];
    ws.on("message", (raw) => {
      const msg = JSON.parse(raw.toString());
      const waiter = ws.waiters.shift();
      if (waiter) waiter(msg);
      else ws.inbox.push(msg);
    });
    ws.once("open", () => resolve(ws));
    ws.once("error", reject);
  });
}

function nextMessage(ws, timeoutMs = 1500) {
  if (ws.inbox.length) return Promise.resolve(ws.inbox.shift());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout waiting for message")), timeoutMs);
    ws.waiters.push((msg) => {
      clearTimeout(timer);
      resolve(msg);
    });
  });
}

function expectSilence(ws, ms = 200) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(), ms);
    ws.waiters.push((msg) => {
      clearTimeout(timer);
      reject(new Error(`unexpected message: ${JSON.stringify(msg)}`));
    });
  }).finally(() => {
    ws.waiters.length = 0;
  });
}

function join(ws, roomId, sender) {
  ws.send(JSON.stringify({ type: "join-room", roomId, sender }));
}

function closeAll(...sockets) {
  return Promise.all(
    sockets.map(
      (ws) =>
        new Promise((resolve) => {
          if (ws.readyState === WebSocket.CLOSED) return resolve();
          ws.once("close", resolve);
          ws.close();
        })
    )
  );
}

test("GET /health responds ok", async () => {
  const body = await new Promise((resolve, reject) => {
    http.get(`${baseUrl}/health`, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve({ status: res.statusCode, data }));
    }).on("error", reject);
  });
  assert.equal(body.status, 200);
  assert.equal(body.data, "ok");
});

test("join-room notifies existing peers with new-peer", async () => {
  const a = await connect();
  const b = await connect();
  join(a, "room-1", "A");
  join(b, "room-1", "B");

  const msg = await nextMessage(a);
  assert.deepEqual(msg, { type: "new-peer", roomId: "room-1", sender: "B" });
  await expectSilence(b);
  assert.equal(rooms.get("room-1").size, 2);

  await closeAll(a, b);
});

test("targeted messages are delivered only to the target", async () => {
  const a = await connect();
  const b = await connect();
  const c = await connect();
  join(a, "room-2", "A");
  join(b, "room-2", "B");
  join(c, "room-2", "C");
  await nextMessage(a); // new-peer B
  await nextMessage(a); // new-peer C
  await nextMessage(b); // new-peer C

  const offer = { type: "offer", roomId: "room-2", sender: "A", target: "B", sdp: "v=0" };
  a.send(JSON.stringify(offer));

  assert.deepEqual(await nextMessage(b), offer);
  await expectSilence(c);

  await closeAll(a, b, c);
});

test("messages without target are broadcast to other peers in the room only", async () => {
  const a = await connect();
  const b = await connect();
  const other = await connect();
  join(a, "room-3", "A");
  join(b, "room-3", "B");
  join(other, "room-4", "X");
  await nextMessage(a); // new-peer B

  const payload = { type: "custom", roomId: "room-3", sender: "A", body: 1 };
  a.send(JSON.stringify(payload));

  assert.deepEqual(await nextMessage(b), payload);
  await expectSilence(other);

  await closeAll(a, b, other);
});

test("closing a socket emits peer-left and removes empty rooms", async () => {
  const a = await connect();
  const b = await connect();
  join(a, "room-5", "A");
  join(b, "room-5", "B");
  await nextMessage(a); // new-peer B

  await closeAll(b);
  assert.deepEqual(await nextMessage(a), { type: "peer-left", roomId: "room-5", sender: "B" });
  assert.equal(rooms.get("room-5").size, 1);

  await closeAll(a);
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(rooms.has("room-5"), false);
});

test("invalid JSON and messages before join are ignored", async () => {
  const a = await connect();
  a.send("not json");
  a.send(JSON.stringify({ type: "offer", target: "nobody" }));
  await expectSilence(a);
  await closeAll(a);
});
