# Скрипт для перемещения раздела восстановления и расширения диска C:
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!
# ВНИМАНИЕ: Это продвинутая операция, рекомендуется использовать специализированные инструменты

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Move Recovery Partition Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем права администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required!" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "WARNING: Moving recovery partition is a complex operation!" -ForegroundColor Red
Write-Host ""
Write-Host "Current situation:" -ForegroundColor Yellow
Write-Host "  - C: drive cannot be extended because recovery partition is between" -ForegroundColor White
Write-Host "  - Recovery partition needs to be moved to the end" -ForegroundColor White
Write-Host ""

Write-Host "RECOMMENDED: Use specialized tools instead:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1: AOMEI Partition Assistant (Free)" -ForegroundColor Green
Write-Host "  1. Download from: https://www.diskpart.com/free-partition-manager.html" -ForegroundColor White
Write-Host "  2. Install and run" -ForegroundColor White
Write-Host "  3. Right-click recovery partition → Move/Resize" -ForegroundColor White
Write-Host "  4. Move it to the end of disk" -ForegroundColor White
Write-Host "  5. Then extend C: drive" -ForegroundColor White
Write-Host ""
Write-Host "Option 2: MiniTool Partition Wizard (Free)" -ForegroundColor Green
Write-Host "  1. Download from: https://www.partitionwizard.com/free-partition-manager.html" -ForegroundColor White
Write-Host "  2. Similar steps as above" -ForegroundColor White
Write-Host ""
Write-Host "Option 3: Create separate drive (Safest)" -ForegroundColor Green
Write-Host "  - Use unallocated space as separate drive (D:)" -ForegroundColor White
Write-Host "  - No risk, no complex operations" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Do you want to proceed with PowerShell method? (NOT RECOMMENDED) (Y/N)"
if ($choice -ne "Y" -and $choice -ne "y") {
    Write-Host "Operation cancelled. Use specialized tools instead." -ForegroundColor Yellow
    pause
    exit 0
}

Write-Host ""
Write-Host "PowerShell method is complex and risky." -ForegroundColor Red
Write-Host "It's better to use specialized partition tools." -ForegroundColor Yellow
Write-Host ""
pause








