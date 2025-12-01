@echo off
REM Обертка для запуска PowerShell скрипта очистки Docker
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0cleanup-docker.ps1"
pause









