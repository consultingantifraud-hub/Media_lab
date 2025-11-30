#!/bin/bash
# Расширенная версия автоматического коммита с улучшенной фильтрацией
# Вариант 3: Комбинированная фильтрация (белый список + черный список)

REPO_DIR="/opt/media-lab"
LOG_FILE="/opt/media-lab/logs/git_auto_commit.log"
MIN_CHANGES=1

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd "$REPO_DIR" || { log "❌ Ошибка: Не удалось перейти в $REPO_DIR"; exit 1; }

log "=== Автоматическая проверка изменений (расширенная фильтрация) ==="

git fetch origin --quiet 2>&1

CHANGED_FILES=$(git status --porcelain 2>/dev/null | wc -l)

if [ "$CHANGED_FILES" -eq 0 ]; then
    log "✅ Нет изменений. Репозиторий актуален."
    exit 0
fi

log "Обнаружено $CHANGED_FILES измененных файлов"

# === РАСШИРЕННАЯ ФИЛЬТРАЦИЯ ===

# БЕЛЫЙ СПИСОК: разрешенные расширения и паттерны
WHITELIST_PATTERNS=(
    '*.py'                    # Python код
    '*.yml' '*.yaml'          # Конфигурация
    '*.md' '*.txt'            # Документация
    '*.json'                  # JSON конфигурация
    'Dockerfile*'             # Docker файлы
    '.dockerignore'           # Docker ignore
    '.gitignore'              # Git ignore
    'requirements*.txt'       # Зависимости
    '*.sh'                    # Скрипты
    '*.env.example'           # Примеры env
    '*.conf' '*.config'       # Конфигурация
)

# ЧЕРНЫЙ СПИСОК: запрещенные паттерны и пути
BLACKLIST_PATTERNS=(
    '*.log'                   # Логи
    '*.tmp' '*.temp'          # Временные файлы
    '*.cache'                 # Кэш
    '*.pyc' '*.pyo'           # Скомпилированный Python
    '__pycache__/'            # Python кэш
    '*.db' '*.sqlite*'        # Базы данных
    '.env'                    # Секреты
    '*.swp' '*.swo'           # Vim временные
    '.DS_Store'               # macOS
    'Thumbs.db'               # Windows
    '*.bak' '*.backup'        # Бэкапы
    'logs/*'                  # Директория логов
    'media/images/*'          # Медиа файлы
    'media/videos/*'          # Медиа файлы
    '*.pid'                   # PID файлы
)

# СПЕЦИАЛЬНЫЕ ПРАВИЛА: пути, которые всегда включаются
INCLUDE_PATHS=(
    'app/'                    # Вся директория приложения
    'docker/'                 # Docker конфигурация
    'README.md'               # Основной README
    '.gitignore'              # Git ignore
)

log "Применение расширенной фильтрации..."

# Сбрасываем предыдущий индекс
git reset 2>/dev/null

# Получаем список всех измененных файлов
ALL_FILES=$(git status --porcelain | awk '{print $2}')

INCLUDED_FILES=()
EXCLUDED_FILES=()

# Фильтруем файлы
for file in $ALL_FILES; do
    # Проверяем специальные пути (всегда включаем)
    INCLUDE=false
    for pattern in "${INCLUDE_PATHS[@]}"; do
        if [[ "$file" == $pattern* ]]; then
            INCLUDED_FILES+=("$file")
            INCLUDE=true
            break
        fi
    done
    
    if [ "$INCLUDE" = true ]; then
        continue
    fi
    
    # Проверяем черный список
    EXCLUDE=false
    for pattern in "${BLACKLIST_PATTERNS[@]}"; do
        if [[ "$file" == $pattern ]] || [[ "$file" == *"/$pattern" ]] || [[ "$file" == "$pattern"* ]]; then
            EXCLUDED_FILES+=("$file")
            EXCLUDE=true
            break
        fi
    done
    
    if [ "$EXCLUDE" = true ]; then
        continue
    fi
    
    # Проверяем белый список
    for pattern in "${WHITELIST_PATTERNS[@]}"; do
        if [[ "$file" == $pattern ]] || [[ "$file" == *"/$pattern" ]]; then
            INCLUDED_FILES+=("$file")
            break
        fi
    done
done

# Показываем результаты фильтрации
if [ ${#INCLUDED_FILES[@]} -gt 0 ]; then
    log "✅ Файлы для коммита (${#INCLUDED_FILES[@]}):"
    for file in "${INCLUDED_FILES[@]:0:10}"; do
        log "   + $file"
    done
    if [ ${#INCLUDED_FILES[@]} -gt 10 ]; then
        log "   ... и еще $((${#INCLUDED_FILES[@]} - 10)) файлов"
    fi
fi

if [ ${#EXCLUDED_FILES[@]} -gt 0 ]; then
    log "❌ Исключенные файлы (${#EXCLUDED_FILES[@]}):"
    for file in "${EXCLUDED_FILES[@]:0:5}"; do
        log "   - $file"
    done
    if [ ${#EXCLUDED_FILES[@]} -gt 5 ]; then
        log "   ... и еще $((${#EXCLUDED_FILES[@]} - 5)) файлов"
    fi
fi

# Проверяем, есть ли что коммитить
if [ ${#INCLUDED_FILES[@]} -lt "$MIN_CHANGES" ]; then
    log "⚠️  После фильтрации осталось мало изменений (${#INCLUDED_FILES[@]}). Пропускаю коммит."
    exit 0
fi

# Добавляем только разрешенные файлы
for file in "${INCLUDED_FILES[@]}"; do
    git add "$file" 2>/dev/null
done

STAGED_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l)

if [ "$STAGED_COUNT" -lt "$MIN_CHANGES" ]; then
    log "⚠️  Недостаточно изменений для коммита ($STAGED_COUNT)."
    git reset 2>/dev/null
    exit 0
fi

log "✅ Готово к коммиту: $STAGED_COUNT файлов"

# Создаем коммит
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_MSG="Auto-update: $STAGED_COUNT files changed ($TIMESTAMP)"

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
    exit 1
fi

log ""
exit 0

