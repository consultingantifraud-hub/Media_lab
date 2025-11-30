# Скрипт для удаления раздела Ubuntu (47.27 ГБ)
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ubuntu Partition Removal Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем права администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required!" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator" -ForegroundColor Yellow
    pause
    exit 1
}

# Находим раздел Ubuntu (47.27 ГБ, без буквы диска)
$ubuntuPartition = Get-Partition | Where-Object {
    $_.Size -gt 40GB -and 
    $_.Size -lt 50GB -and 
    [string]::IsNullOrEmpty($_.DriveLetter)
}

if (-not $ubuntuPartition) {
    Write-Host "Ubuntu partition not found!" -ForegroundColor Red
    Write-Host "Looking for partitions without drive letters..." -ForegroundColor Yellow
    
    $allPartitions = Get-Partition | Where-Object { [string]::IsNullOrEmpty($_.DriveLetter) }
    if ($allPartitions) {
        Write-Host ""
        Write-Host "Found partitions without drive letters:" -ForegroundColor Yellow
        $allPartitions | ForEach-Object {
            $sizeGB = [math]::Round($_.Size / 1GB, 2)
            Write-Host "  Partition $($_.PartitionNumber): $sizeGB GB (Type: $($_.Type))" -ForegroundColor Gray
        }
    }
    pause
    exit 1
}

$partitionNumber = $ubuntuPartition.PartitionNumber
$sizeGB = [math]::Round($ubuntuPartition.Size / 1GB, 2)

Write-Host "Found Ubuntu partition:" -ForegroundColor Green
Write-Host "  Partition Number: $partitionNumber" -ForegroundColor White
Write-Host "  Size: $sizeGB GB" -ForegroundColor White
Write-Host "  Type: $($ubuntuPartition.Type)" -ForegroundColor White
Write-Host "  Drive Letter: (none)" -ForegroundColor White
Write-Host ""

# Показываем текущее состояние дисков
Write-Host "Current disk layout:" -ForegroundColor Cyan
Get-Partition | Select-Object PartitionNumber, DriveLetter, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, Type | Format-Table -AutoSize
Write-Host ""

# Предупреждение
Write-Host "WARNING: This will permanently delete the Ubuntu partition!" -ForegroundColor Red
Write-Host "All data on this partition will be lost!" -ForegroundColor Red
Write-Host ""
Write-Host "After deletion, you can:" -ForegroundColor Yellow
Write-Host "  1. Extend drive C: to use this space" -ForegroundColor White
Write-Host "  2. Leave it as unallocated space" -ForegroundColor White
Write-Host ""

$confirmation = Read-Host "Are you sure you want to delete this partition? (YES to confirm)"
if ($confirmation -ne "YES") {
    Write-Host "Operation cancelled." -ForegroundColor Yellow
    pause
    exit 0
}

Write-Host ""
Write-Host "Deleting partition $partitionNumber..." -ForegroundColor Yellow

try {
    # Удаляем раздел
    Remove-Partition -PartitionNumber $partitionNumber -Confirm:$false
    
    Write-Host "  Partition deleted successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Показываем новое состояние
    Write-Host "New disk layout:" -ForegroundColor Cyan
    Get-Partition | Select-Object PartitionNumber, DriveLetter, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, Type | Format-Table -AutoSize
    Write-Host ""
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Success! Ubuntu partition deleted." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Freed space: $sizeGB GB" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To extend drive C: with this space:" -ForegroundColor Yellow
    Write-Host "  1. Open Disk Management (diskmgmt.msc)" -ForegroundColor White
    Write-Host "  2. Right-click on C: drive" -ForegroundColor White
    Write-Host "  3. Select 'Extend Volume'" -ForegroundColor White
    Write-Host ""
    
} catch {
    Write-Host "Error deleting partition: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "You may need to:" -ForegroundColor Yellow
    Write-Host "  1. Use Disk Management GUI (diskmgmt.msc)" -ForegroundColor White
    Write-Host "  2. Right-click the partition" -ForegroundColor White
    Write-Host "  3. Select 'Delete Volume'" -ForegroundColor White
}

Write-Host ""
pause







