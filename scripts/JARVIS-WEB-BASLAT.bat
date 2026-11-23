@echo off
title Accio Jarvis - Sesli Komuta Merkezi
cd /d "%~dp0"
echo ========================================================
echo       Accio Jarvis Sesli Arayuz Baslatiliyor...
echo ========================================================

set "ACCIO_PY=C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

start "" "http://127.0.0.1:7860"

if exist "%ACCIO_PY%" (
    "%ACCIO_PY%" jarvis_server.py
) else (
    python jarvis_server.py
)

pause
