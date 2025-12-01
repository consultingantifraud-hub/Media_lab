# Прямое сжатие VHDX через PowerShell (без diskpart)
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

$userProfile = $env:USERPROFILE
$vhdxPath = Join-Path $userProfile "AppData\Local\Docker\wsl\disk\docker_data.vhdx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Direct VHDX Compression" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем права администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required!" -ForegroundColor Red
    pause
    exit 1
}

# Проверяем наличие файла
if (-not (Test-Path $vhdxPath)) {
    Write-Host "Error: VHDX file not found" -ForegroundColor Red
    pause
    exit 1
}

$beforeSize = (Get-Item $vhdxPath).Length
Write-Host "Current size: $([math]::Round($beforeSize/1GB, 2)) GB" -ForegroundColor Yellow
Write-Host ""

# Останавливаем WSL
Write-Host "[1/2] Shutting down WSL..." -ForegroundColor Yellow
wsl --shutdown 2>&1 | Out-Null
Start-Sleep -Seconds 3
Write-Host "  Done" -ForegroundColor Green

# Используем diskpart через cmd с правильной кодировкой
Write-Host "[2/2] Compressing VHDX..." -ForegroundColor Yellow
Write-Host "  This may take 5-15 minutes..." -ForegroundColor Gray
Write-Host ""

# Создаем скрипт для diskpart в папке без кириллицы
$scriptDir = "C:\temp"
if (-not (Test-Path $scriptDir)) {
    New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null
}

$scriptFile = Join-Path $scriptDir "compact.txt"

# Используем UNC путь или другой метод
# Пробуем использовать переменную окружения для пути
$diskpartCmd = @"
select vdisk file="$vhdxPath"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@

# Сохраняем в файл с UTF-8 BOM для правильной обработки кириллицы
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($scriptFile, $diskpartCmd, $utf8NoBom)

Write-Host "  Running diskpart..." -ForegroundColor Gray

# Запускаем diskpart через cmd с правильной кодировкой
$output = cmd /c "chcp 65001 >nul && diskpart /s `"$scriptFile`"" 2>&1

Write-Host ""
Write-Host "Diskpart output:" -ForegroundColor Cyan
Write-Host $output

# Удаляем временный файл
Remove-Item $scriptFile -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 3

# Проверяем результат
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

if ($freedSpace -gt 100MB) {
    Write-Host "Success! File compressed." -ForegroundColor Green
} else {
    Write-Host "File size unchanged." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: Use Windows built-in tool:" -ForegroundColor Cyan
    Write-Host "1. Open PowerShell as Administrator" -ForegroundColor White
    Write-Host "2. Run: Optimize-VHD -Path `"$vhdxPath`" -Mode Full" -ForegroundColor White
    Write-Host "   (Requires Hyper-V feature)" -ForegroundColor Gray
}

Write-Host ""
pause








