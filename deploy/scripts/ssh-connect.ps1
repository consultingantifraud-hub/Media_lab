# PowerShell скрипт для подключения к SSH серверу
# Использование: .\ssh-connect.ps1 [server_name]

param(
    [string]$ServerName = "reg-ru-neurostudio",
    [string]$ServerIP = "",
    [string]$Username = "",
    [int]$Port = 22
)

Write-Host "🔐 Подключение к SSH серверу..." -ForegroundColor Cyan

# Проверка наличия SSH клиента
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Host "❌ SSH клиент не найден!" -ForegroundColor Red
    Write-Host "Установите OpenSSH Client через: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0" -ForegroundColor Yellow
    exit 1
}

# Если указаны параметры сервера, используем их
if ($ServerIP -and $Username) {
    $connectionString = "${Username}@${ServerIP}"
    if ($Port -ne 22) {
        $connectionString = "${Username}@${ServerIP} -p ${Port}"
    }
    Write-Host "Подключение к: $connectionString" -ForegroundColor Green
    ssh $connectionString
} else {
    # Используем конфигурацию из ~/.ssh/config
    Write-Host "Подключение к серверу: $ServerName" -ForegroundColor Green
    Write-Host "Используется конфигурация из ~/.ssh/config" -ForegroundColor Gray
    ssh $ServerName
}

