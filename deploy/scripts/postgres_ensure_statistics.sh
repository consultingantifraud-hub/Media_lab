#!/bin/bash
# Скрипт для обновления сводной статистики пользователей
# Убеждается, что все данные из operations и payments агрегированы в user_statistics
# Перед удалением детальных транзакций

LOG_FILE="/opt/media-lab/logs/postgres-statistics.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Обновление сводной статистики пользователей ==="

# Проверяем, что контейнер PostgreSQL запущен
if ! docker ps | grep -q deploy-postgres-1; then
    log "❌ Контейнер PostgreSQL не запущен!"
    exit 1
fi

# Обновляем статистику для всех пользователей
log "Обновление user_statistics из детальных данных..."

docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab <<EOF >> "$LOG_FILE" 2>&1
-- Обновляем статистику операций
INSERT INTO user_statistics (user_id, total_operations, total_spent, first_operation_at, last_operation_at, updated_at)
SELECT 
    o.user_id,
    COUNT(*) as total_operations,
    COALESCE(SUM(o.price), 0) as total_spent,
    MIN(o.created_at) as first_operation_at,
    MAX(o.created_at) as last_operation_at,
    NOW() as updated_at
FROM operations o
WHERE o.status = 'charged'
GROUP BY o.user_id
ON CONFLICT (user_id) DO UPDATE SET
    total_operations = EXCLUDED.total_operations,
    total_spent = EXCLUDED.total_spent,
    first_operation_at = LEAST(user_statistics.first_operation_at, EXCLUDED.first_operation_at),
    last_operation_at = GREATEST(user_statistics.last_operation_at, EXCLUDED.last_operation_at),
    updated_at = NOW();

-- Обновляем operations_by_type (JSON)
UPDATE user_statistics us
SET operations_by_type = sub.ops_by_type
FROM (
    SELECT 
        user_id,
        jsonb_object_agg(type, count) as ops_by_type
    FROM (
        SELECT user_id, type, COUNT(*) as count
        FROM operations
        WHERE status = 'charged'
        GROUP BY user_id, type
    ) t
    GROUP BY user_id
) sub
WHERE us.user_id = sub.user_id;

-- Обновляем models_used (JSON)
UPDATE user_statistics us
SET models_used = sub.models
FROM (
    SELECT 
        user_id,
        jsonb_object_agg(model, count) as models
    FROM (
        SELECT user_id, model, COUNT(*) as count
        FROM operations
        WHERE status = 'charged' AND model IS NOT NULL
        GROUP BY user_id, model
    ) t
    GROUP BY user_id
) sub
WHERE us.user_id = sub.user_id;
EOF

if [ $? -eq 0 ]; then
    log "✅ Сводная статистика обновлена успешно"
else
    log "⚠️ Ошибка при обновлении статистики"
fi

log "=== Обновление завершено! ==="
log ""

exit 0

