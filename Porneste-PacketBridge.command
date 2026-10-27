#!/bin/bash
set -e

PB_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [ -z "$IP" ]; then
  IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [ -z "$IP" ]; then
  IP="$(ifconfig | awk '/inet / && $2 !~ /^127\\./ && $2 !~ /^169\\.254\\./ {print $2; exit}')"
fi

if [ -z "$IP" ]; then
  echo "Nu am putut detecta IP-ul local. Verifica Wi-Fi-ul."
  read -r -p "Apasa Enter pentru inchidere..."
  exit 1
fi

echo "PacketBridge va folosi IP-ul: $IP"
cd "$PB_DIR"

"$PYTHON_BIN" -m packetbridge.relay --bind 0.0.0.0 --port 8765 --origin "http://$IP:8765" &
RELAY_PID=$!
trap 'kill "$RELAY_PID" 2>/dev/null || true' EXIT INT TERM

sleep 2
"$PYTHON_BIN" launch.py
