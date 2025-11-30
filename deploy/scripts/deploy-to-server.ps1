# PowerShell скрипт для автоматического развертывания на сервер
# Использование: .\scripts\deploy-to-server.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio",
    [string]$ServerPath = "/opt/media-lab",
    [string]$LocalPath = ".."
)

Write-Host "🚀 Начало автоматического развертывания на сервер..." -ForegroundColor Cyan

# Проверка SSH ключа
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"
if (-not (Test-Path $sshKeyPath)) {
    Write-Host "❌ SSH ключ не найден!" -ForegroundColor Red
    exit 1
}

# Копирование SSH ключа на сервер (один раз, потребуется пароль)
Write-Host "📋 Копирование SSH ключа на сервер..." -ForegroundColor Yellow
Write-Host "⚠️  Вам нужно будет ввести пароль один раз" -ForegroundColor Yellow
$publicKey = Get-Content $sshKeyPath
$publicKey | ssh $ServerName "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ SSH ключ скопирован успешно!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Не удалось скопировать ключ автоматически. Продолжаем..." -ForegroundColor Yellow
}

# Создание директории на сервере
Write-Host "📁 Создание директории на сервере..." -ForegroundColor Cyan
ssh $ServerName "mkdir -p $ServerPath && chmod 755 $ServerPath"

# Загрузка файлов проекта
Write-Host "📦 Загрузка файлов проекта на сервер..." -ForegroundColor Cyan
$projectRoot = Resolve-Path $LocalPath
Write-Host "Загрузка из: $projectRoot" -ForegroundColor Gray

# Исключаем ненужные директории
$excludeDirs = @("node_modules", ".git", "__pycache__", ".venv", "venv", "*.pyc", ".env", "media")
$excludeArgs = $excludeDirs | ForEach-Object { "-x $_" }
$excludeString = $excludeArgs -join " "

# Используем scp для загрузки файлов
scp -r "$projectRoot\*" "${ServerName}:${ServerPath}/"

Write-Host "✅ Файлы загружены!" -ForegroundColor Green

# Выполнение скрипта настройки на сервере
Write-Host "🔧 Выполнение настройки сервера..." -ForegroundColor Cyan
ssh $ServerName "cd $ServerPath/deploy && chmod +x scripts/*.sh monitoring/*.sh && ./scripts/setup.sh"

Write-Host ""
Write-Host "✅ Развертывание завершено!" -ForegroundColor Green
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Подключитесь к серверу: ssh $ServerName" -ForegroundColor White
Write-Host "2. Настройте .env файл: cd $ServerPath && cp deploy/env.prod.example .env && nano .env" -ForegroundColor White
Write-Host "3. Создайте директории: mkdir -p media/images media/edits media/face_swap media/videos" -ForegroundColor White
Write-Host "4. Запустите сервисы: cd $ServerPath/deploy && ./scripts/start.sh" -ForegroundColor White

