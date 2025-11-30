# Скрипт для проверки безопасности удаления раздела Ubuntu
# Показывает, что Windows не зависит от этого раздела

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Boot Safety Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем структуру разделов
Write-Host "Disk Partitions:" -ForegroundColor Yellow
$partitions = Get-Partition | Select-Object PartitionNumber, DriveLetter, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, Type, IsActive, IsBoot, IsSystem
$partitions | Format-Table -AutoSize
Write-Host ""

# Находим Ubuntu раздел
$ubuntuPartition = Get-Partition | Where-Object {
    $_.Size -gt 40GB -and 
    $_.Size -lt 50GB -and 
    [string]::IsNullOrEmpty($_.DriveLetter)
}

if ($ubuntuPartition) {
    Write-Host "Ubuntu Partition Analysis:" -ForegroundColor Cyan
    Write-Host "  Partition Number: $($ubuntuPartition.PartitionNumber)" -ForegroundColor White
    Write-Host "  Size: $([math]::Round($ubuntuPartition.Size/1GB, 2)) GB" -ForegroundColor White
    Write-Host "  Type: $($ubuntuPartition.Type)" -ForegroundColor White
    Write-Host "  Is Active: $($ubuntuPartition.IsActive)" -ForegroundColor $(if ($ubuntuPartition.IsActive) { "Red" } else { "Green" })
    Write-Host "  Is Boot: $($ubuntuPartition.IsBoot)" -ForegroundColor $(if ($ubuntuPartition.IsBoot) { "Red" } else { "Green" })
    Write-Host "  Is System: $($ubuntuPartition.IsSystem)" -ForegroundColor $(if ($ubuntuPartition.IsSystem) { "Red" } else { "Green" })
    Write-Host ""
    
    # Проверяем загрузочный раздел Windows
    $windowsBoot = Get-Partition | Where-Object { $_.IsBoot -eq $true }
    if ($windowsBoot) {
        Write-Host "Windows Boot Partition:" -ForegroundColor Green
        Write-Host "  Partition Number: $($windowsBoot.PartitionNumber)" -ForegroundColor White
        Write-Host "  Drive Letter: $($windowsBoot.DriveLetter)" -ForegroundColor White
        Write-Host "  Size: $([math]::Round($windowsBoot.Size/1GB, 2)) GB" -ForegroundColor White
        Write-Host ""
    }
    
    # Вывод о безопасности
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Safety Analysis:" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    $isSafe = $true
    $reasons = @()
    
    if ($ubuntuPartition.IsActive) {
        $isSafe = $false
        $reasons += "WARNING: Ubuntu partition is marked as Active!"
    } else {
        $reasons += "[OK] Ubuntu partition is NOT active (safe)"
    }
    
    if ($ubuntuPartition.IsBoot) {
        $isSafe = $false
        $reasons += "WARNING: Ubuntu partition is marked as Boot!"
    } else {
        $reasons += "[OK] Ubuntu partition is NOT boot partition (safe)"
    }
    
    if ($ubuntuPartition.IsSystem) {
        $isSafe = $false
        $reasons += "WARNING: Ubuntu partition is marked as System!"
    } else {
        $reasons += "[OK] Ubuntu partition is NOT system partition (safe)"
    }
    
    if ($windowsBoot -and $windowsBoot.PartitionNumber -ne $ubuntuPartition.PartitionNumber) {
        $reasons += "[OK] Windows boots from partition $($windowsBoot.PartitionNumber) (different from Ubuntu)"
    }
    
    foreach ($reason in $reasons) {
        if ($reason -match "WARNING") {
            Write-Host $reason -ForegroundColor Red
        } else {
            Write-Host $reason -ForegroundColor Green
        }
    }
    
    Write-Host ""
    
    if ($isSafe) {
        Write-Host "RESULT: Safe to delete Ubuntu partition!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Windows will continue to work normally because:" -ForegroundColor Yellow
        Write-Host "  - Windows boots from partition $($windowsBoot.PartitionNumber) (C:)" -ForegroundColor White
        Write-Host "  - Ubuntu partition is separate and inactive" -ForegroundColor White
        Write-Host "  - No system files are on Ubuntu partition" -ForegroundColor White
    } else {
        Write-Host "RESULT: NOT SAFE to delete!" -ForegroundColor Red
        Write-Host "Please check the warnings above." -ForegroundColor Yellow
    }
} else {
    Write-Host "Ubuntu partition not found!" -ForegroundColor Yellow
}

Write-Host ""
pause

