#!/bin/bash
# Скрипт для автоматической очистки старых медиа файлов
# Удаляет файлы старше указанного времени

REPO_DIR="/opt/media-lab"
MEDIA_DIR="$REPO_DIR/media"
LOG_FILE="$REPO_DIR/logs/cleanup_media.log"

# Настройки
MAX_AGE_HOURS=24  # Удалять файлы старше 24 часов (1 день)
MIN_AGE_MINUTES=30  # Не удалять файлы младше 30 минут (защита от случайного удаления активных задач)

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Начало очистки старых медиа файлов ==="

if [ ! -d "$MEDIA_DIR" ]; then
    log "❌ Директория media не найдена: $MEDIA_DIR"
    exit 1
fi

# Подсчитываем файлы до очистки
TOTAL_FILES_BEFORE=$(find "$MEDIA_DIR" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.webp" -o -name "*.mp4" -o -name "*.avi" -o -name "*.mov" \) 2>/dev/null | wc -l)
TOTAL_SIZE_BEFORE=$(du -sh "$MEDIA_DIR" 2>/dev/null | awk '{print $1}')

log "Файлов до очистки: $TOTAL_FILES_BEFORE"
log "Размер media/ до очистки: $TOTAL_SIZE_BEFORE"

if [ "$TOTAL_FILES_BEFORE" -eq 0 ]; then
    log "✅ Нет медиа файлов для очистки"
    exit 0
fi

# Вычисляем временные метки
CURRENT_TIME=$(date +%s)
MAX_AGE_SECONDS=$((MAX_AGE_HOURS * 3600))
MIN_AGE_SECONDS=$((MIN_AGE_MINUTES * 60))
CUTOFF_TIME=$((CURRENT_TIME - MAX_AGE_SECONDS))
PROTECTION_TIME=$((CURRENT_TIME - MIN_AGE_SECONDS))

log "Удаляем файлы старше: $MAX_AGE_HOURS часов"
log "Защита: не удаляем файлы младше $MIN_AGE_MINUTES минут"

# Счетчики
DELETED_COUNT=0
PROTECTED_COUNT=0
ERROR_COUNT=0
DELETED_SIZE=0

# Функция для удаления файла
delete_file() {
    local file="$1"
    local file_age=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null)
    
    if [ -z "$file_age" ]; then
        log "⚠️  Не удалось получить возраст файла: $file"
        ERROR_COUNT=$((ERROR_COUNT + 1))
        return 1
    fi
    
    # Проверяем защиту (не удаляем слишком свежие файлы)
    if [ "$file_age" -gt "$PROTECTION_TIME" ]; then
        PROTECTED_COUNT=$((PROTECTED_COUNT + 1))
        return 0
    fi
    
    # Удаляем старые файлы
    if [ "$file_age" -lt "$CUTOFF_TIME" ]; then
        local file_size=$(stat -c %s "$file" 2>/dev/null || stat -f %z "$file" 2>/dev/null)
        local file_age_hours=$(( (CURRENT_TIME - file_age) / 3600 ))
        
        if rm -f "$file" 2>/dev/null; then
            DELETED_COUNT=$((DELETED_COUNT + 1))
            if [ -n "$file_size" ]; then
                DELETED_SIZE=$((DELETED_SIZE + file_size))
            fi
            if [ "$DELETED_COUNT" -le 10 ]; then
                log "  ✓ Удален: $(basename "$file") (возраст: ${file_age_hours}ч)"
            fi
        else
            log "  ✗ Ошибка удаления: $file"
            ERROR_COUNT=$((ERROR_COUNT + 1))
        fi
    fi
}

# Обрабатываем файлы
log "Обработка файлов..."

# Находим и удаляем старые файлы
find "$MEDIA_DIR" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.webp" -o -name "*.mp4" -o -name "*.avi" -o -name "*.mov" \) -print0 2>/dev/null | while IFS= read -r -d '' file; do
    delete_file "$file"
done

# Подсчитываем файлы после очистки
TOTAL_FILES_AFTER=$(find "$MEDIA_DIR" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.webp" -o -name "*.mp4" -o -name "*.avi" -o -name "*.mov" \) 2>/dev/null | wc -l)
TOTAL_SIZE_AFTER=$(du -sh "$MEDIA_DIR" 2>/dev/null | awk '{print $1}')

# Форматируем размер
DELETED_SIZE_MB=$((DELETED_SIZE / 1024 / 1024))

log ""
log "=== Результаты очистки ==="
log "  Удалено файлов: $DELETED_COUNT"
log "  Защищено файлов: $PROTECTED_COUNT (младше $MIN_AGE_MINUTES минут)"
log "  Ошибок: $ERROR_COUNT"
log "  Освобождено места: ~${DELETED_SIZE_MB}MB"
log ""
log "  Файлов до: $TOTAL_FILES_BEFORE"
log "  Файлов после: $TOTAL_FILES_AFTER"
log "  Размер до: $TOTAL_SIZE_BEFORE"
log "  Размер после: $TOTAL_SIZE_AFTER"

if [ "$DELETED_COUNT" -gt 0 ]; then
    log "✅ Очистка завершена успешно"
else
    log "✅ Нет файлов для удаления"
fi

log ""
exit 0

