@echo off
REM Скрипт для очистки системных файлов (требует прав администратора)
echo ========================================
echo Очистка системных файлов Windows
echo ========================================
echo.
echo ВНИМАНИЕ: Запустите от имени АДМИНИСТРАТОРА!
echo.
pause

echo 1. Очистка точек восстановления (System Volume Information)...
vssadmin delete shadows /all
echo.

echo 2. Очистка Windows Installer кэша...
DISM /online /Cleanup-Image /StartComponentCleanup /ResetBase
echo.

echo 3. Запуск расширенной очистки диска...
cleanmgr /d C: /sageset:1
echo.
echo В открывшемся окне отметьте ВСЕ пункты и нажмите ОК
pause

cleanmgr /d C: /sagerun:1
echo.

echo ========================================
echo Очистка завершена!
echo ========================================
pause




