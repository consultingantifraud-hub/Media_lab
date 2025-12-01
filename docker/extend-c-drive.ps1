# Скрипт для расширения диска C: используя нераспределенное пространство
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Extend C: Drive Script" -ForegroundColor Cyan
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

# Получаем информацию о диске C:
$cDrive = Get-Partition | Where-Object { $_.DriveLetter -eq 'C' }
if (-not $cDrive) {
    Write-Host "Error: C: drive not found!" -ForegroundColor Red
    pause
    exit 1
}

$cVolume = Get-Volume -DriveLetter C
$cSizeBefore = $cVolume.Size
$cFreeBefore = $cVolume.SizeRemaining

Write-Host "Current C: drive status:" -ForegroundColor Yellow
Write-Host "  Size: $([math]::Round($cSizeBefore/1GB, 2)) GB" -ForegroundColor White
Write-Host "  Free: $([math]::Round($cFreeBefore/1GB, 2)) GB" -ForegroundColor White
Write-Host ""

# Проверяем нераспределенное пространство
$unallocated = Get-PartitionSupportedSize -DriveLetter C
if ($unallocated) {
    $maxSize = $unallocated.SizeMax
    $currentSize = $unallocated.SizeMin
    $availableSpace = $maxSize - $currentSize
    $availableSpaceGB = [math]::Round($availableSpace / 1GB, 2)
    
    Write-Host "Available unallocated space: $availableSpaceGB GB" -ForegroundColor Green
    Write-Host ""
    
    if ($availableSpace -gt 0) {
        Write-Host "Extending C: drive..." -ForegroundColor Yellow
        
        try {
            # Расширяем диск C: на максимально доступный размер
            Resize-Partition -DriveLetter C -Size $maxSize
            
            # Проверяем результат
            $cVolumeAfter = Get-Volume -DriveLetter C
            $cSizeAfter = $cVolumeAfter.Size
            $cFreeAfter = $cVolumeAfter.SizeRemaining
            $addedSpace = $cSizeAfter - $cSizeBefore
            
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "Success! C: drive extended." -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host ""
            Write-Host "Before:" -ForegroundColor Yellow
            Write-Host "  Size: $([math]::Round($cSizeBefore/1GB, 2)) GB" -ForegroundColor White
            Write-Host "  Free: $([math]::Round($cFreeBefore/1GB, 2)) GB" -ForegroundColor White
            Write-Host ""
            Write-Host "After:" -ForegroundColor Green
            Write-Host "  Size: $([math]::Round($cSizeAfter/1GB, 2)) GB" -ForegroundColor White
            Write-Host "  Free: $([math]::Round($cFreeAfter/1GB, 2)) GB" -ForegroundColor White
            Write-Host ""
            Write-Host "Added: $([math]::Round($addedSpace/1GB, 2)) GB" -ForegroundColor Cyan
            
        } catch {
            Write-Host "Error extending partition: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "Try using Disk Management GUI:" -ForegroundColor Yellow
            Write-Host "  1. Open diskmgmt.msc" -ForegroundColor White
            Write-Host "  2. Right-click on C: drive" -ForegroundColor White
            Write-Host "  3. Select 'Extend Volume'" -ForegroundColor White
        }
    } else {
        Write-Host "No unallocated space available to extend C: drive." -ForegroundColor Yellow
    }
} else {
    Write-Host "Could not determine available space." -ForegroundColor Yellow
    Write-Host "Try using Disk Management GUI:" -ForegroundColor Yellow
    Write-Host "  1. Open diskmgmt.msc" -ForegroundColor White
    Write-Host "  2. Right-click on C: drive" -ForegroundColor White
    Write-Host "  3. Select 'Extend Volume'" -ForegroundColor White
}

Write-Host ""
pause








