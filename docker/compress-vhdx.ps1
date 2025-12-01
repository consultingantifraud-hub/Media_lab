# Скрипт для сжатия docker_data.vhdx файла
# ТРЕБУЕТ: Docker Desktop должен быть полностью остановлен!

$userProfile = $env:USERPROFILE
$vhdxPath = Join-Path $userProfile "AppData\Local\Docker\wsl\disk\docker_data.vhdx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VHDX Compression Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем наличие файла
if (-not (Test-Path $vhdxPath)) {
    Write-Host "Error: VHDX file not found at: $vhdxPath" -ForegroundColor Red
    exit 1
}

# Показываем текущий размер
$beforeSize = (Get-Item $vhdxPath).Length
Write-Host "Current size: $([math]::Round($beforeSize/1GB, 2)) GB" -ForegroundColor Yellow
Write-Host ""

# Проверяем, не используется ли файл
$dockerProcesses = Get-Process -Name "*docker*","*wsl*","*com.docker*" -ErrorAction SilentlyContinue
if ($dockerProcesses) {
    Write-Host "WARNING: Docker processes are still running!" -ForegroundColor Red
    Write-Host "Please stop Docker Desktop completely before compressing." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Running processes:" -ForegroundColor Yellow
    $dockerProcesses | Select-Object ProcessName, Id | Format-Table
    Write-Host ""
    Write-Host "To stop Docker Desktop:" -ForegroundColor Cyan
    Write-Host "1. Right-click Docker Desktop icon in system tray" -ForegroundColor White
    Write-Host "2. Click 'Quit Docker Desktop'" -ForegroundColor White
    Write-Host "3. Wait until all processes stop" -ForegroundColor White
    Write-Host "4. Run this script again" -ForegroundColor White
    exit 1
}

Write-Host "Docker Desktop is stopped. Proceeding with compression..." -ForegroundColor Green
Write-Host ""

# Останавливаем WSL полностью
Write-Host "[1/3] Shutting down WSL..." -ForegroundColor Yellow
wsl --shutdown 2>&1 | Out-Null
Start-Sleep -Seconds 3
Write-Host "  WSL shut down" -ForegroundColor Green

# Используем diskpart для сжатия
Write-Host "[2/3] Compressing VHDX file (this may take several minutes)..." -ForegroundColor Yellow
$diskpartScript = @"
select vdisk file="$vhdxPath"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@

try {
    $result = $diskpartScript | diskpart 2>&1
    if ($LASTEXITCODE -eq 0 -or $result -match "successfully") {
        Write-Host "  Compression completed" -ForegroundColor Green
    } else {
        Write-Host "  Compression may have completed (checking file size...)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Error during compression: $_" -ForegroundColor Red
}

Start-Sleep -Seconds 2

# Проверяем новый размер
Write-Host "[3/3] Checking new file size..." -ForegroundColor Yellow
$afterSize = (Get-Item $vhdxPath).Length
$freedSpace = $beforeSize - $afterSize

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Results:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Before: $([math]::Round($beforeSize/1GB, 2)) GB" -ForegroundColor Yellow
Write-Host "After:  $([math]::Round($afterSize/1GB, 2)) GB" -ForegroundColor Green
Write-Host "Freed:  $([math]::Round($freedSpace/1GB, 2)) GB" -ForegroundColor Cyan
Write-Host ""

if ($freedSpace -gt 0) {
    Write-Host "Success! File compressed." -ForegroundColor Green
} else {
    Write-Host "Note: File size unchanged. This may happen if:" -ForegroundColor Yellow
    Write-Host "  - File is already optimized" -ForegroundColor Gray
    Write-Host "  - File is still in use by another process" -ForegroundColor Gray
    Write-Host "  - VHDX format doesn't support compression" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Try:" -ForegroundColor Cyan
    Write-Host "  1. Restart your computer" -ForegroundColor White
    Write-Host "  2. Then run this script again" -ForegroundColor White
}

Write-Host ""

