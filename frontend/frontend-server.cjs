const fs = require("fs");
const http = require("http");
const path = require("path");

const host = process.env.FRONTEND_HOST || "0.0.0.0";
const port = Number(process.env.FRONTEND_PORT || process.env.PORT || 80);
const distDir = path.join(__dirname, "dist");
const runtimeConfig = {
  VITE_SIGNAL_URL: process.env.VITE_SIGNAL_URL || "",
  VITE_SIGNAL_PORT: process.env.VITE_SIGNAL_PORT || "3001",
};

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
};

function sendFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const contentType = mimeTypes[ext] || "application/octet-stream";

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("internal-server-error");
      return;
    }

    res.writeHead(200, { "Content-Type": contentType });
    res.end(data);
  });
}

function sendRuntimeConfig(res) {
  const body = `window.__APP_CONFIG__ = ${JSON.stringify(runtimeConfig)};\n`;
  res.writeHead(200, {
    "Content-Type": "text/javascript; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("ok");
    return;
  }

  if ((req.url || "").split("?")[0] === "/env-config.js") {
    sendRuntimeConfig(res);
    return;
  }

  const requestPath = decodeURIComponent((req.url || "/").split("?")[0]);
  const normalizedPath = requestPath === "/" ? "/index.html" : requestPath;
  const candidatePath = path.join(distDir, normalizedPath);

  if (!candidatePath.startsWith(distDir)) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("forbidden");
    return;
  }

  fs.stat(candidatePath, (err, stat) => {
    if (!err && stat.isFile()) {
      sendFile(res, candidatePath);
      return;
    }

    sendFile(res, path.join(distDir, "index.html"));
  });
});

server.listen(port, host, () => {
  console.log(`Frontend server listening on http://${host}:${port}`);
});
