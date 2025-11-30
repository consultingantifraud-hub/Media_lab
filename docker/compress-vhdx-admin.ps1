# Скрипт для сжатия docker_data.vhdx файла
# ТРЕБУЕТ: Запуск от имени АДМИНИСТРАТОРА!

$userProfile = $env:USERPROFILE
$vhdxPath = Join-Path $userProfile "AppData\Local\Docker\wsl\disk\docker_data.vhdx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VHDX Compression Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем права администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please:" -ForegroundColor Yellow
    Write-Host "1. Right-click PowerShell" -ForegroundColor White
    Write-Host "2. Select 'Run as Administrator'" -ForegroundColor White
    Write-Host "3. Run this script again" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

# Проверяем наличие файла
if (-not (Test-Path $vhdxPath)) {
    Write-Host "Error: VHDX file not found at: $vhdxPath" -ForegroundColor Red
    pause
    exit 1
}

# Показываем текущий размер
$beforeSize = (Get-Item $vhdxPath).Length
Write-Host "Current size: $([math]::Round($beforeSize/1GB, 2)) GB" -ForegroundColor Yellow
Write-Host ""

# Останавливаем WSL
Write-Host "[1/3] Shutting down WSL..." -ForegroundColor Yellow
wsl --shutdown 2>&1 | Out-Null
Start-Sleep -Seconds 3
Write-Host "  WSL shut down" -ForegroundColor Green

# Используем diskpart для сжатия
Write-Host "[2/3] Compressing VHDX file..." -ForegroundColor Yellow
Write-Host "  This may take 5-15 minutes, please wait..." -ForegroundColor Gray
Write-Host ""

# Создаем символическую ссылку без кириллицы для diskpart
# Diskpart не поддерживает кириллицу в путях
# Используем C:\temp вместо TEMP (который может содержать кириллицу)
Write-Host "  Creating temporary symbolic link..." -ForegroundColor Gray

# Создаем папку C:\temp если её нет
$tempDir = "C:\temp"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

$tempLink = Join-Path $tempDir "docker_data_link.vhdx"

# Удаляем старую ссылку если есть
if (Test-Path $tempLink) {
    Remove-Item $tempLink -Force -ErrorAction SilentlyContinue
}

try {
    # Создаем символическую ссылку
    cmd /c "mklink `"$tempLink`" `"$vhdxPath`"" | Out-Null
    Write-Host "  Using link: $tempLink" -ForegroundColor Gray
    Write-Host ""
    
    # Создаем временный скрипт для diskpart
    $tempScript = Join-Path $env:TEMP "diskpart_compress.txt"
    $diskpartCommands = @"
select vdisk file="$tempLink"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartCommands | Out-File -FilePath $tempScript -Encoding ASCII -Force
    
    Write-Host "  Running diskpart..." -ForegroundColor Gray
    $diskpartScript = "diskpart /s `"$tempScript`""
} catch {
    Write-Host "  Error creating link: $_" -ForegroundColor Red
    Write-Host "  Trying direct path..." -ForegroundColor Yellow
    $tempLink = $vhdxPath
    $tempScript = Join-Path $env:TEMP "diskpart_compress.txt"
    $diskpartCommands = @"
select vdisk file="$tempLink"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartCommands | Out-File -FilePath $tempScript -Encoding ASCII -Force
    $diskpartScript = "diskpart /s `"$tempScript`""
}

try {
    $result = Invoke-Expression $diskpartScript 2>&1
    Write-Host $result
    
    if ($result -match "successfully" -or $result -match "100 percent" -or $result -match "100%") {
        Write-Host "  Compression completed successfully" -ForegroundColor Green
    } else {
        Write-Host "  Compression completed (checking file size...)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Error during compression: $_" -ForegroundColor Red
} finally {
    # Удаляем временные файлы
    if (Test-Path $tempScript) {
        Remove-Item $tempScript -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $tempLink) {
        Remove-Item $tempLink -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 2

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

if ($freedSpace -gt 100MB) {
    Write-Host "Success! File compressed and space freed." -ForegroundColor Green
} elseif ($freedSpace -gt 0) {
    Write-Host "File compressed slightly. Some space freed." -ForegroundColor Yellow
} else {
    Write-Host "File size unchanged. Possible reasons:" -ForegroundColor Yellow
    Write-Host "  - File is already optimized" -ForegroundColor Gray
    Write-Host "  - File is still in use by another process" -ForegroundColor Gray
    Write-Host "  - Try restarting your computer and run again" -ForegroundColor Gray
}

Write-Host ""
pause

