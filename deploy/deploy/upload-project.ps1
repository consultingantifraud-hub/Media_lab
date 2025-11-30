# Скрипт загрузки проекта на сервер
# Запустите: .\deploy\upload-project.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio"
)

Write-Host "📦 Загрузка проекта на сервер..." -ForegroundColor Cyan
Write-Host ""

# Переход в корневую директорию проекта
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Директория проекта: $projectRoot" -ForegroundColor Gray
Write-Host ""

# Создание архива проекта
Write-Host "[1/3] Создание архива проекта..." -ForegroundColor Yellow
$tempZip = "$env:TEMP\media-lab-deploy.zip"
if (Test-Path $tempZip) { 
    Remove-Item $tempZip -Force 
}

# Исключаем ненужные директории и файлы
$excludeItems = @("node_modules", ".git", "__pycache__", ".venv", "venv", "*.pyc", "deploy_temp.zip", ".env")

Get-ChildItem -Path $projectRoot -Exclude $excludeItems | 
    Where-Object { 
        $_.Name -notin $excludeItems -and 
        $_.Name -ne "deploy_temp.zip" 
    } | 
    Compress-Archive -DestinationPath $tempZip -Force

Write-Host "✅ Архив создан: $tempZip" -ForegroundColor Green
Write-Host ""

# Загрузка архива на сервер
Write-Host "[2/3] Загрузка архива на сервер..." -ForegroundColor Yellow
Write-Host "⚠️  Введите пароль для пользователя root (потребуется один раз)" -ForegroundColor Yellow
Write-Host ""

scp $tempZip "${ServerName}:/tmp/media-lab.zip"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Архив загружен на сервер" -ForegroundColor Green
    Write-Host ""
    
    # Распаковка на сервере
    Write-Host "[3/3] Распаковка и настройка на сервере..." -ForegroundColor Yellow
    
    $unpackCmd = @"
cd /opt/media-lab
unzip -q -o /tmp/media-lab.zip -d /opt/media-lab
rm /tmp/media-lab.zip
chmod +x deploy/scripts/*.sh deploy/monitoring/*.sh 2>/dev/null || true
cp deploy/env.prod.example .env 2>/dev/null || true
echo '✅ Файлы распакованы и настроены'
"@
    
    ssh $ServerName $unpackCmd
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Проект успешно загружен на сервер!" -ForegroundColor Green
        Write-Host ""
        Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host "✅ Загрузка завершена!" -ForegroundColor Green
        Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "📝 Следующие шаги:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "1. Настройте .env файл на сервере:" -ForegroundColor White
        Write-Host "   ssh $ServerName 'cd /opt/media-lab && nano .env'" -ForegroundColor Gray
        Write-Host ""
        Write-Host "2. Запустите сервисы:" -ForegroundColor White
        Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "❌ Ошибка при распаковке на сервере" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Ошибка при загрузке архива" -ForegroundColor Red
}

# Удаление временного архива
if (Test-Path $tempZip) {
    Remove-Item $tempZip -Force
    Write-Host "Временный архив удален" -ForegroundColor Gray
}

