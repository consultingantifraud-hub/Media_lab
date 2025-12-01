# Скрипт сборки Docker образов локально и загрузки на сервер
# Запустите после запуска Docker Desktop: .\build-images-local.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio"
)

Write-Host "🐳 Сборка Docker образов локально" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker
Write-Host "Проверка Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✅ Docker работает" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker не запущен! Запустите Docker Desktop" -ForegroundColor Red
    exit 1
}

$projectRoot = Get-Location
Write-Host "Директория: $projectRoot" -ForegroundColor Gray
Write-Host ""

# Создание временной директории
$tempDir = "$env:TEMP\docker-images-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
Write-Host "Временная директория: $tempDir" -ForegroundColor Gray
Write-Host ""

# Сборка образов
$images = @(
    @{Name="bot"; File="docker/Dockerfile.bot"},
    @{Name="api"; File="docker/Dockerfile.api"},
    @{Name="worker-image"; File="docker/Dockerfile.worker"}
)

foreach ($img in $images) {
    Write-Host "[$($images.IndexOf($img)+1)/$($images.Count)] Сборка образа: $($img.Name)..." -ForegroundColor Yellow
    
    docker build -f $img.File -t "deploy-$($img.Name):latest" .
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Образ собран" -ForegroundColor Green
        
        # Сохранение в tar
        $tarFile = Join-Path $tempDir "$($img.Name).tar"
        Write-Host "Сохранение в $tarFile..." -ForegroundColor Gray
        docker save "deploy-$($img.Name):latest" -o $tarFile
        
        if ($LASTEXITCODE -eq 0) {
            $size = [math]::Round((Get-Item $tarFile).Length / 1MB, 2)
            Write-Host "✅ Сохранен ($size MB)" -ForegroundColor Green
        }
    } else {
        Write-Host "❌ Ошибка сборки" -ForegroundColor Red
    }
    Write-Host ""
}

# Загрузка на сервер
Write-Host "Загрузка образов на сервер..." -ForegroundColor Yellow
Write-Host ""

foreach ($img in $images) {
    $tarFile = Join-Path $tempDir "$($img.Name).tar"
    if (Test-Path $tarFile) {
        Write-Host "Загрузка $($img.Name).tar..." -ForegroundColor Cyan
        scp $tarFile "${ServerName}:/tmp/$($img.Name).tar"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Загружен на сервер" -ForegroundColor Green
            
            # Загрузка в Docker на сервере
            Write-Host "Импорт в Docker на сервере..." -ForegroundColor Gray
            ssh $ServerName "docker load -i /tmp/$($img.Name).tar && rm /tmp/$($img.Name).tar"
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ Импортирован в Docker" -ForegroundColor Green
            }
        }
        Write-Host ""
    }
}

# Очистка
Remove-Item -Path $tempDir -Recurse -Force
Write-Host "✅ Готово! Образы собраны и загружены на сервер" -ForegroundColor Green
Write-Host ""
Write-Host "Запустите сервисы:" -ForegroundColor Yellow
Write-Host "  ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
