#!/bin/bash
set -e

PB_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PB_DIR"

echo "Instalez dependentele PacketBridge..."
python3 -m pip install -r requirements.txt
chmod +x "$PB_DIR/Porneste-PacketBridge.command"

echo
echo "Deschid setarile macOS pentru permisiuni."
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture' || true
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility' || true

echo
echo "Activeaza pentru Terminal sau Python:"
echo "  - Screen Recording"
echo "  - Accessibility"
echo
echo "Dupa acordarea permisiunilor, porneste PacketBridge cu:"
echo "$PB_DIR/Porneste-PacketBridge.command"
read -r -p "Apasa Enter pentru inchidere..."
