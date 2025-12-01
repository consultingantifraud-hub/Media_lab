# Скрипт для безопасной очистки Docker без влияния на работающие контейнеры
# Удаляет: неиспользуемые образы, build cache, остановленные контейнеры, неиспользуемые volumes и сети
# ВАЖНО: Bind mounts (например, ../media:/app/media) НЕ удаляются - это папки на хосте

param(
    [switch]$SkipVolumes = $true,  # По умолчанию volumes НЕ удаляются для безопасности
    [switch]$CleanMedia = $false   # По умолчанию папка media/ НЕ очищается
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Очистка Docker" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Ошибка: Docker не найден. Убедитесь, что Docker Desktop установлен и запущен." -ForegroundColor Red
    exit 1
}

# Проверка, что Docker работает
try {
    docker info | Out-Null
} catch {
    Write-Host "Ошибка: Docker не запущен. Запустите Docker Desktop и повторите попытку." -ForegroundColor Red
    exit 1
}

Write-Host "Текущее использование дискового пространства Docker:" -ForegroundColor Yellow
docker system df
Write-Host ""

# Показываем информацию о build cache
$buildCacheInfo = docker system df --format "{{.Type}}\t{{.Reclaimable}}" | Select-String "Build Cache"
if ($buildCacheInfo) {
    Write-Host "Build Cache занимает много места и будет очищен:" -ForegroundColor Cyan
    docker system df | Select-String "Build Cache"
    Write-Host ""
}

# Получаем список работающих контейнеров
$runningContainers = docker ps -q
$runningContainersNames = docker ps --format "{{.Names}}"
if ($runningContainers) {
    Write-Host "========================================" -ForegroundColor Green
    $runningHeader = "РАБОТАЮЩИЕ КОНТЕЙНЕРЫ (БУДУТ СОХРАНЕНЫ):"
    Write-Host $runningHeader -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    Write-Host ""
    $savedMsg = "✓ Эти контейнеры и их образы НЕ будут удалены"
    Write-Host $savedMsg -ForegroundColor Green
    Write-Host ""
}

# Получаем список всех контейнеров (работающих и остановленных)
$allContainers = docker ps -a --format "{{.Names}}"
$stoppedContainersList = docker ps -a -f "status=exited" --format "{{.Names}}"

if ($allContainers) {
    Write-Host "Все контейнеры (работающие + остановленные):" -ForegroundColor Cyan
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    Write-Host ""
}

# Получаем список используемых образов
$usedImages = docker ps -a --format "{{.Image}}" | Sort-Object -Unique
$runningImages = docker ps --format "{{.Image}}" | Sort-Object -Unique
$stoppedImages = docker ps -a -f "status=exited" --format "{{.Image}}" | Sort-Object -Unique

if ($usedImages) {
    Write-Host "Образы, используемые контейнерами:" -ForegroundColor Cyan
    if ($runningImages) {
        Write-Host "  Работающие контейнеры (образы будут сохранены):" -ForegroundColor Green
        $runningImages | ForEach-Object { Write-Host "    ✓ $_" -ForegroundColor Green }
    }
    if ($stoppedImages) {
        Write-Host "  Остановленные контейнеры (образы могут быть удалены после удаления контейнеров):" -ForegroundColor Yellow
        $stoppedImages | ForEach-Object { Write-Host "    ⚠ $_" -ForegroundColor Yellow }
    }
    Write-Host ""
}

# Проверяем volumes
$allVolumes = docker volume ls -q
$mountsOutput = docker ps -a --format "{{.Mounts}}"
$usedVolumes = @()
if ($mountsOutput) {
    $mountsOutput | Select-String "volume" | ForEach-Object {
        $line = $_.Line
        if ($line -match 'volume\s+([^\s]+)') {
            $usedVolumes += $matches[1]
        }
    }
}
$usedVolumes = $usedVolumes | Sort-Object -Unique
$unusedVolumesList = @()

if ($allVolumes) {
    Write-Host "Volumes:" -ForegroundColor Cyan
    docker volume ls
    Write-Host ""
    
    if ($usedVolumes) {
        Write-Host "Используемые volumes (будут сохранены):" -ForegroundColor Green
        $usedVolumes | ForEach-Object { Write-Host "  - $_" }
        Write-Host ""
    }
    
    # Находим неиспользуемые volumes
    foreach ($vol in $allVolumes) {
        if ($usedVolumes -notcontains $vol) {
            $unusedVolumesList += $vol
        }
    }
    
    if ($unusedVolumesList.Count -gt 0) {
        Write-Host "Неиспользуемые volumes (будут удалены, если не пропущены):" -ForegroundColor Yellow
        $unusedVolumesList | ForEach-Object { Write-Host "  - $_" }
        Write-Host ""
    }
}

# Показываем что будет удалено
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Будет выполнена очистка:" -ForegroundColor Yellow
Write-Host "  ✓ Неиспользуемые образы (dangling и неиспользуемые)" -ForegroundColor White
Write-Host "  ✓ Build cache" -ForegroundColor White
Write-Host "  ✓ Остановленные контейнеры" -ForegroundColor White
if (-not $SkipVolumes) {
    Write-Host "  ✓ Неиспользуемые volumes (named volumes, НЕ bind mounts!)" -ForegroundColor White
} else {
    Write-Host "  ✗ Volumes (пропущено для безопасности)" -ForegroundColor Gray
}
Write-Host "  ✓ Неиспользуемые сети" -ForegroundColor White
if ($CleanMedia) {
    $mediaPath = Join-Path $PSScriptRoot "..\media"
    if (Test-Path $mediaPath) {
        $mediaSize = (Get-ChildItem $mediaPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $mediaSizeGB = [math]::Round($mediaSize / 1GB, 2)
        $fileCount = (Get-ChildItem $mediaPath -Recurse -File -ErrorAction SilentlyContinue).Count
        $mediaMsg = "  ⚠ ОЧИСТКА ПАПКИ media/ (будет удалено ~$mediaSizeGB ГБ, $fileCount файлов)"
        Write-Host $mediaMsg -ForegroundColor Red
    }
} else {
    Write-Host "  ✗ Папка media/ (пропущено)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "БЕЗОПАСНОСТЬ:" -ForegroundColor Yellow
if ($runningContainers) {
    Write-Host "  ✓ Работающие контейнеры НЕ будут удалены" -ForegroundColor Green
    Write-Host "  ✓ Образы работающих контейнеров НЕ будут удалены" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Работающие контейнеры, которые будут сохранены:" -ForegroundColor Green
    docker ps --format "    ✓ {{.Names}} ({{.Image}})" | ForEach-Object { Write-Host $_ -ForegroundColor Green }
    Write-Host ""
}
if ($stoppedImages) {
    Write-Host "  ⚠ Образы остановленных контейнеров могут быть удалены после удаления контейнеров" -ForegroundColor Yellow
    Write-Host "    (если они не используются другими контейнерами)" -ForegroundColor Yellow
    Write-Host ""
}
if (-not $CleanMedia) {
    Write-Host "  ✓ Данные в папке media/ на хосте НЕ затрагиваются" -ForegroundColor Green
}
Write-Host "  ✓ Удаляются ТОЛЬКО остановленные контейнеры (status=exited)" -ForegroundColor Green
Write-Host ""

# Дополнительное подтверждение для очистки media/
if ($CleanMedia) {
    Write-Host "⚠ ВНИМАНИЕ: Будет удалено содержимое папки media/!" -ForegroundColor Red
    Write-Host "Это действие НЕОБРАТИМО!" -ForegroundColor Red
    $mediaConfirmation = Read-Host "Вы уверены, что хотите удалить данные в media/? (YES для подтверждения)"
    if ($mediaConfirmation -ne "YES") {
        Write-Host "Очистка media/ отменена. Продолжаем только очистку Docker..." -ForegroundColor Yellow
        $CleanMedia = $false
    }
}

$confirmation = Read-Host "Продолжить очистку? (Y/N)"
if ($confirmation -ne "Y" -and $confirmation -ne "y") {
    Write-Host "Очистка отменена." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Начало очистки..." -ForegroundColor Cyan
Write-Host ""

# Подсчитываем количество шагов
$totalSteps = 6
if ($CleanMedia) { $totalSteps = 7 }

# 1. Удаление остановленных контейнеров
Write-Host "[1/$totalSteps] Удаление остановленных контейнеров..." -ForegroundColor Yellow
$stoppedContainers = docker ps -a -q -f "status=exited"
if ($stoppedContainers) {
    $stoppedNames = docker ps -a -f "status=exited" --format "{{.Names}}"
    Write-Host "  Будут удалены ТОЛЬКО остановленные контейнеры:" -ForegroundColor Yellow
    $stoppedNames | ForEach-Object { Write-Host "    - $_ (остановлен)" -ForegroundColor Gray }
    if ($runningContainers) {
        Write-Host "  Работающие контейнеры остаются нетронутыми:" -ForegroundColor Green
        $runningContainersNames | ForEach-Object { Write-Host "    ✓ $_ (работает)" -ForegroundColor Green }
    }
    docker rm $stoppedContainers 2>&1 | Out-Null
    Write-Host "  ✓ Удалено остановленных контейнеров: $($stoppedContainers.Count)" -ForegroundColor Green
} else {
    Write-Host "  Остановленных контейнеров не найдено" -ForegroundColor Gray
    if ($runningContainers) {
        Write-Host "  Работающие контейнеры остаются нетронутыми" -ForegroundColor Green
    }
}

# 2. Удаление неиспользуемых образов (dangling)
Write-Host "[2/$totalSteps] Удаление dangling образов..." -ForegroundColor Yellow
$danglingImages = docker images -q -f "dangling=true"
if ($danglingImages) {
    docker rmi $danglingImages 2>&1 | Out-Null
    Write-Host "  Удалено dangling образов: $($danglingImages.Count)" -ForegroundColor Green
} else {
    Write-Host "  Dangling образов не найдено" -ForegroundColor Gray
}

# 3. Удаление неиспользуемых образов (не используемые ни одним контейнером)
Write-Host "[3/$totalSteps] Удаление неиспользуемых образов..." -ForegroundColor Yellow
$beforeImages = (docker images -q | Measure-Object).Count
docker image prune -a -f 2>&1 | Out-Null
$afterImages = (docker images -q | Measure-Object).Count
$removedImages = $beforeImages - $afterImages
if ($removedImages -gt 0) {
    Write-Host "  Удалено неиспользуемых образов: $removedImages" -ForegroundColor Green
} else {
    Write-Host "  Неиспользуемых образов не найдено" -ForegroundColor Gray
}

# 4. Удаление неиспользуемых volumes (только если не пропущено)
if (-not $SkipVolumes) {
    Write-Host "[4/$totalSteps] Удаление неиспользуемых volumes..." -ForegroundColor Yellow
    Write-Host "  ВНИМАНИЕ: Удаляются только named volumes, НЕ bind mounts!" -ForegroundColor Yellow
    Write-Host "  Bind mounts (../media:/app/media) остаются нетронутыми" -ForegroundColor Green
    
    $beforeVolumes = (docker volume ls -q | Measure-Object).Count
    docker volume prune -f 2>&1 | Out-Null
    $afterVolumes = (docker volume ls -q | Measure-Object).Count
    $removedVolumes = $beforeVolumes - $afterVolumes
    
    if ($removedVolumes -gt 0) {
        Write-Host "  ✓ Удалено неиспользуемых volumes: $removedVolumes" -ForegroundColor Green
    } else {
        Write-Host "  Неиспользуемых volumes не найдено" -ForegroundColor Gray
    }
} else {
    Write-Host "[4/$totalSteps] Удаление volumes пропущено (безопасный режим)" -ForegroundColor Gray
}

# 5. Очистка build cache
$stepNum = if (-not $SkipVolumes) { 5 } else { 4 }
Write-Host "[$stepNum/$totalSteps] Очистка build cache..." -ForegroundColor Yellow
docker builder prune -f 2>&1 | Out-Null
Write-Host "  Build cache очищен" -ForegroundColor Green

# 6. Удаление неиспользуемых сетей
$stepNum = if (-not $SkipVolumes) { 6 } else { 5 }
Write-Host "[$stepNum/$totalSteps] Удаление неиспользуемых сетей..." -ForegroundColor Yellow
docker network prune -f 2>&1 | Out-Null
Write-Host "  Неиспользуемые сети удалены" -ForegroundColor Green

# 7. Очистка папки media/ (если запрошено)
if ($CleanMedia) {
    Write-Host "[$totalSteps/$totalSteps] Очистка папки media/..." -ForegroundColor Yellow
    $mediaPath = Join-Path $PSScriptRoot "..\media"
    
    if (Test-Path $mediaPath) {
        # Получаем список подпапок
        $subdirs = Get-ChildItem $mediaPath -Directory -ErrorAction SilentlyContinue
        
        $totalFiles = 0
        $totalSize = 0
        
        foreach ($dir in $subdirs) {
            $files = Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue
            $dirSize = ($files | Measure-Object -Property Length -Sum).Sum
            $fileCount = $files.Count
            
            if ($fileCount -gt 0) {
                $dirSizeMB = [math]::Round($dirSize / 1MB, 2)
                $deleteMsg = "  Удаление файлов из $($dir.Name)/ ($fileCount файлов, $dirSizeMB МБ)..."
                Write-Host $deleteMsg -ForegroundColor Gray
                Remove-Item "$($dir.FullName)\*" -Recurse -Force -ErrorAction SilentlyContinue
                $totalFiles += $fileCount
                $totalSize += $dirSize
            }
        }
        
        # Удаляем файлы в корне media/ (если есть)
        $rootFiles = Get-ChildItem $mediaPath -File -ErrorAction SilentlyContinue
        if ($rootFiles) {
            Remove-Item "$mediaPath\*" -Force -ErrorAction SilentlyContinue
            $totalFiles += $rootFiles.Count
            $totalSize += ($rootFiles | Measure-Object -Property Length -Sum).Sum
        }
        
        if ($totalFiles -gt 0) {
            $totalSizeGB = [math]::Round($totalSize / 1GB, 2)
            Write-Host "  ✓ Удалено файлов: $totalFiles (~$totalSizeGB ГБ)" -ForegroundColor Green
            Write-Host "  ✓ Структура папок сохранена (папки остались пустыми)" -ForegroundColor Green
        } else {
            Write-Host "  Папка media/ уже пуста" -ForegroundColor Gray
        }
    } else {
        Write-Host "  Папка media/ не найдена" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Очистка завершена!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Показываем итоговое использование
Write-Host "Итоговое использование дискового пространства Docker:" -ForegroundColor Yellow
docker system df
Write-Host ""

# Проверяем контейнеры после очистки
$stillRunning = docker ps -q
$stillStopped = docker ps -a -q -f "status=exited"

if ($stillRunning) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Работающие контейнеры (все в порядке):" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    Write-Host ""
    Write-Host "✓ Все работающие контейнеры сохранены и продолжают работать" -ForegroundColor Green
    Write-Host ""
}

if ($stillStopped) {
    Write-Host "Остановленные контейнеры (остались, не были удалены):" -ForegroundColor Yellow
    docker ps -a -f "status=exited" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    Write-Host ""
}

# Проверяем volumes
$remainingVolumes = docker volume ls -q
if ($remainingVolumes) {
    Write-Host "Оставшиеся volumes:" -ForegroundColor Cyan
    docker volume ls
    Write-Host ""
    Write-Host "Примечание: Bind mounts (../media:/app/media) не отображаются здесь," -ForegroundColor Gray
    Write-Host "они хранятся в папке media/ на хосте и не были затронуты." -ForegroundColor Gray
}

Write-Host ""

