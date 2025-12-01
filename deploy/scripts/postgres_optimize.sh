#!/bin/bash
# Скрипт оптимизации PostgreSQL
# Выполняет VACUUM ANALYZE, REINDEX и очистку старых данных
# Рекомендуется запускать еженедельно

LOG_FILE="/opt/media-lab/logs/postgres-optimize.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')
PROJECT_DIR="/opt/media-lab/deploy"

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало оптимизации PostgreSQL ==="

# Проверяем, что контейнер PostgreSQL запущен
if ! docker ps | grep -q deploy-postgres-1; then
    log "❌ Контейнер PostgreSQL не запущен!"
    exit 1
fi

# Показываем текущее состояние БД
log "Текущий размер БД:"
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "SELECT pg_size_pretty(pg_database_size('media_lab')) AS db_size;" >> "$LOG_FILE" 2>&1

# Показываем статистику по таблицам
log "Статистика по таблицам (мертвые строки):"
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "SELECT schemaname, relname as tablename, n_dead_tup, n_live_tup, last_vacuum, last_autovacuum FROM pg_stat_user_tables ORDER BY n_dead_tup DESC NULLS LAST LIMIT 10;" >> "$LOG_FILE" 2>&1

# 1. VACUUM ANALYZE для всех таблиц
log "1. Выполнение VACUUM ANALYZE для всех таблиц..."
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "VACUUM ANALYZE;" >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✅ VACUUM ANALYZE выполнен успешно"
else
    log "⚠️ Ошибка при выполнении VACUUM ANALYZE"
fi

# 2. REINDEX для всех индексов (выполняется реже, так как занимает больше времени)
# Выполняем только если это не ежедневный запуск (можно добавить проверку параметра)
if [ "$1" = "--full" ]; then
    log "2. Выполнение REINDEX для всех индексов (полная оптимизация)..."
    docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "REINDEX DATABASE media_lab;" >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        log "✅ REINDEX выполнен успешно"
    else
        log "⚠️ Ошибка при выполнении REINDEX"
    fi
else
    log "2. REINDEX пропущен (используйте --full для полной оптимизации)"
fi

# 3. Обновление сводной статистики перед очисткой
log "3. Обновление сводной статистики из детальных данных..."
if [ -f "$(dirname "$0")/postgres_ensure_statistics.sh" ]; then
    "$(dirname "$0")/postgres_ensure_statistics.sh" >> "$LOG_FILE" 2>&1
    log "✅ Статистика обновлена"
else
    log "⚠️ Скрипт обновления статистики не найден"
fi

# 4. Очистка старых ДЕТАЛЬНЫХ транзакций (только детали, сводная информация сохраняется)
# ВАЖНО: Данные о пользователях (users, balances, user_statistics) сохраняются БЕССРОЧНО
log "4. Очистка старых детальных транзакций (старше 180 дней)..."
log "   ⚠️ Данные о пользователях и сводная статистика сохраняются бессрочно"

# Удаляем только детальные операции (сводная информация уже в user_statistics)
CLEANED_OPERATIONS=$(docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "WITH deleted AS (DELETE FROM operations WHERE created_at < NOW() - INTERVAL '180 days' RETURNING 1) SELECT COUNT(*) FROM deleted;" 2>/dev/null | tr -d ' ' || echo "0")

# Удаляем только детальные платежи (сводная информация уже в user_statistics)
CLEANED_PAYMENTS=$(docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "WITH deleted AS (DELETE FROM payments WHERE created_at < NOW() - INTERVAL '180 days' RETURNING 1) SELECT COUNT(*) FROM deleted;" 2>/dev/null | tr -d ' ' || echo "0")

# Удаляем старые вопросы AI ассистента (не нужны для продаж)
CLEANED_QUESTIONS=$(docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "WITH deleted AS (DELETE FROM ai_assistant_questions WHERE created_at < NOW() - INTERVAL '90 days' RETURNING 1) SELECT COUNT(*) FROM deleted;" 2>/dev/null | tr -d ' ' || echo "0")

# Удаляем старые связи пользователей с промокодами (старше 180 дней)
CLEANED_USER_DISCOUNTS=$(docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "WITH deleted AS (DELETE FROM user_discount_codes WHERE used_at < NOW() - INTERVAL '180 days' RETURNING 1) SELECT COUNT(*) FROM deleted;" 2>/dev/null | tr -d ' ' || echo "0")

log "✅ Удалено старых детальных записей:"
log "   - Детальные операции (старше 180 дней): $CLEANED_OPERATIONS"
log "   - Детальные платежи (старше 180 дней): $CLEANED_PAYMENTS"
log "   - Вопросы AI ассистента (старше 90 дней): $CLEANED_QUESTIONS"
log "   - Связи с промокодами (старше 180 дней): $CLEANED_USER_DISCOUNTS"
log "   ✅ Сохранено бессрочно: users, balances, user_statistics, discount_codes"

# 5. Финальный VACUUM после очистки
log "5. Финальный VACUUM после очистки данных..."
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "VACUUM;" >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    log "✅ Финальный VACUUM выполнен успешно"
fi

# Показываем результат
log "Финальный размер БД:"
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "SELECT pg_size_pretty(pg_database_size('media_lab')) AS db_size;" >> "$LOG_FILE" 2>&1

log "=== Оптимизация PostgreSQL завершена! ==="
log ""

# Ограничиваем размер лог-файла (оставляем последние 2000 строк)
if [ -f "$LOG_FILE" ]; then
    tail -n 2000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

exit 0

