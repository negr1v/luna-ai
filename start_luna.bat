@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_luna.ps1" -Action Start
exit /b %ERRORLEVEL%
