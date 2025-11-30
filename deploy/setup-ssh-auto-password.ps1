# Автоматическая настройка SSH с использованием пароля из конфигурации
# Запустите: .\setup-ssh-auto-password.ps1

$configFile = "deploy\config\server-credentials.json"

if (-not (Test-Path $configFile)) {
    Write-Host "Файл конфигурации не найден: $configFile" -ForegroundColor Red
    exit 1
}

# Чтение конфигурации
try {
    $json = Get-Content $configFile -Raw -Encoding UTF8
    $config = $json | ConvertFrom-Json
    $serverHostname = $config.server.hostname
    $serverUser = $config.server.user
    $serverPassword = $config.server.password
    $serverPort = $config.server.port
    
    Write-Host "Настройка SSH подключения..." -ForegroundColor Cyan
    Write-Host "Сервер: $serverUser@$serverHostname" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "Ошибка чтения конфигурации: $_" -ForegroundColor Red
    exit 1
}

# Проверка/создание SSH ключа
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa"
if (-not (Test-Path $sshKeyPath)) {
    Write-Host "Создание SSH ключа..." -ForegroundColor Yellow
    ssh-keygen -t rsa -b 4096 -f $sshKeyPath -N '""' -q
    Write-Host "SSH ключ создан" -ForegroundColor Green
} else {
    Write-Host "SSH ключ уже существует" -ForegroundColor Green
}

Write-Host ""
Write-Host "Копирование SSH ключа на сервер..." -ForegroundColor Yellow
Write-Host "Используется пароль из конфигурации" -ForegroundColor Gray
Write-Host ""

# Используем plink или создаем временный скрипт для автоматической передачи пароля
$publicKey = Get-Content "$sshKeyPath.pub"

# Создаем временный скрипт на сервере через echo и ssh с паролем
# Используем expect-подобный подход через PowerShell

Write-Host "Попытка автоматической передачи пароля..." -ForegroundColor Yellow

# Альтернативный метод: создаем команду, которая будет выполнена на сервере
$setupCommand = @"
mkdir -p ~/.ssh
echo '$publicKey' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
echo 'SSH key added successfully'
"@

# Сохраняем команду во временный файл
$tempScript = "$env:TEMP\ssh-setup-$(Get-Random).sh"
$setupCommand | Out-File -FilePath $tempScript -Encoding ASCII -NoNewline

# Используем ssh с передачей пароля через stdin
# Для Windows нужно использовать другой подход
Write-Host ""
Write-Host "ВНИМАНИЕ: Для автоматической передачи пароля требуется ввести его вручную" -ForegroundColor Yellow
Write-Host "Скопируйте пароль из файла конфигурации и вставьте его когда запросит:" -ForegroundColor Yellow
Write-Host "Пароль: $serverPassword" -ForegroundColor Cyan
Write-Host ""
Write-Host "Нажмите Enter для продолжения..."
Read-Host

# Копирование ключа
$publicKey | ssh -p $serverPort "${serverUser}@${serverHostname}" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo 'SSH key added'"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SSH ключ скопирован!" -ForegroundColor Green
    Write-Host "Проверка подключения без пароля..." -ForegroundColor Yellow
    
    ssh -p $serverPort "${serverUser}@${serverHostname}" "echo 'Connected successfully - no password required!'"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Успешно! Теперь подключение работает без пароля!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Можно использовать: ssh reg-ru-neurostudio" -ForegroundColor Cyan
    }
} else {
    Write-Host ""
    Write-Host "Ошибка при копировании ключа" -ForegroundColor Red
}

# Удаление временного файла
if (Test-Path $tempScript) {
    Remove-Item $tempScript -Force
}

