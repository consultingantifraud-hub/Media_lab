@echo off
REM Скрипт для сжатия docker_data.vhdx
REM ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

echo ========================================
echo VHDX Compression Script
echo ========================================
echo.

REM Останавливаем WSL
echo [1/3] Shutting down WSL...
wsl --shutdown
timeout /t 3 /nobreak >nul
echo   WSL shut down
echo.

REM Создаем папку C:\temp если её нет
if not exist "C:\temp" mkdir "C:\temp"

REM Создаем скрипт для diskpart
echo [2/3] Creating diskpart script...
set SCRIPT_FILE=C:\temp\compact.txt
set VHDX_PATH=C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx

echo select vdisk file="%VHDX_PATH%" > "%SCRIPT_FILE%"
echo attach vdisk readonly >> "%SCRIPT_FILE%"
echo compact vdisk >> "%SCRIPT_FILE%"
echo detach vdisk >> "%SCRIPT_FILE%"
echo exit >> "%SCRIPT_FILE%"

echo   Script created
echo.

REM Запускаем diskpart
echo [3/3] Running diskpart compression...
echo   This may take 5-15 minutes...
echo.
chcp 65001 >nul
diskpart /s "%SCRIPT_FILE%"

REM Удаляем временный файл
del "%SCRIPT_FILE%" >nul 2>&1

echo.
echo ========================================
echo Compression completed!
echo ========================================
echo.
pause








