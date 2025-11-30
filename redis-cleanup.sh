#!/bin/bash
# Скрипт для очистки старых задач RQ в Redis
# Можно запускать отдельно или как часть общей очистки

LOG_FILE="/opt/media-lab/logs/redis-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало очистки Redis ==="

# Показываем текущее состояние
JOB_COUNT=$(docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | wc -l)
log "Задач в Redis (rq:job:*): $JOB_COUNT"

# Показываем использование памяти
docker exec deploy-redis-1 redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio' >> "$LOG_FILE" 2>&1

# Очистка завершенных задач старше 3 дней
log "Очистка завершенных задач старше 3 дней..."
THREE_DAYS_AGO=$(date -d '3 days ago' +%s 2>/dev/null || date -v-3d +%s 2>/dev/null || echo "0")
CLEANED_COUNT=0

if [ "$THREE_DAYS_AGO" != "0" ]; then
    docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | while read job_key; do
        ENDED_AT=$(docker exec deploy-redis-1 redis-cli HGET "$job_key" "ended_at" 2>/dev/null)
        if [ -n "$ENDED_AT" ]; then
            ENDED_TIMESTAMP=$(date -d "$ENDED_AT" +%s 2>/dev/null || echo "0")
            if [ "$ENDED_TIMESTAMP" != "0" ] && [ "$ENDED_TIMESTAMP" -lt "$THREE_DAYS_AGO" ]; then
                docker exec deploy-redis-1 redis-cli DEL "$job_key" >/dev/null 2>&1 && ((CLEANED_COUNT++))
            fi
        fi
    done
    log "✓ Очищено завершенных задач: $CLEANED_COUNT"
else
    log "⚠️ Не удалось определить дату, пропускаем очистку по дате"
fi

# Очистка задач без ended_at, но с очень старым created_at (старше 14 дней)
log "Очистка очень старых задач (старше 14 дней)..."
FOURTEEN_DAYS_AGO=$(date -d '14 days ago' +%s 2>/dev/null || date -v-14d +%s 2>/dev/null || echo "0")
OLD_CLEANED=0

if [ "$FOURTEEN_DAYS_AGO" != "0" ]; then
    docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | while read job_key; do
        CREATED_AT=$(docker exec deploy-redis-1 redis-cli HGET "$job_key" "created_at" 2>/dev/null)
        if [ -n "$CREATED_AT" ]; then
            CREATED_TIMESTAMP=$(date -d "$CREATED_AT" +%s 2>/dev/null || echo "0")
            if [ "$CREATED_TIMESTAMP" != "0" ] && [ "$CREATED_TIMESTAMP" -lt "$FOURTEEN_DAYS_AGO" ]; then
                # Проверяем, что задача не активна
                ENDED_AT=$(docker exec deploy-redis-1 redis-cli HGET "$job_key" "ended_at" 2>/dev/null)
                if [ -n "$ENDED_AT" ]; then
                    docker exec deploy-redis-1 redis-cli DEL "$job_key" >/dev/null 2>&1 && ((OLD_CLEANED++))
                fi
            fi
        fi
    done
    log "✓ Очищено очень старых задач: $OLD_CLEANED"
fi

# Финальное состояние
FINAL_JOB_COUNT=$(docker exec deploy-redis-1 redis-cli --scan --pattern 'rq:job:*' 2>/dev/null | wc -l)
log "Задач в Redis после очистки: $FINAL_JOB_COUNT (было: $JOB_COUNT)"

log "Финальное состояние Redis:"
docker exec deploy-redis-1 redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio' >> "$LOG_FILE" 2>&1

log "=== Очистка Redis завершена! ==="
log ""

exit 0

