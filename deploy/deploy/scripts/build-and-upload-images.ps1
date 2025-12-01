# Скрипт сборки Docker образов локально и загрузки на сервер
# Запустите: .\deploy\scripts\build-and-upload-images.ps1

param(
    [string]$ServerName = "reg-ru-neurostudio"
)

$ErrorActionPreference = "Stop"

Write-Host "🐳 Сборка Docker образов локально и загрузка на сервер" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker не установлен на локальном ПК!" -ForegroundColor Red
    Write-Host "Установите Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Docker найден: $(docker --version)" -ForegroundColor Green
Write-Host ""

# Переход в корневую директорию проекта
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $projectRoot

Write-Host "📁 Директория проекта: $projectRoot" -ForegroundColor Gray
Write-Host ""

# Создание временной директории для образов
$tempDir = "$env:TEMP\docker-images-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
Write-Host "📦 Временная директория: $tempDir" -ForegroundColor Gray
Write-Host ""

# Сборка образов
Write-Host "[1/5] Сборка Docker образов..." -ForegroundColor Yellow
Write-Host ""

$images = @(
    @{Name="bot"; Dockerfile="docker/Dockerfile.bot"; Context="."},
    @{Name="api"; Dockerfile="docker/Dockerfile.api"; Context="."},
    @{Name="worker-image"; Dockerfile="docker/Dockerfile.worker"; Context="."}
)

foreach ($img in $images) {
    Write-Host "Сборка образа: $($img.Name)..." -ForegroundColor Cyan
    docker build -f $img.Dockerfile -t "media-lab-$($img.Name):latest" $img.Context
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Образ $($img.Name) собран" -ForegroundColor Green
        
        # Сохранение образа в tar файл
        $tarFile = Join-Path $tempDir "$($img.Name).tar"
        Write-Host "Сохранение образа в $tarFile..." -ForegroundColor Gray
        docker save "media-lab-$($img.Name):latest" -o $tarFile
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Образ сохранен: $tarFile" -ForegroundColor Green
        } else {
            Write-Host "❌ Ошибка сохранения образа $($img.Name)" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ Ошибка сборки образа $($img.Name)" -ForegroundColor Red
    }
    Write-Host ""
}

# Загрузка образов на сервер
Write-Host "[2/5] Загрузка образов на сервер..." -ForegroundColor Yellow
Write-Host ""

foreach ($img in $images) {
    $tarFile = Join-Path $tempDir "$($img.Name).tar"
    if (Test-Path $tarFile) {
        $fileSize = (Get-Item $tarFile).Length / 1MB
        Write-Host "Загрузка $($img.Name).tar ($([math]::Round($fileSize, 2)) MB)..." -ForegroundColor Cyan
        scp $tarFile "${ServerName}:/tmp/$($img.Name).tar"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Образ $($img.Name) загружен на сервер" -ForegroundColor Green
        } else {
            Write-Host "❌ Ошибка загрузки образа $($img.Name)" -ForegroundColor Red
        }
        Write-Host ""
    }
}

# Загрузка образов в Docker на сервере
Write-Host "[3/5] Загрузка образов в Docker на сервере..." -ForegroundColor Yellow
Write-Host ""

foreach ($img in $images) {
    Write-Host "Загрузка образа $($img.Name) в Docker..." -ForegroundColor Cyan
    ssh $ServerName "docker load -i /tmp/$($img.Name).tar && docker tag media-lab-$($img.Name):latest deploy-$($img.Name):latest && rm /tmp/$($img.Name).tar"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Образ $($img.Name) загружен в Docker" -ForegroundColor Green
    } else {
        Write-Host "❌ Ошибка загрузки образа $($img.Name) в Docker" -ForegroundColor Red
    }
    Write-Host ""
}

# Очистка
Write-Host "[4/5] Очистка временных файлов..." -ForegroundColor Yellow
Remove-Item -Path $tempDir -Recurse -Force
Write-Host "✅ Временные файлы удалены" -ForegroundColor Green
Write-Host ""

# Проверка
Write-Host "[5/5] Проверка образов на сервере..." -ForegroundColor Yellow
ssh $ServerName "docker images | grep -E 'media-lab|deploy'"
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ Образы собраны и загружены на сервер!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Теперь можно запустить сервисы:" -ForegroundColor Yellow
Write-Host "  ssh $ServerName 'cd /opt/media-lab/deploy && ./scripts/start.sh'" -ForegroundColor Gray
Write-Host ""






