@echo off
REM Скрипт для расширения диска C:
REM ВАЖНО: Запустите от имени АДМИНИСТРАТОРА!
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0extend-c-drive.ps1"







