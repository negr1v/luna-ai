@echo off
title Accio Luna - Sesli Komuta Merkezi
cd /d "%~dp0"
echo ========================================================
echo       Accio Luna Sesli Arayuz Baslatiliyor...
echo ========================================================

set "ACCIO_PY=C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

start "" "http://127.0.0.1:7860"

if exist "%ACCIO_PY%" (
    "%ACCIO_PY%" luna_server.py
) else (
    python luna_server.py
)

pause
