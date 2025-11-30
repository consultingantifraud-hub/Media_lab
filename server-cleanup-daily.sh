#!/bin/bash
# Ежедневная автоматическая очистка Docker на сервере
# Выполняется в 02:00 по московскому времени

LOG_FILE="/opt/media-lab/logs/docker-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало ежедневной очистки Docker ==="

# Показываем текущее состояние
log "Текущее использование Docker:"
docker system df >> "$LOG_FILE" 2>&1

# 1. Удаление неиспользуемых образов (dangling images)
log "1. Удаление неиспользуемых образов..."
docker image prune -f >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✓ Неиспользуемые образы удалены"
else
    log "✗ Ошибка при удалении образов"
fi

# 2. Удаление всего неиспользуемого build cache (без фильтра по времени)
log "2. Очистка Build Cache (все неиспользуемые кэши)..."
docker builder prune -af >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✓ Build cache очищен"
else
    log "✗ Ошибка при очистке build cache"
fi

# 3. Удаление остановленных контейнеров
log "3. Удаление остановленных контейнеров..."
docker container prune -f >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✓ Остановленные контейнеры удалены"
else
    log "✗ Ошибка при удалении контейнеров"
fi

# 4. Удаление неиспользуемых volumes (только неиспользуемые)
log "4. Удаление неиспользуемых volumes..."
docker volume prune -f >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✓ Неиспользуемые volumes удалены"
else
    log "✗ Ошибка при удалении volumes"
fi

# Показываем результат
log "Результат после очистки:"
docker system df >> "$LOG_FILE" 2>&1

log "=== Очистка завершена! ==="
log ""

