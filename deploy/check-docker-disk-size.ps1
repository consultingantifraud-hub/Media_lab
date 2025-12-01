# Проверка размера дисков Docker после пересоздания

Write-Host "=== Размер дисков Docker ===" -ForegroundColor Cyan
Write-Host ""

$diskPath = "$env:LOCALAPPDATA\Docker\wsl\disk"
if (Test-Path $diskPath) {
    $disks = Get-ChildItem "$diskPath\*.vhdx" -ErrorAction SilentlyContinue
    if ($disks) {
        $totalSize = 0
        foreach ($disk in $disks) {
            $sizeGB = [math]::Round($disk.Length / 1GB, 2)
            $totalSize += $sizeGB
            Write-Host "$($disk.Name): $sizeGB GB" -ForegroundColor White
        }
        Write-Host ""
        Write-Host "Общий размер: $totalSize GB" -ForegroundColor Yellow
        
        if ($totalSize -lt 5) {
            Write-Host "✓ Отлично! Диск сжат до минимального размера" -ForegroundColor Green
        } elseif ($totalSize -lt 10) {
            Write-Host "✓ Хорошо! Размер значительно уменьшен" -ForegroundColor Green
        } else {
            Write-Host "⚠ Размер все еще большой, возможно нужно подождать еще" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Диски еще не созданы. Подождите, пока Docker Desktop полностью запустится." -ForegroundColor Yellow
    }
} else {
    Write-Host "Папка с дисками не найдена. Docker Desktop может еще не запуститься." -ForegroundColor Red
}

Write-Host ""
Write-Host "Для повторной проверки запустите этот скрипт снова через минуту." -ForegroundColor Gray




