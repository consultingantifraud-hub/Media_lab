@echo off
REM Скрипт для удаления раздела Ubuntu
REM ВАЖНО: Запустите от имени АДМИНИСТРАТОРА!
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0remove-ubuntu-partition.ps1"







