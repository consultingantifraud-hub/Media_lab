@echo off
REM Скрипт для сжатия docker_data.vhdx
REM ВАЖНО: Остановите Docker Desktop перед запуском!
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0compress-vhdx.ps1"
pause








