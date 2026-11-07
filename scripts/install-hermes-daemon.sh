#!/usr/bin/env bash
# Hermes 데몬을 WSL 부팅 시 자동 시작하도록 설치한다.
# - systemd가 켜져 있으면: 유닛 설치 + enable + start
# - 꺼져 있으면: /etc/wsl.conf에 [boot] systemd=true 추가 후 재시작 안내 (PowerShell: wsl --shutdown)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO_DIR/hermes/systemd/hermes-daemon.service"
UNIT_DST="/etc/systemd/system/hermes-daemon.service"
UV_BIN="$(command -v uv || echo /root/.local/bin/uv)"
# Ollama 주소: 환경변수 OLLAMA_HOST 우선. 없으면 WSL은 Windows 호스트(기본 게이트웨이), 그 외는 localhost.
if [ -n "${OLLAMA_HOST:-}" ]; then
  OLLAMA_HOST_VALUE="$OLLAMA_HOST"
elif grep -qi microsoft /proc/version 2>/dev/null; then
  OLLAMA_HOST_VALUE="$(ip route 2>/dev/null | awk '/default/{print $3; exit}'):11434"
else
  OLLAMA_HOST_VALUE="localhost:11434"
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "root로 실행하세요 (sudo $0)"; exit 1
fi

STATE="$(systemctl is-system-running 2>/dev/null || true)"
if [ "$STATE" != "running" ] && [ "$STATE" != "degraded" ]; then
  if ! grep -q '^\[boot\]' /etc/wsl.conf 2>/dev/null; then
    printf '\n[boot]\nsystemd=true\n' >> /etc/wsl.conf
    echo "✓ /etc/wsl.conf에 [boot] systemd=true 추가"
  elif ! grep -q '^systemd=true' /etc/wsl.conf; then
    sed -i 's/^\[boot\]/[boot]\nsystemd=true/' /etc/wsl.conf
    echo "✓ /etc/wsl.conf [boot] 섹션에 systemd=true 추가"
  fi
  echo "systemd가 아직 활성화되지 않았습니다 (state: ${STATE:-none})."
  echo "Windows PowerShell에서 'wsl --shutdown' 후 WSL을 다시 열고 이 스크립트를 재실행하세요."
  exit 0
fi

sed -e "s#/home/ubuntu/webrtc-app#$REPO_DIR#g" \
    -e "s#/root/.local/bin/uv#$UV_BIN#g" \
    -e "s#OLLAMA_HOST=.*#OLLAMA_HOST=$OLLAMA_HOST_VALUE#" \
    "$UNIT_SRC" > "$UNIT_DST"
mkdir -p "$REPO_DIR/hermes/workspace"
systemctl daemon-reload
systemctl enable --now hermes-daemon.service
echo "✓ hermes-daemon 설치·시작 완료"
echo "  상태: systemctl status hermes-daemon"
echo "  로그: tail -f $REPO_DIR/hermes/workspace/daemon.log"
echo "  중지: systemctl disable --now hermes-daemon"
