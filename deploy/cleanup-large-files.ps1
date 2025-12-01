# Скрипт для безопасной очистки крупных файлов
# Анализирует и предлагает варианты очистки

Write-Host "=== Анализ крупных файлов ===" -ForegroundColor Cyan
Write-Host ""

# 1. Docker диски
Write-Host "1. DOCKER ФАЙЛЫ:" -ForegroundColor Yellow
$dockerDisk = "C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
if (Test-Path $dockerDisk) {
    $size = (Get-Item $dockerDisk).Length / 1GB
    Write-Host "   docker_data.vhdx: $([math]::Round($size, 2)) GB" -ForegroundColor White
    if ($size -gt 5) {
        Write-Host "   ⚠ Можно сжать (см. shrink-docker-admin.bat)" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ✓ Не найден (уже удален)" -ForegroundColor Green
}
Write-Host ""

# 2. Ubuntu WSL диск
Write-Host "2. UBUNTU WSL ДИСК:" -ForegroundColor Yellow
$ubuntuDisk = "C:\Users\Колесник Дмитрий\AppData\Local\Packages\CanonicalGroupLimited.Ubuntu_79rhkp1fndgsc\LocalState\ext4.vhdx"
if (Test-Path $ubuntuDisk) {
    $size = (Get-Item $ubuntuDisk).Length / 1GB
    Write-Host "   ext4.vhdx: $([math]::Round($size, 2)) GB" -ForegroundColor White
    Write-Host "   ⚠ Можно очистить если Ubuntu не используется активно" -ForegroundColor Yellow
    Write-Host "   Команда: wsl --shutdown; wsl --unregister Ubuntu" -ForegroundColor Gray
} else {
    Write-Host "   ✓ Не найден" -ForegroundColor Green
}
Write-Host ""

# 3. Файл гибернации
Write-Host "3. ФАЙЛ ГИБЕРНАЦИИ:" -ForegroundColor Yellow
$hiberfil = "C:\hiberfil.sys"
if (Test-Path $hiberfil) {
    $size = (Get-Item $hiberfil).Length / 1GB
    Write-Host "   hiberfil.sys: $([math]::Round($size, 2)) GB" -ForegroundColor White
    Write-Host "   ⚠ Можно отключить (освободит ~3 GB)" -ForegroundColor Yellow
    Write-Host "   Команда (от админа): powercfg /hibernate off" -ForegroundColor Gray
    Write-Host "   ВНИМАНИЕ: Отключит режим гибернации Windows" -ForegroundColor Red
} else {
    Write-Host "   ✓ Не найден (уже отключен)" -ForegroundColor Green
}
Write-Host ""

# 4. Файл подкачки
Write-Host "4. ФАЙЛ ПОДКАЧКИ:" -ForegroundColor Yellow
$pagefile = "C:\pagefile.sys"
if (Test-Path $pagefile) {
    $size = (Get-Item $pagefile).Length / 1GB
    Write-Host "   pagefile.sys: $([math]::Round($size, 2)) GB" -ForegroundColor White
    Write-Host "   ⚠ Можно уменьшить (но не рекомендуется удалять полностью)" -ForegroundColor Yellow
    Write-Host "   Настройка: Панель управления -> Система -> Дополнительные параметры -> Быстродействие -> Виртуальная память" -ForegroundColor Gray
}
Write-Host ""

# 5. Outlook файлы
Write-Host "5. OUTLOOK ФАЙЛЫ:" -ForegroundColor Yellow
$outlookPath = "C:\Users\Колесник Дмитрий\AppData\Local\Microsoft\Outlook"
if (Test-Path $outlookPath) {
    $ostFiles = Get-ChildItem "$outlookPath\*.ost" -ErrorAction SilentlyContinue
    $pstFiles = Get-ChildItem "$outlookPath\*.pst" -ErrorAction SilentlyContinue
    $totalSize = 0
    foreach ($file in ($ostFiles + $pstFiles)) {
        $size = $file.Length / 1GB
        $totalSize += $size
        Write-Host "   $($file.Name): $([math]::Round($size, 2)) GB" -ForegroundColor White
    }
    if ($totalSize -gt 0) {
        Write-Host "   Всего: $([math]::Round($totalSize, 2)) GB" -ForegroundColor White
        Write-Host "   ⚠ Можно архивировать старые или удалить дубликаты" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ✓ Папка не найдена" -ForegroundColor Green
}
Write-Host ""

# 6. Cursor кэш
Write-Host "6. CURSOR КЭШ:" -ForegroundColor Yellow
$cursorCache = "C:\Users\Колесник Дмитрий\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
if (Test-Path $cursorCache) {
    $size = (Get-Item $cursorCache).Length / 1MB
    Write-Host "   state.vscdb: $([math]::Round($size, 2)) MB" -ForegroundColor White
    Write-Host "   ⚠ Можно очистить (кэш редактора)" -ForegroundColor Yellow
    Write-Host "   Команда: Remove-Item `"$cursorCache`" -Force" -ForegroundColor Gray
}
$cursorBackup = "C:\Users\Колесник Дмитрий\AppData\Roaming\Cursor\User\globalStorage\state.vscdb.backup"
if (Test-Path $cursorBackup) {
    $size = (Get-Item $cursorBackup).Length / 1MB
    Write-Host "   state.vscdb.backup: $([math]::Round($size, 2)) MB" -ForegroundColor White
    Write-Host "   ⚠ Можно удалить (резервная копия кэша)" -ForegroundColor Yellow
}
Write-Host ""

# 7. Windows Installer кэш
Write-Host "7. WINDOWS INSTALLER КЭШ:" -ForegroundColor Yellow
$installerPath = "C:\Windows\Installer"
if (Test-Path $installerPath) {
    $mspFiles = Get-ChildItem "$installerPath\*.msp" -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 5
    $totalSize = 0
    foreach ($file in $mspFiles) {
        $size = $file.Length / 1MB
        $totalSize += $size
        Write-Host "   $($file.Name): $([math]::Round($size, 2)) MB" -ForegroundColor White
    }
    if ($totalSize -gt 0) {
        Write-Host "   Всего (топ-5): $([math]::Round($totalSize, 2)) MB" -ForegroundColor White
        Write-Host "   ⚠ Можно очистить через 'Очистка диска' Windows" -ForegroundColor Yellow
        Write-Host "   Команда: cleanmgr /d C:" -ForegroundColor Gray
    }
}
Write-Host ""

# 8. System Volume Information
Write-Host "8. SYSTEM VOLUME INFORMATION:" -ForegroundColor Yellow
Write-Host "   ⚠ Системные файлы Windows (точки восстановления)" -ForegroundColor Yellow
Write-Host "   Можно очистить через 'Очистка диска' -> 'Очистить системные файлы'" -ForegroundColor Gray
Write-Host "   Команда: cleanmgr /d C: /sageset:1" -ForegroundColor Gray
Write-Host ""

# 9. Windows Search индекс
Write-Host "9. WINDOWS SEARCH ИНДЕКС:" -ForegroundColor Yellow
$searchDb = "C:\ProgramData\Microsoft\Search\Data\Applications\Windows\Windows.db"
if (Test-Path $searchDb) {
    $size = (Get-Item $searchDb).Length / 1MB
    Write-Host "   Windows.db: $([math]::Round($size, 2)) MB" -ForegroundColor White
    Write-Host "   ⚠ Можно пересоздать (индекс поиска)" -ForegroundColor Yellow
    Write-Host "   Команда: net stop wsearch; Remove-Item `"$searchDb`" -Force; net start wsearch" -ForegroundColor Gray
}
Write-Host ""

# 10. Python кэш
Write-Host "10. PYTHON КЭШ:" -ForegroundColor Yellow
$pythonCache = "C:\Users\Колесник Дмитрий\AppData\Local\Programs\Python"
if (Test-Path $pythonCache) {
    $pycache = Get-ChildItem "$pythonCache" -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue
    $totalSize = 0
    foreach ($dir in $pycache) {
        $size = (Get-ChildItem $dir.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
        $totalSize += $size
    }
    if ($totalSize -gt 0) {
        Write-Host "   __pycache__: $([math]::Round($totalSize, 2)) MB" -ForegroundColor White
        Write-Host "   ⚠ Можно удалить (кэш Python)" -ForegroundColor Yellow
        Write-Host "   Команда: Get-ChildItem `"$pythonCache`" -Recurse -Filter `"__pycache__`" -Directory | Remove-Item -Recurse -Force" -ForegroundColor Gray
    }
}
Write-Host ""

Write-Host "=== РЕКОМЕНДАЦИИ ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "БЕЗОПАСНО можно очистить:" -ForegroundColor Green
Write-Host "  • Cursor кэш (state.vscdb) - ~1.5 GB" -ForegroundColor White
Write-Host "  • Windows Installer кэш - через cleanmgr" -ForegroundColor White
Write-Host "  • System Volume Information - через cleanmgr" -ForegroundColor White
Write-Host "  • Windows Search индекс - можно пересоздать" -ForegroundColor White
Write-Host ""
Write-Host "ОСТОРОЖНО (требует проверки):" -ForegroundColor Yellow
Write-Host "  • Ubuntu WSL диск - если не используется" -ForegroundColor White
Write-Host "  • Outlook файлы - архивировать старые" -ForegroundColor White
Write-Host "  • Файл гибернации - отключить если не нужен" -ForegroundColor White
Write-Host ""
Write-Host "НЕ РЕКОМЕНДУЕТСЯ:" -ForegroundColor Red
Write-Host "  • pagefile.sys - можно только уменьшить" -ForegroundColor White
Write-Host ""




