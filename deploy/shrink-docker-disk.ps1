# Скрипт для сжатия виртуального диска Docker в Windows
# Освобождает место на локальном диске

Write-Host "=== Сжатие виртуального диска Docker ===" -ForegroundColor Cyan
Write-Host ""

# Шаг 1: Остановка Docker Desktop
Write-Host "1. Остановка Docker Desktop..." -ForegroundColor Yellow
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Write-Host "✓ Docker Desktop остановлен" -ForegroundColor Green
Write-Host ""

# Шаг 2: Остановка WSL
Write-Host "2. Остановка WSL..." -ForegroundColor Yellow
wsl --shutdown
Start-Sleep -Seconds 3
Write-Host "✓ WSL остановлен" -ForegroundColor Green
Write-Host ""

# Шаг 3: Сжатие виртуального диска Docker
Write-Host "3. Сжатие виртуального диска Docker..." -ForegroundColor Yellow
$diskPath = "$env:LOCALAPPDATA\Docker\wsl\data\ext4.vhdx"
if (Test-Path $diskPath) {
    Write-Host "Найден диск: $diskPath" -ForegroundColor Gray
    Write-Host "Запуск оптимизации диска..." -ForegroundColor Gray
    
    # Используем diskpart для сжатия VHDX
    $diskpartScript = @"
select vdisk file="$diskPath"
attach vdisk readonly
compact vdisk
detach vdisk
"@
    
    $diskpartScript | diskpart
    Write-Host "✓ Диск сжат" -ForegroundColor Green
} else {
    Write-Host "Диск не найден по пути: $diskPath" -ForegroundColor Red
    Write-Host "Попробуйте найти диск вручную:" -ForegroundColor Yellow
    Get-ChildItem "$env:LOCALAPPDATA\Docker\wsl" -Recurse -Filter "*.vhdx" | Select-Object FullName, @{Name="SizeGB";Expression={[math]::Round($_.Length/1GB,2)}}
}
Write-Host ""

# Шаг 4: Запуск Docker Desktop
Write-Host "4. Запуск Docker Desktop..." -ForegroundColor Yellow
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
Write-Host "✓ Docker Desktop запущен" -ForegroundColor Green
Write-Host ""

Write-Host "=== Сжатие завершено! ===" -ForegroundColor Cyan
Write-Host "Проверьте размер диска в Docker Desktop -> Settings -> Resources" -ForegroundColor Yellow




