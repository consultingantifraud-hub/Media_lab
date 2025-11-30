#!/bin/bash
# Улучшенный скрипт автоматической очистки сервера
# Учитывает увеличенные ресурсы (Redis 4GB, 10 воркеров, API 2GB)
# Выполняется ежедневно в 02:00 по московскому времени

LOG_FILE="/opt/media-lab/logs/docker-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало улучшенной очистки сервера Media Lab ==="

# Показываем текущее состояние
log "Текущее использование Docker:"
docker system df >> "$LOG_FILE" 2>&1

# Показываем состояние Redis
log "Текущее состояние Redis:"
docker exec deploy-redis-1 redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio' >> "$LOG_FILE" 2>&1 || log "⚠️ Не удалось получить информацию о Redis"

# Показываем количество задач в Redis
JOB_COUNT=$(docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | wc -l)
log "Задач в Redis (rq:job:*): $JOB_COUNT"

# 1. Очистка старых задач RQ в Redis (старше 7 дней)
log "1. Очистка старых задач RQ в Redis (старше 7 дней)..."
CLEANED_JOBS=0
SEVEN_DAYS_AGO=$(date -d '7 days ago' +%s 2>/dev/null || date -v-7d +%s 2>/dev/null || echo "0")

if [ "$SEVEN_DAYS_AGO" != "0" ]; then
    # Получаем все задачи и проверяем их возраст
    docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | while read job_key; do
        CREATED_AT=$(docker exec deploy-redis-1 redis-cli HGET "$job_key" "created_at" 2>/dev/null)
        if [ -n "$CREATED_AT" ]; then
            # Парсим ISO дату и сравниваем
            JOB_TIMESTAMP=$(date -d "$CREATED_AT" +%s 2>/dev/null || echo "0")
            if [ "$JOB_TIMESTAMP" != "0" ] && [ "$JOB_TIMESTAMP" -lt "$SEVEN_DAYS_AGO" ]; then
                docker exec deploy-redis-1 redis-cli DEL "$job_key" >/dev/null 2>&1 && ((CLEANED_JOBS++))
            fi
        fi
    done
    log "✓ Очищено старых задач RQ: $CLEANED_JOBS"
else
    # Альтернативный метод: удаляем задачи, которые не обновлялись более 7 дней
    log "Используем альтернативный метод очистки (по времени последнего обновления)..."
    docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | while read job_key; do
        # Проверяем, есть ли у задачи время завершения
        ENDED_AT=$(docker exec deploy-redis-1 redis-cli HGET "$job_key" "ended_at" 2>/dev/null)
        if [ -n "$ENDED_AT" ]; then
            # Если задача завершена более 7 дней назад, удаляем
            ENDED_TIMESTAMP=$(date -d "$ENDED_AT" +%s 2>/dev/null || echo "0")
            if [ "$ENDED_TIMESTAMP" != "0" ] && [ "$ENDED_TIMESTAMP" -lt "$SEVEN_DAYS_AGO" ]; then
                docker exec deploy-redis-1 redis-cli DEL "$job_key" >/dev/null 2>&1 && ((CLEANED_JOBS++))
            fi
        fi
    done
    log "✓ Очищено завершенных задач RQ: $CLEANED_JOBS"
fi

# 2. Очистка временных файлов в /tmp (старше 7 дней)
log "2. Очистка временных файлов в /tmp (старше 7 дней)..."
TMP_CLEANED=$(find /tmp -maxdepth 1 -type f \( -name "*.py" -o -name "*.db" -o -name "*.log" -o -name "*.sh" \) -mtime +7 -delete -print 2>/dev/null | wc -l)
log "✓ Удалено временных файлов: $TMP_CLEANED"

# 3. Удаление неиспользуемых образов Docker (dangling images)
log "3. Удаление неиспользуемых образов Docker..."
DELETED_IMAGES=$(docker image prune -f 2>&1 | grep -i "reclaimed\|deleted" | tail -1 || echo "0B")
log "✓ $DELETED_IMAGES"

# 4. Очистка Build Cache (старше 24 часов)
log "4. Очистка Build Cache (старше 24 часов)..."
DELETED_CACHE=$(docker builder prune -f --filter "until=24h" 2>&1 | grep -i "reclaimed\|total" | tail -1 || echo "0B")
log "✓ $DELETED_CACHE"

# 5. Удаление остановленных контейнеров
log "5. Удаление остановленных контейнеров..."
DELETED_CONTAINERS=$(docker container prune -f 2>&1 | grep -i "reclaimed\|total" | tail -1 || echo "0B")
log "✓ $DELETED_CONTAINERS"

# 6. Удаление неиспользуемых volumes (только неиспользуемые)
log "6. Удаление неиспользуемых volumes..."
DELETED_VOLUMES=$(docker volume prune -f 2>&1 | grep -i "reclaimed\|total" | tail -1 || echo "0B")
log "✓ $DELETED_VOLUMES"

# Показываем результат
log "Результат после очистки:"
docker system df >> "$LOG_FILE" 2>&1

# Финальное состояние Redis
log "Финальное состояние Redis:"
docker exec deploy-redis-1 redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio' >> "$LOG_FILE" 2>&1 || log "⚠️ Не удалось получить информацию о Redis"

FINAL_JOB_COUNT=$(docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | wc -l)
log "Задач в Redis после очистки: $FINAL_JOB_COUNT (было: $JOB_COUNT)"

log "=== Очистка завершена успешно! ==="
log ""

# Ограничиваем размер лог-файла (оставляем последние 2000 строк)
if [ -f "$LOG_FILE" ]; then
    tail -n 2000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

exit 0

