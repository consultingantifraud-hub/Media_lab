param(
    [string]$ConfigFile = "deploy\config\server-credentials.json"
)

Write-Host "Настройка SSH подключения..." -ForegroundColor Cyan

if (-not (Test-Path $ConfigFile)) {
    Write-Host "Файл не найден: $ConfigFile" -ForegroundColor Red
    exit 1
}

$config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
$serverHost = $config.server.host
$serverHostname = $config.server.hostname
$serverUser = $config.server.user
$serverPort = $config.server.port

Write-Host "Сервер: $serverHost" -ForegroundColor Green

$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa"
if (-not (Test-Path $sshKeyPath)) {
    Write-Host "Создание SSH ключа..." -ForegroundColor Yellow
    ssh-keygen -t rsa -b 4096 -f $sshKeyPath -N '""' -q
}

Write-Host "Копирование ключа на сервер..." -ForegroundColor Yellow
Write-Host "Введите пароль один раз:" -ForegroundColor Yellow

$publicKey = Get-Content "$sshKeyPath.pub"
$publicKey | ssh -p $serverPort "${serverUser}@${serverHostname}" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Готово! Проверка подключения..." -ForegroundColor Green
    ssh -p $serverPort "${serverUser}@${serverHostname}" "echo 'Connected successfully'"
    Write-Host "SSH настроен!" -ForegroundColor Green
} else {
    Write-Host "Ошибка" -ForegroundColor Red
}
