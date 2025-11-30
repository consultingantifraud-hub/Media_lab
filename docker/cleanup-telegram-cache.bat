@echo off
REM Скрипт для очистки кэша Telegram Desktop
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0cleanup-telegram-cache.ps1"
pause







