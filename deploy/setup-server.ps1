# Комплексный скрипт автоматической настройки сервера
# Запустите этот скрипт один раз: .\setup-server.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio"
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Автоматическая настройка сервера Media Lab" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Шаг 1: Настройка SSH ключей
Write-Host "[1/9] Настройка SSH ключей..." -ForegroundColor Yellow
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"

if (-not (Test-Path $sshKeyPath)) {
    Write-Host "Создание SSH ключа..." -ForegroundColor Gray
    ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\id_rsa" -N '""' -q
}

Write-Host "Копирование SSH ключа на сервер..." -ForegroundColor Gray
Write-Host "⚠️  Введите пароль для пользователя root (потребуется один раз)" -ForegroundColor Yellow
$publicKey = Get-Content $sshKeyPath
$publicKey | ssh $ServerName "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo 'SSH ключ добавлен'"

Write-Host "✅ SSH ключи настроены" -ForegroundColor Green
Write-Host ""

# Шаг 2: Загрузка скрипта настройки на сервер
Write-Host "[2/9] Загрузка скрипта настройки на сервер..." -ForegroundColor Yellow
scp scripts\server-setup.sh "${ServerName}:/tmp/server-setup.sh"
ssh $ServerName "chmod +x /tmp/server-setup.sh"
Write-Host "✅ Скрипт загружен" -ForegroundColor Green
Write-Host ""

# Шаг 3: Выполнение настройки сервера
Write-Host "[3/9] Выполнение настройки сервера (это может занять несколько минут)..." -ForegroundColor Yellow
ssh $ServerName "/tmp/server-setup.sh"
Write-Host "✅ Сервер настроен" -ForegroundColor Green
Write-Host ""

# Шаг 4: Загрузка файлов проекта
Write-Host "[4/9] Загрузка файлов проекта на сервер..." -ForegroundColor Yellow
$projectRoot = Resolve-Path ".."
Write-Host "Загрузка из: $projectRoot" -ForegroundColor Gray

# Создаем архив проекта (исключая ненужные файлы)
$tempZip = "$env:TEMP\media-lab-deploy.zip"
if (Test-Path $tempZip) { Remove-Item $tempZip -Force }

Write-Host "Архивирование проекта..." -ForegroundColor Gray
cd ..
Get-ChildItem -Exclude node_modules,.git,__pycache__,.venv,venv,*.pyc,deploy_temp.zip | 
    Where-Object { $_.Name -ne "deploy_temp.zip" } | 
    Compress-Archive -DestinationPath $tempZip -Force
cd deploy

Write-Host "Загрузка архива на сервер..." -ForegroundColor Gray
scp $tempZip "${ServerName}:/tmp/media-lab.zip"
Remove-Item $tempZip -Force

Write-Host "Распаковка на сервере..." -ForegroundColor Gray
$unzipCmd = "cd /opt/media-lab && unzip -q -o /tmp/media-lab.zip -d /opt/media-lab && rm /tmp/media-lab.zip && chmod +x deploy/scripts/*.sh deploy/monitoring/*.sh 2>/dev/null || true && echo 'Files extracted'"
ssh $ServerName $unzipCmd

Write-Host "✅ Файлы загружены" -ForegroundColor Green
Write-Host ""

# Шаг 5: Создание .env файла из примера
Write-Host "[5/9] Создание конфигурационного файла .env..." -ForegroundColor Yellow
ssh $ServerName "cd /opt/media-lab && cp deploy/env.prod.example .env && echo '✅ Файл .env создан из примера'"
Write-Host "✅ Конфигурационный файл создан" -ForegroundColor Green
Write-Host ""

# Шаг 6: Проверка Docker
Write-Host "[6/9] Проверка Docker..." -ForegroundColor Yellow
ssh $ServerName "docker --version && docker-compose --version"
Write-Host "✅ Docker готов" -ForegroundColor Green
Write-Host ""

# Шаг 7: Создание директорий для медиа
Write-Host "[7/9] Создание директорий для медиа..." -ForegroundColor Yellow
ssh $ServerName "cd /opt/media-lab && mkdir -p media/images media/edits media/face_swap media/videos && chmod -R 755 media"
Write-Host "✅ Директории созданы" -ForegroundColor Green
Write-Host ""

# Шаг 8: Очистка временных файлов
Write-Host "[8/9] Очистка временных файлов..." -ForegroundColor Yellow
ssh $ServerName "rm -f /tmp/server-setup.sh /tmp/media-lab.zip"
Write-Host "✅ Временные файлы удалены" -ForegroundColor Green
Write-Host ""

# Шаг 9: Итоговая информация
Write-Host "[9/9] Настройка завершена!" -ForegroundColor Green
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ Сервер успешно настроен и готов к работе!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Следующие шаги:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Настройте переменные окружения:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab && nano .env'" -ForegroundColor Gray
Write-Host ""
Write-Host "   Заполните обязательные переменные:" -ForegroundColor White
Write-Host "   - tg_bot_token (токен Telegram бота от @BotFather)" -ForegroundColor Gray
Write-Host "   - fal_api_key (API ключ от https://fal.ai/dashboard/keys)" -ForegroundColor Gray
Write-Host "   - app_env=vps" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Запустите сервисы:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Проверьте статус:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/status.sh'" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Просмотрите логи:" -ForegroundColor White
Write-Host "   ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/logs.sh'" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Подсказка: Теперь вы можете подключаться без пароля:" -ForegroundColor Cyan
Write-Host "   ssh $ServerName" -ForegroundColor Gray
Write-Host ""

