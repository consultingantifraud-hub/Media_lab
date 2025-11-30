@echo off
REM Версия очистки Docker С очисткой папки media/
REM ВНИМАНИЕ: Будет удалено содержимое папки media/!
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0cleanup-docker-with-media.ps1"
pause








