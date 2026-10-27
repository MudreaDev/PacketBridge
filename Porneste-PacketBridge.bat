@echo off
setlocal

set "PB=C:\Users\Mihai\Desktop\PacketBridge"
set "PY=C:\Users\Mihai\AppData\Local\Python\bin\python.exe"

if not exist "%PY%" (
  echo Nu am gasit Python la:
  echo %PY%
  pause
  exit /b 1
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$text=ipconfig; $block=($text -split ([Environment]::NewLine + [Environment]::NewLine) ^| Where-Object { $_ -match 'WiFi' } ^| Select-Object -First 1); if ($block -match '([0-9]{1,3}[.]){3}[0-9]{1,3}') { $matches[0] } else { $ips=$text ^| Select-String -Pattern 'IPv4' ^| ForEach-Object { if ($_ -match '([0-9]{1,3}[.]){3}[0-9]{1,3}') { $matches[0] } }; $ips ^| Where-Object { $_ -notlike '127.*' -and $_ -notlike '169.254.*' } ^| Select-Object -First 1 }"`) do set "IP=%%I"

if not defined IP (
  echo Nu am putut detecta IP-ul local. Verifica conexiunea Wi-Fi.
  pause
  exit /b 1
)

echo PacketBridge va folosi IP-ul: %IP%
start "PacketBridge Relay" /min "%PY%" -m packetbridge.relay --bind 0.0.0.0 --port 8765 --origin http://%IP%:8765

timeout /t 2 /nobreak >nul
cd /d "%PB%"
"%PY%" launch.py

endlocal
