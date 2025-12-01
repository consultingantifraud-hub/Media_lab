# Безопасная очистка крупных файлов
# Запустите от имени администратора для полной очистки

Write-Host "=== Безопасная очистка крупных файлов ===" -ForegroundColor Cyan
Write-Host ""

# 1. Очистка Cursor кэша
Write-Host "1. Очистка Cursor кэша..." -ForegroundColor Yellow
$cursorCache = "C:\Users\Колесник Дмитрий\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
$cursorBackup = "C:\Users\Колесник Дмитрий\AppData\Roaming\Cursor\User\globalStorage\state.vscdb.backup"

$freed = 0
if (Test-Path $cursorCache) {
    $size = (Get-Item $cursorCache).Length / 1MB
    Remove-Item $cursorCache -Force -ErrorAction SilentlyContinue
    $freed += $size
    Write-Host "   ✓ Удален state.vscdb ($([math]::Round($size, 2)) MB)" -ForegroundColor Green
}
if (Test-Path $cursorBackup) {
    $size = (Get-Item $cursorBackup).Length / 1MB
    Remove-Item $cursorBackup -Force -ErrorAction SilentlyContinue
    $freed += $size
    Write-Host "   ✓ Удален state.vscdb.backup ($([math]::Round($size, 2)) MB)" -ForegroundColor Green
}
if ($freed -eq 0) {
    Write-Host "   ✓ Кэш уже очищен" -ForegroundColor Green
} else {
    Write-Host "   Всего освобождено: $([math]::Round($freed, 2)) MB (~$([math]::Round($freed/1024, 2)) GB)" -ForegroundColor Green
}
Write-Host ""

# 2. Запуск очистки диска Windows
Write-Host "2. Запуск Windows Disk Cleanup..." -ForegroundColor Yellow
Write-Host "   Откроется окно 'Очистка диска'" -ForegroundColor Gray
Write-Host "   Выберите:" -ForegroundColor Gray
Write-Host "     • Временные файлы установки Windows" -ForegroundColor White
Write-Host "     • Файлы установщика Windows" -ForegroundColor White
Write-Host "     • Временные файлы" -ForegroundColor White
Write-Host ""
Start-Process cleanmgr -ArgumentList "/d C:"
Write-Host "   ✓ Окно открыто" -ForegroundColor Green
Write-Host ""

# 3. Отключение гибернации (опционально)
Write-Host "3. Отключение гибернации (освободит ~3 GB)..." -ForegroundColor Yellow
$hiberfil = "C:\hiberfil.sys"
if (Test-Path $hiberfil) {
    $size = (Get-Item $hiberfil).Length / 1GB
    Write-Host "   Текущий размер: $([math]::Round($size, 2)) GB" -ForegroundColor White
    Write-Host "   Для отключения выполните (от админа):" -ForegroundColor Gray
    Write-Host "   powercfg /hibernate off" -ForegroundColor White
    Write-Host "   ⚠ Это отключит режим гибернации Windows" -ForegroundColor Yellow
} else {
    Write-Host "   ✓ Гибернация уже отключена" -ForegroundColor Green
}
Write-Host ""

Write-Host "=== Очистка завершена! ===" -ForegroundColor Cyan
Write-Host "Проверьте результаты в окне 'Очистка диска'" -ForegroundColor Yellow




