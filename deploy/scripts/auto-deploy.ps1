# Автоматический скрипт развертывания - выполняет все действия на сервере
# Использование: .\scripts\auto-deploy.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio"
)

Write-Host "🤖 Автоматическое развертывание проекта на сервер" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Шаг 1: Проверка и установка Docker
Write-Host "[1/7] Проверка Docker..." -ForegroundColor Yellow
ssh $ServerName @"
if ! command -v docker &> /dev/null; then
    echo 'Установка Docker...'
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    echo '✅ Docker установлен'
else
    echo '✅ Docker уже установлен'
    docker --version
fi
"@

# Шаг 2: Проверка и установка Docker Compose
Write-Host "[2/7] Проверка Docker Compose..." -ForegroundColor Yellow
ssh $ServerName @"
if ! command -v docker-compose &> /dev/null; then
    echo 'Установка Docker Compose...'
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo '✅ Docker Compose установлен'
else
    echo '✅ Docker Compose уже установлен'
    docker-compose --version
fi
"@

# Шаг 3: Создание директорий
Write-Host "[3/7] Создание директорий..." -ForegroundColor Yellow
ssh $ServerName "mkdir -p /opt/media-lab && mkdir -p /opt/backups/media-lab && chmod 755 /opt/media-lab /opt/backups/media-lab"
Write-Host "✅ Директории созданы" -ForegroundColor Green

# Шаг 4: Загрузка файлов проекта
Write-Host "[4/7] Загрузка файлов проекта..." -ForegroundColor Yellow
$projectRoot = Resolve-Path ".."
Write-Host "Загрузка из: $projectRoot" -ForegroundColor Gray

# Создаем временный список файлов для исключения
$excludePattern = @("node_modules", ".git", "__pycache__", ".venv", "venv", "*.pyc")

# Загружаем файлы через tar для сохранения структуры
Write-Host "Архивирование и загрузка..." -ForegroundColor Gray
cd ..
Get-ChildItem -Exclude node_modules,.git,__pycache__,.venv,venv,*.pyc | Compress-Archive -DestinationPath deploy_temp.zip -Force
scp deploy_temp.zip "${ServerName}:/tmp/media-lab.zip"
Remove-Item deploy_temp.zip -Force
cd deploy

# Распаковка на сервере
ssh $ServerName @"
cd /opt/media-lab
if [ -f /tmp/media-lab.zip ]; then
    unzip -q -o /tmp/media-lab.zip -d /opt/media-lab
    rm /tmp/media-lab.zip
    echo '✅ Файлы распакованы'
else
    echo '⚠️  Архив не найден'
fi
"@

Write-Host "✅ Файлы загружены" -ForegroundColor Green

# Шаг 5: Установка прав на скрипты
Write-Host "[5/7] Установка прав на скрипты..." -ForegroundColor Yellow
ssh $ServerName "cd /opt/media-lab/deploy && chmod +x scripts/*.sh monitoring/*.sh 2>/dev/null || true"
Write-Host "✅ Права установлены" -ForegroundColor Green

# Шаг 6: Запуск скрипта настройки
Write-Host "[6/7] Выполнение скрипта настройки сервера..." -ForegroundColor Yellow
ssh $ServerName "cd /opt/media-lab/deploy && ./scripts/setup.sh"
Write-Host "✅ Настройка завершена" -ForegroundColor Green

# Шаг 7: Создание директорий для медиа
Write-Host "[7/7] Создание директорий для медиа..." -ForegroundColor Yellow
ssh $ServerName "cd /opt/media-lab && mkdir -p media/images media/edits media/face_swap media/videos && chmod -R 755 media"
Write-Host "✅ Директории для медиа созданы" -ForegroundColor Green

Write-Host ""
Write-Host "✅ Автоматическое развертывание завершено!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Настройте .env файл:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab && cp deploy/env.prod.example .env && nano .env'" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Запустите сервисы:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Проверьте статус:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/status.sh'" -ForegroundColor Gray

