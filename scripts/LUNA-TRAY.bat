@echo off
setlocal
cd /d "%~dp0"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0luna_tray.ps1"
exit /b 0
