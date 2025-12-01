# Создание скрипта для загрузки файлов через base64
# Этот скрипт создаст команды для выполнения на сервере

$projectRoot = "C:\MAIN\Bots\Media_lab"
$outputFile = "server-upload-commands.txt"

Write-Host "Создание команд для загрузки файлов на сервер..." -ForegroundColor Cyan

# Список важных файлов для загрузки
$importantFiles = @(
    "deploy\docker-compose.prod.yml",
    "deploy\env.prod.example",
    "deploy\scripts\start.sh",
    "deploy\scripts\stop.sh",
    "deploy\scripts\status.sh",
    "deploy\scripts\logs.sh",
    "deploy\scripts\restart.sh"
)

$commands = @()
$commands += "mkdir -p /opt/media-lab/deploy/scripts"
$commands += "mkdir -p /opt/media-lab/deploy/monitoring"

foreach ($file in $importantFiles) {
    $fullPath = Join-Path $projectRoot $file
    if (Test-Path $fullPath) {
        $content = Get-Content $fullPath -Raw -Encoding UTF8
        $base64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
        $serverPath = $file.Replace("\", "/")
        $commands += "cat > /opt/media-lab/$serverPath << 'ENDOFFILE'"
        $commands += $content
        $commands += "ENDOFFILE"
        $commands += "chmod +x /opt/media-lab/$serverPath"
    }
}

$commands | Out-File $outputFile -Encoding UTF8
Write-Host "Команды сохранены в $outputFile" -ForegroundColor Green
Write-Host "Скопируйте содержимое этого файла и выполните на сервере" -ForegroundColor Yellow







