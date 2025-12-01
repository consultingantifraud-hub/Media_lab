#!/bin/bash
# Скрипт архивации важных данных о пользователях в сжатом виде
# Сохраняет: users, balances, user_statistics, discount_codes
# Создает сжатый дамп для бессрочного хранения

LOG_FILE="/opt/media-lab/logs/postgres-archive.log"
ARCHIVE_DIR="/opt/backups/media-lab/archive"
DATE=$(date '+%Y%m%d_%H%M%S')
ARCHIVE_FILE="$ARCHIVE_DIR/users_archive_$DATE.sql.gz"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$ARCHIVE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Начало архивации данных пользователей ==="

# Проверяем, что контейнер PostgreSQL запущен
if ! docker ps | grep -q deploy-postgres-1; then
    log "❌ Контейнер PostgreSQL не запущен!"
    exit 1
fi

# Показываем статистику перед архивацией
log "Статистика данных перед архивацией:"
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab <<EOF >> "$LOG_FILE" 2>&1
SELECT 
    'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'balances', COUNT(*) FROM balances
UNION ALL
SELECT 'user_statistics', COUNT(*) FROM user_statistics
UNION ALL
SELECT 'discount_codes', COUNT(*) FROM discount_codes
UNION ALL
SELECT 'operations', COUNT(*) FROM operations
UNION ALL
SELECT 'payments', COUNT(*) FROM payments;
EOF

# Создаем сжатый дамп важных таблиц
log "Создание архива важных данных..."
docker exec deploy-postgres-1 pg_dump -U media_lab_user -d media_lab \
    --table=users \
    --table=balances \
    --table=user_statistics \
    --table=discount_codes \
    --table=user_discount_codes \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    --format=plain \
    2>> "$LOG_FILE" | gzip > "$ARCHIVE_FILE"

if [ $? -eq 0 ] && [ -f "$ARCHIVE_FILE" ]; then
    ARCHIVE_SIZE=$(du -h "$ARCHIVE_FILE" | cut -f1)
    log "✅ Архив создан: $ARCHIVE_FILE ($ARCHIVE_SIZE)"
else
    log "❌ Ошибка при создании архива!"
    exit 1
fi

# Удаляем старые архивы (старше 1 года, оставляем последние 12)
log "Очистка старых архивов (старше 1 года)..."
find "$ARCHIVE_DIR" -name "users_archive_*.sql.gz" -mtime +365 -delete 2>/dev/null
KEPT_ARCHIVES=$(ls -1t "$ARCHIVE_DIR"/users_archive_*.sql.gz 2>/dev/null | wc -l)
log "✅ Сохранено архивов: $KEPT_ARCHIVES (последние 12 месяцев)"

log "=== Архивация завершена! ==="
log ""

exit 0

