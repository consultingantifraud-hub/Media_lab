# Скрипт для очистки кэша Telegram Desktop
# Безопасно удаляет только кэш, сохраняя чаты и настройки

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Telegram Desktop Cache Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$telegramPath = "$env:APPDATA\Telegram Desktop\tdata"
$userDataPath = Join-Path $telegramPath "user_data"

# Проверяем наличие Telegram Desktop
if (-not (Test-Path $telegramPath)) {
    Write-Host "Error: Telegram Desktop not found!" -ForegroundColor Red
    Write-Host "Path: $telegramPath" -ForegroundColor Gray
    pause
    exit 1
}

if (-not (Test-Path $userDataPath)) {
    Write-Host "Error: user_data folder not found!" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "Telegram Desktop found!" -ForegroundColor Green
Write-Host ""

# Проверяем размер кэша
$mediaCachePath = Join-Path $userDataPath "media_cache"
$cachePath = Join-Path $userDataPath "cache"

$mediaCacheSize = 0
$cacheSize = 0
$fileCount = 0

if (Test-Path $mediaCachePath) {
    $mediaFiles = Get-ChildItem $mediaCachePath -Recurse -File -ErrorAction SilentlyContinue
    $mediaCacheSize = ($mediaFiles | Measure-Object -Property Length -Sum).Sum
    $fileCount += $mediaFiles.Count
}

if (Test-Path $cachePath) {
    $cacheFiles = Get-ChildItem $cachePath -Recurse -File -ErrorAction SilentlyContinue
    $cacheSize = ($cacheFiles | Measure-Object -Property Length -Sum).Sum
    $fileCount += $cacheFiles.Count
}

$totalSize = $mediaCacheSize + $cacheSize

if ($totalSize -eq 0) {
    Write-Host "Cache is already empty!" -ForegroundColor Green
    pause
    exit 0
}

Write-Host "Current cache size:" -ForegroundColor Yellow
Write-Host "  media_cache: $([math]::Round($mediaCacheSize/1GB,2)) GB ($([math]::Round($mediaCacheSize/1MB,0)) MB)" -ForegroundColor White
Write-Host "  cache: $([math]::Round($cacheSize/1GB,2)) GB ($([math]::Round($cacheSize/1MB,0)) MB)" -ForegroundColor White
Write-Host "  Total: $([math]::Round($totalSize/1GB,2)) GB ($([math]::Round($totalSize/1MB,0)) MB)" -ForegroundColor Cyan
Write-Host "  Files: $fileCount" -ForegroundColor White
Write-Host ""

Write-Host "What will be deleted:" -ForegroundColor Yellow
Write-Host "  - Cached media files (images, videos, documents)" -ForegroundColor White
Write-Host "  - Temporary cache files" -ForegroundColor White
Write-Host ""
Write-Host "What will be preserved:" -ForegroundColor Green
Write-Host "  - All your chats and messages" -ForegroundColor White
Write-Host "  - Settings and preferences" -ForegroundColor White
Write-Host "  - Contacts and account data" -ForegroundColor White
Write-Host "  - Downloaded files (if any)" -ForegroundColor White
Write-Host ""

Write-Host "Note: Telegram will re-download media when you open chats." -ForegroundColor Gray
Write-Host ""

$confirmation = Read-Host "Continue with cache cleanup? (Y/N)"
if ($confirmation -ne "Y" -and $confirmation -ne "y") {
    Write-Host "Operation cancelled." -ForegroundColor Yellow
    pause
    exit 0
}

Write-Host ""
Write-Host "Cleaning cache..." -ForegroundColor Cyan

# Закрываем Telegram Desktop если запущен
$telegramProcess = Get-Process -Name "Telegram" -ErrorAction SilentlyContinue
if ($telegramProcess) {
    Write-Host "  Closing Telegram Desktop..." -ForegroundColor Yellow
    $telegramProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$deletedFiles = 0
$deletedSize = 0

# Удаляем media_cache
if (Test-Path $mediaCachePath) {
    Write-Host "  Cleaning media_cache..." -ForegroundColor Gray
    $files = Get-ChildItem $mediaCachePath -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        try {
            Remove-Item $file.FullName -Force -ErrorAction SilentlyContinue
            $deletedFiles++
            $deletedSize += $file.Length
        } catch {
            # Ignore errors
        }
    }
    Write-Host "    Deleted $($files.Count) files" -ForegroundColor Green
}

# Удаляем cache
if (Test-Path $cachePath) {
    Write-Host "  Cleaning cache..." -ForegroundColor Gray
    $files = Get-ChildItem $cachePath -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        try {
            Remove-Item $file.FullName -Force -ErrorAction SilentlyContinue
            $deletedFiles++
            $deletedSize += $file.Length
        } catch {
            # Ignore errors
        }
    }
    Write-Host "    Deleted $($files.Count) files" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cleanup completed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Deleted:" -ForegroundColor Yellow
Write-Host "  Files: $deletedFiles" -ForegroundColor White
Write-Host "  Size: $([math]::Round($deletedSize/1GB,2)) GB ($([math]::Round($deletedSize/1MB,0)) MB)" -ForegroundColor Green
Write-Host ""

if ($telegramProcess) {
    Write-Host "Telegram Desktop was closed. You can restart it now." -ForegroundColor Yellow
}

Write-Host ""
pause








