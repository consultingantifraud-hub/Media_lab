#!/bin/bash
# Автоматическая очистка Docker на сервере
# Запускается по расписанию через cron

LOG_FILE="/opt/media-lab/logs/docker-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало автоматической очистки Docker ==="

# Показываем текущее состояние
log "Текущее использование Docker:"
docker system df >> "$LOG_FILE" 2>&1

# 1. Удаление неиспользуемых образов (dangling images)
log "1. Удаление неиспользуемых образов..."
DELETED_IMAGES=$(docker image prune -f 2>&1 | grep -i "reclaimed\|deleted" | tail -1)
log "$DELETED_IMAGES"

# 2. Удаление неиспользуемого build cache (старше 24 часов)
log "2. Очистка Build Cache (старше 24 часов)..."
DELETED_CACHE=$(docker builder prune -f --filter "until=24h" 2>&1 | grep -i "reclaimed\|total" | tail -1)
log "$DELETED_CACHE"

# 3. Удаление остановленных контейнеров
log "3. Удаление остановленных контейнеров..."
DELETED_CONTAINERS=$(docker container prune -f 2>&1 | grep -i "reclaimed\|total" | tail -1)
log "$DELETED_CONTAINERS"

# 4. Удаление неиспользуемых volumes (только неиспользуемые)
log "4. Удаление неиспользуемых volumes..."
DELETED_VOLUMES=$(docker volume prune -f 2>&1 | grep -i "reclaimed\|total" | tail -1)
log "$DELETED_VOLUMES"

# Показываем результат
log "Результат после очистки:"
docker system df >> "$LOG_FILE" 2>&1

log "=== Очистка завершена успешно! ==="
log ""

# Ограничиваем размер лог-файла (оставляем последние 1000 строк)
if [ -f "$LOG_FILE" ]; then
    tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

exit 0

