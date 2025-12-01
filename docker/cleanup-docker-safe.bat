@echo off
REM Безопасная версия очистки Docker БЕЗ удаления volumes
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0cleanup-docker-safe.ps1"
pause









