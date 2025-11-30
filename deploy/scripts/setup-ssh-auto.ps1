# Скрипт настройки автоматического SSH подключения
# Запустите: .\deploy\scripts\setup-ssh-auto.ps1

param(
    [string]$ConfigFile = "deploy\config\server-credentials.json"
)

Write-Host "🔐 Настройка автоматического SSH подключения..." -ForegroundColor Cyan
Write-Host ""

# Проверка наличия файла конфигурации
if (-not (Test-Path $ConfigFile)) {
    Write-Host "❌ Файл конфигурации не найден: $ConfigFile" -ForegroundColor Red
    Write-Host ""
    Write-Host "Создайте файл $ConfigFile на основе server-credentials.json.example" -ForegroundColor Yellow
    Write-Host "И заполните пароль сервера" -ForegroundColor Yellow
    exit 1
}

# Чтение конфигурации
try {
    $config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
    $serverHost = $config.server.host
    $serverHostname = $config.server.hostname
    $serverUser = $config.server.user
    $serverPassword = $config.server.password
    $serverPort = $config.server.port
    
    Write-Host "✅ Конфигурация загружена" -ForegroundColor Green
    Write-Host "   Сервер: $serverHost ($serverHostname)" -ForegroundColor Gray
    Write-Host "   Пользователь: $serverUser" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "❌ Ошибка чтения конфигурации: $_" -ForegroundColor Red
    exit 1
}

# Проверка SSH ключа
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa"
if (-not (Test-Path $sshKeyPath)) {
    Write-Host "Создание SSH ключа..." -ForegroundColor Yellow
    ssh-keygen -t rsa -b 4096 -f $sshKeyPath -N '""' -q
    Write-Host "✅ SSH ключ создан" -ForegroundColor Green
}

# Копирование SSH ключа на сервер
Write-Host "Копирование SSH ключа на сервер..." -ForegroundColor Yellow
Write-Host "Введите пароль для пользователя $serverUser (потребуется один раз)..." -ForegroundColor Yellow
Write-Host ""

$publicKey = Get-Content "$sshKeyPath.pub"
$publicKey | ssh -p $serverPort "${serverUser}@${serverHostname}" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo 'SSH key added'"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ SSH ключ скопирован на сервер" -ForegroundColor Green
    Write-Host ""
    Write-Host "Проверка подключения без пароля..." -ForegroundColor Yellow
    
    # Тест подключения
    $testResult = ssh -p $serverPort "${serverUser}@${serverHostname}" "echo 'SSH connection successful'"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Подключение работает без пароля!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Теперь можно использовать команды:" -ForegroundColor Cyan
        Write-Host "  ssh $serverHost" -ForegroundColor Gray
        Write-Host "  .\deploy\scripts\ssh-exec.ps1 'команда'" -ForegroundColor Gray
    } else {
        Write-Host "⚠️  Подключение все еще требует пароль" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ Ошибка при копировании SSH ключа" -ForegroundColor Red
}

