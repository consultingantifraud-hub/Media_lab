# Альтернативный метод сжатия VHDX через WSL
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

$userProfile = $env:USERPROFILE
$vhdxPath = Join-Path $userProfile "AppData\Local\Docker\wsl\disk\docker_data.vhdx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Alternative VHDX Compression Method" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем права администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script requires Administrator privileges!" -ForegroundColor Red
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

Write-Host "This method uses diskpart with a workaround for Cyrillic paths." -ForegroundColor Cyan
Write-Host ""

# Останавливаем WSL
Write-Host "[1/3] Shutting down WSL..." -ForegroundColor Yellow
wsl --shutdown 2>&1 | Out-Null
Start-Sleep -Seconds 3
Write-Host "  WSL shut down" -ForegroundColor Green

# Используем diskpart через cmd с правильной кодировкой
Write-Host "[2/3] Compressing VHDX file..." -ForegroundColor Yellow
Write-Host "  This may take 5-15 minutes..." -ForegroundColor Gray
Write-Host ""

# Создаем папку C:\temp если её нет
$tempDir = "C:\temp"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

$tempLink = Join-Path $tempDir "docker_data_link.vhdx"
$tempScript = Join-Path $tempDir "diskpart_compress.txt"

# Удаляем старые файлы
if (Test-Path $tempLink) {
    Remove-Item $tempLink -Force -ErrorAction SilentlyContinue
}

# Создаем символическую ссылку
Write-Host "  Creating symbolic link..." -ForegroundColor Gray
$linkResult = cmd /c "mklink `"$tempLink`" `"$vhdxPath`"" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Error creating link: $linkResult" -ForegroundColor Red
    Write-Host "  Trying direct method..." -ForegroundColor Yellow
    
    # Пробуем использовать путь напрямую через chcp для правильной кодировки
    $diskpartCommands = @"
select vdisk file="$vhdxPath"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartCommands | Out-File -FilePath $tempScript -Encoding UTF8 -Force
    
    Write-Host "  Running diskpart with UTF-8 encoding..." -ForegroundColor Gray
    chcp 65001 | Out-Null
    $result = cmd /c "diskpart /s `"$tempScript`"" 2>&1
} else {
    Write-Host "  Link created successfully" -ForegroundColor Green
    
    # Создаем скрипт для diskpart
    $diskpartCommands = @"
select vdisk file="$tempLink"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartCommands | Out-File -FilePath $tempScript -Encoding ASCII -Force
    
    Write-Host "  Running diskpart..." -ForegroundColor Gray
    $result = cmd /c "diskpart /s `"$tempScript`"" 2>&1
}

Write-Host ""
Write-Host "Diskpart output:" -ForegroundColor Cyan
Write-Host $result

Start-Sleep -Seconds 3

# Проверяем новый размер
Write-Host ""
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

# Очистка
if (Test-Path $tempLink) {
    Remove-Item $tempLink -Force -ErrorAction SilentlyContinue
}
if (Test-Path $tempScript) {
    Remove-Item $tempScript -Force -ErrorAction SilentlyContinue
}

if ($freedSpace -gt 100MB) {
    Write-Host "Success! File compressed." -ForegroundColor Green
} else {
    Write-Host "Note: File size unchanged." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Possible solutions:" -ForegroundColor Cyan
    Write-Host "1. The VHDX file may already be optimized" -ForegroundColor White
    Write-Host "2. Try using Windows Disk Management GUI:" -ForegroundColor White
    Write-Host "   - Open 'Disk Management' (diskmgmt.msc)" -ForegroundColor Gray
    Write-Host "   - Action > Attach VHD > Select docker_data.vhdx" -ForegroundColor Gray
    Write-Host "   - Right-click > Compact" -ForegroundColor Gray
    Write-Host "3. Or use third-party tools like 7-Zip to compress the file" -ForegroundColor White
}

Write-Host ""
pause







