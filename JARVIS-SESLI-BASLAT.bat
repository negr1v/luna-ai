@echo off
title Accio Jarvis - Sesli Asistan
cd /d "%~dp0"
echo ========================================================
echo       Accio Jarvis Sesli Asistan Baslatiliyor...
echo ========================================================

set "ACCIO_PY=C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

if exist "%ACCIO_PY%" (
    "%ACCIO_PY%" jarvis_voice.py
) else (
    python jarvis_voice.py
)

pause
