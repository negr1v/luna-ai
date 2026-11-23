@echo off
title LUNA-AI - Temiz Baslatici
cd /d "%~dp0"

echo ========================================================
echo        LUNA-AI GUNCELLEME VE BASLATMA
echo ========================================================
echo 1. Eski calisan sunucu temizleniyor (Port 7860)...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :7860 ^| findstr LISTENING') do (
    echo [BILGI] Port 7860 uzerindeki surec sonlandiriliyor: PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo 2. Tasinabilir paket otomatik senkronize ediliyor...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_portable.ps1"

set "ACCIO_PY=C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

echo 3. Tarayici aciliyor...
start "" "http://127.0.0.1:7860"

echo 4. LUNA Sunucusu Baslatiliyor...
if exist "%ACCIO_PY%" (
    "%ACCIO_PY%" luna_server.py
) else (
    python luna_server.py
)

pause
