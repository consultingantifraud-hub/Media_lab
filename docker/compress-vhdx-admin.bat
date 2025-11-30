@echo off
REM Скрипт для сжатия docker_data.vhdx
REM ВАЖНО: Запустите этот файл от имени АДМИНИСТРАТОРА!
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0compress-vhdx-admin.ps1"







