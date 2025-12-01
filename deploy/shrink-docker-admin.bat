@echo off
echo ========================================
echo Сжатие виртуального диска Docker
echo ========================================
echo.
echo ВНИМАНИЕ: Этот скрипт нужно запустить от имени АДМИНИСТРАТОРА!
echo.
pause

echo Шаг 1: Остановка Docker Desktop...
taskkill /F /IM "Docker Desktop.exe" 2>nul
timeout /t 5 /nobreak >nul

echo Шаг 2: Остановка WSL...
wsl --shutdown
timeout /t 5 /nobreak >nul

echo Шаг 3: Сжатие VHDX диска...
echo.
echo Выполняются команды diskpart...
echo.

(
echo select vdisk file="C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
echo attach vdisk readonly
echo compact vdisk
echo detach vdisk
echo exit
) | diskpart

echo.
echo Шаг 4: Проверка размера диска...
for %%F in ("C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx") do (
    set size=%%~zF
    set /a sizeGB=!size!/1073741824
    echo Размер диска: !sizeGB! GB
)

echo.
echo Шаг 5: Запуск Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"

echo.
echo ========================================
echo Сжатие завершено!
echo ========================================
pause




