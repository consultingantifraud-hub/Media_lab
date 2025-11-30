# Простой скрипт очистки Docker с удалением media/
# Использует простые команды без сложных строковых операций

param(
    [switch]$CleanMedia = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker not found" -ForegroundColor Red
    exit 1
}

try {
    docker info | Out-Null
} catch {
    Write-Host "Error: Docker is not running" -ForegroundColor Red
    exit 1
}

# Показываем текущее состояние
Write-Host "Current Docker usage:" -ForegroundColor Yellow
docker system df
Write-Host ""

# Показываем работающие контейнеры
$running = docker ps -q
if ($running) {
    Write-Host "Running containers (will be preserved):" -ForegroundColor Green
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    Write-Host ""
}

# Показываем остановленные контейнеры
$stopped = docker ps -a -q -f "status=exited"
if ($stopped) {
    Write-Host "Stopped containers (will be removed):" -ForegroundColor Yellow
    docker ps -a -f "status=exited" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    Write-Host ""
}

# Показываем информацию о media/
if ($CleanMedia) {
    $mediaPath = Join-Path $PSScriptRoot "..\media"
    if (Test-Path $mediaPath) {
        $mediaFiles = Get-ChildItem $mediaPath -Recurse -File -ErrorAction SilentlyContinue
        $mediaSize = ($mediaFiles | Measure-Object -Property Length -Sum).Sum
        $mediaSizeGB = [math]::Round($mediaSize / 1GB, 2)
        Write-Host "Media folder will be cleaned: ~$mediaSizeGB GB, $($mediaFiles.Count) files" -ForegroundColor Red
        Write-Host ""
    }
}

Write-Host "Will be cleaned:" -ForegroundColor Yellow
Write-Host "  - Stopped containers" -ForegroundColor White
Write-Host "  - Unused images" -ForegroundColor White
Write-Host "  - Build cache" -ForegroundColor White
Write-Host "  - Unused networks" -ForegroundColor White
if ($CleanMedia) {
    Write-Host "  - Media folder contents" -ForegroundColor Red
}
Write-Host ""

$confirm = Read-Host "Continue? (Y/N)"
if ($confirm -ne "Y" -and $confirm -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting cleanup..." -ForegroundColor Cyan
Write-Host ""

# 1. Удаление остановленных контейнеров
Write-Host "[1/5] Removing stopped containers..." -ForegroundColor Yellow
if ($stopped) {
    docker rm $stopped 2>&1 | Out-Null
    Write-Host "  Removed stopped containers" -ForegroundColor Green
} else {
    Write-Host "  No stopped containers found" -ForegroundColor Gray
}

# 2. Удаление неиспользуемых образов
Write-Host "[2/5] Removing unused images..." -ForegroundColor Yellow
docker image prune -a -f 2>&1 | Out-Null
Write-Host "  Unused images removed" -ForegroundColor Green

# 3. Очистка build cache
Write-Host "[3/5] Cleaning build cache..." -ForegroundColor Yellow
docker builder prune -f 2>&1 | Out-Null
Write-Host "  Build cache cleaned" -ForegroundColor Green

# 4. Удаление неиспользуемых сетей
Write-Host "[4/5] Removing unused networks..." -ForegroundColor Yellow
docker network prune -f 2>&1 | Out-Null
Write-Host "  Unused networks removed" -ForegroundColor Green

# 5. Очистка media/
if ($CleanMedia) {
    Write-Host "[5/5] Cleaning media folder..." -ForegroundColor Yellow
    $mediaPath = Join-Path $PSScriptRoot "..\media"
    
    if (Test-Path $mediaPath) {
        $subdirs = Get-ChildItem $mediaPath -Directory -ErrorAction SilentlyContinue
        $totalFiles = 0
        $totalSize = 0
        
        foreach ($dir in $subdirs) {
            $files = Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue
            if ($files) {
                $dirSize = ($files | Measure-Object -Property Length -Sum).Sum
                Remove-Item "$($dir.FullName)\*" -Recurse -Force -ErrorAction SilentlyContinue
                $totalFiles += $files.Count
                $totalSize += $dirSize
                Write-Host "  Cleaned $($dir.Name)/ ($($files.Count) files)" -ForegroundColor Gray
            }
        }
        
        $rootFiles = Get-ChildItem $mediaPath -File -ErrorAction SilentlyContinue
        if ($rootFiles) {
            Remove-Item "$mediaPath\*" -Force -ErrorAction SilentlyContinue
            $totalFiles += $rootFiles.Count
        }
        
        if ($totalFiles -gt 0) {
            $totalSizeGB = [math]::Round($totalSize / 1GB, 2)
            Write-Host "  Removed $totalFiles files (~$totalSizeGB GB)" -ForegroundColor Green
        } else {
            Write-Host "  Media folder is already empty" -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cleanup completed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Final Docker usage:" -ForegroundColor Yellow
docker system df
Write-Host ""

if ($running) {
    Write-Host "Running containers (all OK):" -ForegroundColor Green
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
}

Write-Host ""








