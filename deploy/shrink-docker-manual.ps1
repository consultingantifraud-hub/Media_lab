# Ручная инструкция по сжатию Docker диска в Windows
# Выполните эти шаги вручную

Write-Host "=== Инструкция по сжатию Docker диска ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "ВАРИАНТ 1: Через Docker Desktop (рекомендуется)" -ForegroundColor Green
Write-Host "1. Откройте Docker Desktop" -ForegroundColor White
Write-Host "2. Перейдите в Settings (шестеренка)" -ForegroundColor White
Write-Host "3. Выберите Resources -> Advanced" -ForegroundColor White
Write-Host "4. Нажмите 'Clean / Purge data' или 'Reclaim space'" -ForegroundColor White
Write-Host "5. Подождите завершения процесса" -ForegroundColor White
Write-Host ""

Write-Host "ВАРИАНТ 2: Через командную строку (требует остановки Docker)" -ForegroundColor Green
Write-Host ""
Write-Host "Выполните команды по порядку:" -ForegroundColor Yellow
Write-Host ""
Write-Host "# 1. Остановите Docker Desktop" -ForegroundColor Gray
Write-Host "Stop-Process -Name 'Docker Desktop' -Force" -ForegroundColor White
Write-Host ""
Write-Host "# 2. Остановите WSL" -ForegroundColor Gray
Write-Host "wsl --shutdown" -ForegroundColor White
Write-Host ""
Write-Host "# 3. Сожмите диск через diskpart" -ForegroundColor Gray
Write-Host "diskpart" -ForegroundColor White
Write-Host "select vdisk file=`"C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx`"" -ForegroundColor White
Write-Host "attach vdisk readonly" -ForegroundColor White
Write-Host "compact vdisk" -ForegroundColor White
Write-Host "detach vdisk" -ForegroundColor White
Write-Host "exit" -ForegroundColor White
Write-Host ""
Write-Host "# 4. Запустите Docker Desktop снова" -ForegroundColor Gray
Write-Host "Start-Process `"`$env:ProgramFiles\Docker\Docker\Docker Desktop.exe`"" -ForegroundColor White
Write-Host ""

Write-Host "ВАРИАНТ 3: Удалить и пересоздать диск (максимальная очистка)" -ForegroundColor Green
Write-Host "ВНИМАНИЕ: Это удалит все локальные данные Docker!" -ForegroundColor Red
Write-Host "1. Docker Desktop -> Settings -> Resources -> Advanced" -ForegroundColor White
Write-Host "2. Нажмите 'Remove all data'" -ForegroundColor White
Write-Host "3. Перезапустите Docker Desktop" -ForegroundColor White
Write-Host ""

Write-Host "Текущий размер диска:" -ForegroundColor Yellow
$diskPath = "C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
if (Test-Path $diskPath) {
    $size = (Get-Item $diskPath).Length / 1GB
    Write-Host "  $([math]::Round($size, 2)) GB" -ForegroundColor White
} else {
    Write-Host "  Диск не найден" -ForegroundColor Red
}




