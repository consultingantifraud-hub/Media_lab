# Скрипт выполнения команд на сервере через SSH
# Использование: .\deploy\scripts\ssh-exec.ps1 "команда"

param(
    [Parameter(Mandatory=$true)]
    [string]$Command,
    
    [string]$ConfigFile = "deploy\config\server-credentials.json",
    [string]$ServerName = "reg-ru-neurostudio"
)

# Проверка наличия конфигурации (опционально)
if (Test-Path $ConfigFile) {
    try {
        $config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
        $ServerName = $config.server.host
    } catch {
        # Используем значение по умолчанию
    }
}

# Выполнение команды на сервере
ssh $ServerName $Command







