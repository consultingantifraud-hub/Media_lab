#!/bin/bash
# Улучшенная версия с префиксами для каждого контейнера и фильтрацией логов скачивания
# Использует docker logs с параллельным выводом в реальном времени
# Оптимизирован для работы через SSH без обрывов

CONTAINERS=(
    "deploy-bot-1"
    "deploy-worker-image-1"
    "deploy-worker-image-2-1"
    "deploy-worker-image-3-1"
    "deploy-worker-image-4-1"
    "deploy-worker-image-5-1"
    "deploy-worker-image-6-1"
    "deploy-worker-image-7-1"
    "deploy-worker-image-8-1"
    "deploy-worker-image-9-1"
    "deploy-worker-image-10-1"
    "deploy-worker-image-11-1"
    "deploy-worker-image-12-1"
    "deploy-worker-image-13-1"
    "deploy-worker-image-14-1"
    "deploy-worker-image-15-1"
    "docker-worker-image-1"
    "docker-worker-image-2"
    "docker-worker-image-3"
    "docker-worker-image-4"
    "docker-worker-image-5"
    "deploy-api-1"
    "deploy-redis-1"
)

# Парсим аргументы
FILTER_DOWNLOAD=false
TAIL_LINES=50
FOLLOW_MODE=true
WORKER_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --download|-d)
            FILTER_DOWNLOAD=true
            shift
            ;;
        --tail|-t)
            TAIL_LINES="$2"
            shift 2
            ;;
        --no-follow|-n)
            FOLLOW_MODE=false
            shift
            ;;
        --worker|-w)
            WORKER_ONLY=true
            shift
            ;;
        --worker-only)
            WORKER_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Использование: $0 [OPTIONS]"
            echo ""
            echo "Опции:"
            echo "  --download, -d          Показывать только логи скачивания"
            echo "  --tail N, -t N          Показать последние N строк перед follow (по умолчанию: 50)"
            echo "  --no-follow, -n         Не следовать за логами (только показать последние строки)"
            echo "  --worker, -w            Показывать только логи воркеров"
            echo "  --worker-only           Показывать только логи воркеров"
            echo "  --help, -h              Показать эту справку"
            echo ""
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $1"
            echo "Используйте --help для справки"
            exit 1
            ;;
    esac
done

# Проверяем запущенные контейнеры
RUNNING=()
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        RUNNING+=("$container")
    fi
done

# Автоматически находим все контейнеры с "worker" в имени, если включен фильтр воркеров
if [ "$WORKER_ONLY" = true ]; then
    WORKER_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -i worker || true)
    RUNNING=()
    while IFS= read -r container; do
        if [[ -n "$container" ]]; then
            RUNNING+=("$container")
        fi
    done <<< "$WORKER_CONTAINERS"
fi

# Если не найден ни один контейнер, пытаемся найти автоматически
if [ ${#RUNNING[@]} -eq 0 ]; then
    if [ "$WORKER_ONLY" = true ]; then
        WORKER_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -i worker || true)
        while IFS= read -r container; do
            if [[ -n "$container" ]]; then
                RUNNING+=("$container")
            fi
        done <<< "$WORKER_CONTAINERS"
    else
        # Ищем все контейнеры с bot, worker, api, redis
        ALL_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -E '(bot|worker|api|redis)' || true)
        while IFS= read -r container; do
            if [[ -n "$container" ]]; then
                RUNNING+=("$container")
            fi
        done <<< "$ALL_CONTAINERS"
    fi
fi

if [ ${#RUNNING[@]} -eq 0 ]; then
    echo "Не найдены запущенные контейнеры"
    exit 1
fi

# Проверяем аргументы для фильтрации
if [ "$FILTER_DOWNLOAD" = true ]; then
    echo "📥 Режим мониторинга скачивания включен"
fi

echo "Просмотр логов: ${RUNNING[*]}"
if [ "$FILTER_DOWNLOAD" = true ]; then
    echo "Фильтр: только логи скачивания (DOWNLOAD, ASYNC, SYNC, SCHEDULING)"
fi
if [ "$FOLLOW_MODE" = true ]; then
    echo "Режим: реальное время (последние $TAIL_LINES строк + follow)"
    echo "Нажмите Ctrl+C для остановки"
else
    echo "Режим: только последние $TAIL_LINES строк"
fi
echo ""

# Функция для обработки сигналов
cleanup() {
    echo ""
    echo "Остановка просмотра логов..."
    # Убиваем все фоновые процессы
    jobs -p | xargs -r kill 2>/dev/null
    pkill -P $$ 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Отключаем буферизацию
export PYTHONUNBUFFERED=1

# Функция для вывода логов контейнера с префиксом (без буферизации)
log_container() {
    local container="$1"
    local prefix="[$container]"
    
    # Используем stdbuf для отключения буферизации
    if command -v stdbuf >/dev/null 2>&1; then
        if [ "$FOLLOW_MODE" = true ]; then
            # Показываем последние строки без буферизации
            docker logs --tail "$TAIL_LINES" "$container" 2>&1 | stdbuf -oL -eL awk -v prefix="$prefix" '{print prefix " " $0}'
            # Затем следуем за новыми логами без буферизации
            docker logs -f --tail 0 "$container" 2>&1 | stdbuf -oL -eL awk -v prefix="$prefix" '{print prefix " " $0}'
        else
            docker logs --tail "$TAIL_LINES" "$container" 2>&1 | stdbuf -oL -eL awk -v prefix="$prefix" '{print prefix " " $0}'
        fi
    else
        # Без stdbuf - используем простой подход с awk
        if [ "$FOLLOW_MODE" = true ]; then
            docker logs --tail "$TAIL_LINES" "$container" 2>&1 | awk -v prefix="$prefix" '{print prefix " " $0}'
            docker logs -f --tail 0 "$container" 2>&1 | awk -v prefix="$prefix" '{print prefix " " $0}'
        else
            docker logs --tail "$TAIL_LINES" "$container" 2>&1 | awk -v prefix="$prefix" '{print prefix " " $0}'
        fi
    fi
}

# Функция для фильтрации логов скачивания (без буферизации)
filter_download() {
    if [ "$FILTER_DOWNLOAD" = true ]; then
        # Используем stdbuf для немедленного вывода
        if command -v stdbuf >/dev/null 2>&1; then
            stdbuf -oL -eL grep -E "DOWNLOAD|ASYNC|SYNC|SCHEDULING|📥|🔄|✅.*DOWNLOAD|❌.*DOWNLOAD|sending by URL|downloading|download|Download|ASYNC DOWNLOAD|SCHEDULING async|Convert|webp|PNG|💾|🗑️|Image job.*completed|Confirmed operation"
        else
            grep --line-buffered -E "DOWNLOAD|ASYNC|SYNC|SCHEDULING|📥|🔄|✅.*DOWNLOAD|❌.*DOWNLOAD|sending by URL|downloading|download|Download|ASYNC DOWNLOAD|SCHEDULING async|Convert|webp|PNG|💾|🗑️|Image job.*completed|Confirmed operation"
        fi
    else
        cat
    fi
}

# Запускаем логи для каждого контейнера в фоне
PIDS=()
for container in "${RUNNING[@]}"; do
    if [ "$FILTER_DOWNLOAD" = true ]; then
        log_container "$container" | filter_download &
    else
        log_container "$container" &
    fi
    PIDS+=($!)
done

# Ждем завершения всех процессов (или до Ctrl+C)
# Используем wait с обработкой ошибок
set +e
wait "${PIDS[@]}" 2>/dev/null
set -e
