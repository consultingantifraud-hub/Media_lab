#!/bin/bash
# Автоматический коммит с умной фильтрацией
# Используется в cron для периодических обновлений

REPO_DIR="/opt/media-lab"
LOG_FILE="/opt/media-lab/logs/git_auto_commit.log"
MIN_CHANGES=1  # Минимальное количество изменений для коммита

# Создаем директорию для логов, если её нет
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd "$REPO_DIR" || { log "❌ Ошибка: Не удалось перейти в $REPO_DIR"; exit 1; }

log "=== Начало автоматической проверки изменений ==="

# Обновляем информацию с GitHub
git fetch origin --quiet 2>&1

# Проверяем, есть ли изменения для коммита
CHANGED_FILES=$(git status --porcelain 2>/dev/null | wc -l)

if [ "$CHANGED_FILES" -eq 0 ]; then
    log "✅ Нет изменений. Репозиторий актуален."
    exit 0
fi

log "Обнаружено $CHANGED_FILES измененных файлов"

# Показываем, какие файлы изменены (только важные)
IMPORTANT_CHANGES=$(git status --porcelain | grep -E '\.(py|yml|yaml|txt|md|dockerfile|dockerignore|gitignore)$' | head -10)
TEMP_CHANGES=$(git status --porcelain | grep -E '\.(log|tmp|cache)$' || true)

if [ -n "$IMPORTANT_CHANGES" ]; then
    log "📝 Важные изменения:"
    echo "$IMPORTANT_CHANGES" | while read line; do
        log "   $line"
    done
fi

# Фильтруем изменения - добавляем только важные файлы
git reset 2>/dev/null  # Сбрасываем предыдущие add

# Добавляем только важные файлы
git add -A 2>/dev/null

# Удаляем временные и ненужные файлы из индекса
git reset HEAD -- '*.log' '*.tmp' '*.cache' '__pycache__/' '*.pyc' 2>/dev/null || true

# Проверяем, что осталось после фильтрации
STAGED_CHANGES=$(git diff --cached --name-only 2>/dev/null | wc -l)

if [ "$STAGED_CHANGES" -lt "$MIN_CHANGES" ]; then
    log "⚠️  После фильтрации осталось мало изменений ($STAGED_CHANGES). Пропускаю коммит."
    git reset 2>/dev/null
    exit 0
fi

log "✅ Готово к коммиту: $STAGED_CHANGES файлов"

# Показываем, что будет закоммичено
COMMIT_FILES=$(git diff --cached --name-only 2>/dev/null | head -5)
log "Файлы для коммита:"
echo "$COMMIT_FILES" | while read file; do
    log "   + $file"
done
if [ "$STAGED_CHANGES" -gt 5 ]; then
    log "   ... и еще $((STAGED_CHANGES - 5)) файлов"
fi

# Создаем коммит с автоматическим сообщением
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_MSG="Auto-update: $STAGED_CHANGES files changed ($TIMESTAMP)"

log "Создание коммита: $COMMIT_MSG"
git commit -m "$COMMIT_MSG" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    log "❌ Ошибка при создании коммита."
    git reset 2>/dev/null
    exit 1
fi

# Отправляем на GitHub
log "Отправка на GitHub..."
git push origin main >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    COMMIT_HASH=$(git log -1 --format="%h")
    log "✅ УСПЕХ! Коммит $COMMIT_HASH отправлен на GitHub"
    log "=== Завершено успешно ==="
else
    log "❌ Ошибка при отправке на GitHub."
    log "Проверьте подключение и права доступа."
    exit 1
fi

log ""
exit 0

