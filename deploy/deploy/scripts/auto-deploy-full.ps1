# Полностью автоматическое развертывание с использованием учетных данных
# Запустите: .\deploy\scripts\auto-deploy-full.ps1

param(
    [string]$ConfigFile = "deploy\config\server-credentials.json"
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Полностью автоматическое развертывание на сервер" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Проверка конфигурации
if (-not (Test-Path $ConfigFile)) {
    Write-Host "❌ Файл конфигурации не найден: $ConfigFile" -ForegroundColor Red
    Write-Host ""
    Write-Host "Создайте файл на основе server-credentials.json.example:" -ForegroundColor Yellow
    Write-Host "1. Скопируйте: deploy\config\server-credentials.json.example" -ForegroundColor Gray
    Write-Host "2. Переименуйте в: deploy\config\server-credentials.json" -ForegroundColor Gray
    Write-Host "3. Заполните пароль сервера" -ForegroundColor Gray
    exit 1
}

# Загрузка конфигурации
$config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
$serverHost = $config.server.host
$serverHostname = $config.server.hostname
$serverUser = $config.server.user
$serverPassword = $config.server.password
$serverPort = $config.server.port

Write-Host "📋 Конфигурация сервера:" -ForegroundColor Yellow
Write-Host "   Host: $serverHost" -ForegroundColor Gray
Write-Host "   User: $serverUser" -ForegroundColor Gray
Write-Host ""

# Проверка SSH подключения
Write-Host "[1/5] Проверка SSH подключения..." -ForegroundColor Yellow
$testConnection = ssh -o ConnectTimeout=5 $serverHost "echo 'connected'" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  SSH подключение требует настройки" -ForegroundColor Yellow
    Write-Host "Запустите сначала: .\deploy\scripts\setup-ssh-auto.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ SSH подключение работает" -ForegroundColor Green
Write-Host ""

# Загрузка файлов проекта
Write-Host "[2/5] Загрузка файлов проекта..." -ForegroundColor Yellow
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $projectRoot

$tempZip = "$env:TEMP\media-lab-deploy-$(Get-Date -Format 'yyyyMMddHHmmss').zip"
if (Test-Path $tempZip) { Remove-Item $tempZip -Force }

# Создание архива
$excludeItems = @("node_modules", ".git", "__pycache__", ".venv", "venv", "*.pyc", "deploy_temp.zip", ".env")
Get-ChildItem -Exclude $excludeItems | 
    Where-Object { $_.Name -notin $excludeItems } | 
    Compress-Archive -DestinationPath $tempZip -Force

Write-Host "Архив создан: $tempZip" -ForegroundColor Gray

# Загрузка на сервер
scp $tempZip "${serverHost}:/tmp/media-lab.zip"
Remove-Item $tempZip -Force

Write-Host "✅ Файлы загружены" -ForegroundColor Green
Write-Host ""

# Распаковка на сервере
Write-Host "[3/5] Распаковка на сервере..." -ForegroundColor Yellow
ssh $serverHost @"
cd /opt/media-lab
unzip -q -o /tmp/media-lab.zip -d /opt/media-lab
rm /tmp/media-lab.zip
chmod +x deploy/scripts/*.sh deploy/monitoring/*.sh 2>/dev/null || true
cp deploy/env.prod.example .env 2>/dev/null || true
echo 'Files extracted'
"@

Write-Host "✅ Файлы распакованы" -ForegroundColor Green
Write-Host ""

# Настройка окружения
Write-Host "[4/5] Настройка окружения..." -ForegroundColor Yellow
ssh $serverHost "cd /opt/media-lab && mkdir -p media/{images,edits,face_swap,videos} && chmod -R 755 media"
Write-Host "✅ Окружение настроено" -ForegroundColor Green
Write-Host ""

# Проверка
Write-Host "[5/5] Проверка установки..." -ForegroundColor Yellow
ssh $serverHost "cd /opt/media-lab && ls -la deploy/scripts/ | head -5"
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ Развертывание завершено!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Следующие шаги:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Настройте .env файл:" -ForegroundColor White
Write-Host "   ssh $serverHost 'cd /opt/media-lab && nano .env'" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Запустите сервисы:" -ForegroundColor White
Write-Host "   ssh $serverHost 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
Write-Host ""

