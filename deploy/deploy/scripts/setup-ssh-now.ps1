# Настройка SSH ключей для автоматического подключения
# Выполните этот скрипт в локальном PowerShell

$serverHostname = "91.197.97.68"
$serverUser = "root"
$serverPort = 22

Write-Host "Настройка SSH подключения..." -ForegroundColor Cyan
Write-Host "Сервер: $serverUser@$serverHostname" -ForegroundColor Gray
Write-Host ""

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
Write-Host "Введите пароль для пользователя $serverUser (потребуется один раз):" -ForegroundColor Yellow
Write-Host ""

# Копирование ключа на сервер
$publicKey = Get-Content "$sshKeyPath.pub"
$publicKey | ssh -p $serverPort "${serverUser}@${serverHostname}" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo 'SSH key added successfully'"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SSH ключ скопирован!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Проверка подключения без пароля..." -ForegroundColor Yellow
    
    # Тест подключения
    $testResult = ssh -p $serverPort "${serverUser}@${serverHostname}" "echo 'SSH connection successful - no password required!'"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Успешно! Теперь подключение работает без пароля!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Можно использовать:" -ForegroundColor Cyan
        Write-Host "  ssh reg-ru-neurostudio" -ForegroundColor Gray
    } else {
        Write-Host ""
        Write-Host "Подключение все еще требует пароль. Попробуйте еще раз." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Ошибка при копировании ключа" -ForegroundColor Red
}







