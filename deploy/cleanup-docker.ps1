# Скрипт для безопасной очистки Docker на локальном ПК
# Не затрагивает сервер, так как сервер использует свои образы

Write-Host "=== Очистка Docker на локальном ПК ===" -ForegroundColor Cyan
Write-Host ""

# Показываем текущее использование
Write-Host "Текущее использование Docker:" -ForegroundColor Yellow
docker system df
Write-Host ""

# Вариант 1: Очистка Build Cache (освободит ~12.57 GB)
Write-Host "1. Очистка Build Cache..." -ForegroundColor Green
docker builder prune -a -f
Write-Host "✓ Build Cache очищен" -ForegroundColor Green
Write-Host ""

# Вариант 2: Удаление неиспользуемых образов (освободит ~8.5 GB)
Write-Host "2. Удаление неиспользуемых образов..." -ForegroundColor Green
docker image prune -a -f
Write-Host "✓ Неиспользуемые образы удалены" -ForegroundColor Green
Write-Host ""

# Вариант 3: Удаление остановленных контейнеров
Write-Host "3. Удаление остановленных контейнеров..." -ForegroundColor Green
docker container prune -f
Write-Host "✓ Остановленные контейнеры удалены" -ForegroundColor Green
Write-Host ""

# Показываем результат
Write-Host "Результат после очистки:" -ForegroundColor Yellow
docker system df
Write-Host ""

Write-Host "=== Очистка завершена! ===" -ForegroundColor Cyan
Write-Host "Сервер не затронут, так как использует свои образы (deploy-*)" -ForegroundColor Green




