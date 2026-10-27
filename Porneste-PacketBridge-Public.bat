@echo off
setlocal
set "PB=C:\Users\Mihai\Desktop\PacketBridge"
set "PY=C:\Users\Mihai\AppData\Local\Python\bin\python.exe"
set "CF=%PB%\cloudflared.exe"

if not exist "%CF%" (
  echo Lipseste cloudflared.exe.
  echo Descarca-l de la: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  pause
  exit /b 1
)

start "PacketBridge Relay" /min "%PY%" -m packetbridge.relay --bind 127.0.0.1 --port 8765 --allow-any-origin
timeout /t 2 /nobreak >nul
start "PacketBridge Public Tunnel" "%CF%" tunnel --url http://127.0.0.1:8765

echo URL-ul public apare in fereastra Cloudflare si se termina in trycloudflare.com.
echo Trimite URL-ul doar persoanei autorizate. Se schimba la fiecare pornire.
cd /d "%PB%"
"%PY%" launch.py
endlocal
