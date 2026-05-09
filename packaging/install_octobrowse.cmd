@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_octobrowse.ps1"
exit /b %ERRORLEVEL%
