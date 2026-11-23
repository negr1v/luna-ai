@echo off
title Accio Luna - Sesli Asistan
cd /d "%~dp0"
echo ========================================================
echo       Accio Luna Sesli Asistan Baslatiliyor...
echo ========================================================

set "ACCIO_PY=C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

if exist "%ACCIO_PY%" (
    "%ACCIO_PY%" luna_voice.py
) else (
    python luna_voice.py
)

pause
