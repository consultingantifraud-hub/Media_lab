#!/bin/bash
# Скрипт очистки старых данных и логов
# Выполняется еженедельно

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOG_FILE="/opt/media-lab/logs/cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Создаем директорию для логов если её нет
mkdir -p "$(dirname "$LOG_FILE")"

# Функция для логирования
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Начало очистки старых данных Media Lab ==="

# Очистка старых логов (старше 30 дней)
if [ -d "$PROJECT_DIR/logs" ]; then
    log "Очистка старых логов (старше 30 дней)..."
    DELETED=$(find "$PROJECT_DIR/logs" -name "*.log" -mtime +30 -delete -print | wc -l)
    log "✅ Логи очищены: удалено $DELETED файлов"
fi

# Очистка старых медиа файлов (старше 30 дней)
# Медиа файлы не нужны на сервере, удаляем чаще
if [ -d "$PROJECT_DIR/media" ]; then
    log "Очистка старых медиа файлов (старше 30 дней)..."
    DELETED=$(find "$PROJECT_DIR/media" -type f -mtime +30 -delete -print | wc -l)
    SIZE_FREED=$(find "$PROJECT_DIR/media" -type f -mtime +30 -exec du -ch {} + 2>/dev/null | tail -1 | cut -f1 || echo "0")
    log "✅ Медиа файлы очищены: удалено $DELETED файлов, освобождено $SIZE_FREED"
fi

# Очистка старых резервных копий (старше 30 дней)
if [ -d "/opt/backups/media-lab" ]; then
    log "Очистка старых резервных копий (старше 30 дней)..."
    find /opt/backups/media-lab -name "*.tar.gz" -mtime +30 -delete
    find /opt/backups/media-lab -name "*.rdb" -mtime +30 -delete
    log "✅ Резервные копии очищены"
fi

log "=== Очистка завершена! ==="
log ""


