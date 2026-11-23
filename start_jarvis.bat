@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_jarvis.ps1" -Action Start
exit /b %ERRORLEVEL%
