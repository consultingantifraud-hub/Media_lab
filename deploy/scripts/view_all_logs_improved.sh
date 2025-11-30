#!/bin/bash
# Улучшенная версия с префиксами для каждого контейнера и фильтрацией логов скачивания
# Использует docker logs с параллельным выводом в реальном времени
# Оптимизирован для работы через SSH без обрывов

# Список возможных контейнеров
CONTAINERS=(
    "deploy-bot-1"
    "docker-worker-image-1"
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
    "deploy-api-1"
    "deploy-redis-1"
)

# Автоматически определяем запущенные контейнеры
RUNNING=()
# Сначала добавляем известные контейнеры
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        RUNNING+=("$container")
    fi
done

# Также ищем все контейнеры с именами, содержащими worker, bot, api, redis
ALL_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -E '(bot|worker|api|redis)' || true)
while IFS= read -r container; do
    if [[ -n "$container" ]] && [[ ! " ${RUNNING[@]} " =~ " ${container} " ]]; then
        RUNNING+=("$container")
    fi
done <<< "$ALL_CONTAINERS"

if [ ${#RUNNING[@]} -eq 0 ]; then
    echo "Не найдены запущенные контейнеры"
    exit 1
fi

# Парсим аргументы
FILTER_DOWNLOAD=false
FILTER_WORKER=false
WORKER_ONLY=false
TAIL_LINES=50
FOLLOW_MODE=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --download|-d)
            FILTER_DOWNLOAD=true
            shift
            ;;
        --worker|-w)
            FILTER_WORKER=true
            shift
            ;;
        --worker-only|-wo)
            WORKER_ONLY=true
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
        --help|-h)
            echo "Использование: $0 [OPTIONS]"
            echo ""
            echo "Опции:"
            echo "  --download, -d          Показывать только логи скачивания"
            echo "  --worker, -w            Показывать только логи воркера (фильтр)"
            echo "  --worker-only, -wo      Показывать только воркер (без других контейнеров)"
            echo "  --tail N, -t N          Показать последние N строк перед follow (по умолчанию: 50)"
            echo "  --no-follow, -n         Не следовать за логами (только показать последние строки)"
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

# Фильтруем контейнеры, если указан --worker-only
if [ "$WORKER_ONLY" = true ]; then
    WORKER_CONTAINERS=()
    for container in "${RUNNING[@]}"; do
        if echo "$container" | grep -qE "(worker|Worker)"; then
            WORKER_CONTAINERS+=("$container")
        fi
    done
    if [ ${#WORKER_CONTAINERS[@]} -eq 0 ]; then
        echo "Не найдены контейнеры воркеров"
        exit 1
    fi
    RUNNING=("${WORKER_CONTAINERS[@]}")
fi

# Проверяем аргументы для фильтрации
if [ "$FILTER_DOWNLOAD" = true ]; then
    echo "📥 Режим мониторинга скачивания включен"
fi

if [ "$FILTER_WORKER" = true ]; then
    echo "🔧 Режим мониторинга воркера включен (фильтр по ключевым словам)"
fi

if [ "$WORKER_ONLY" = true ]; then
    echo "🔧 Показываем только воркеры: ${RUNNING[*]}"
else
    echo "Просмотр логов: ${RUNNING[*]}"
fi

if [ "$FILTER_DOWNLOAD" = true ]; then
    echo "Фильтр: только логи скачивания (DOWNLOAD, ASYNC, SYNC, SCHEDULING)"
fi

if [ "$FILTER_WORKER" = true ]; then
    echo "Фильтр: только логи воркера (POLLING, Image job, process_image_job, operation_id, Confirmed operation)"
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

# Функция для фильтрации логов воркера (без буферизации)
filter_worker() {
    if [ "$FILTER_WORKER" = true ]; then
        # Используем stdbuf для немедленного вывода
        if command -v stdbuf >/dev/null 2>&1; then
            stdbuf -oL -eL grep -E "POLLING|📡|Image job|process_image_job|process_smart_merge|process_face_swap|process_image_edit|operation_id|Confirmed operation|Reserved operation|reserve_operation|confirm_operation|Job OK|Job Failed|Worker|Listening on|Subscribing to|img_queue|vid_queue|ERROR|Exception|Traceback|WARNING|SUCCESS"
        else
            grep --line-buffered -E "POLLING|📡|Image job|process_image_job|process_smart_merge|process_face_swap|process_image_edit|operation_id|Confirmed operation|Reserved operation|reserve_operation|confirm_operation|Job OK|Job Failed|Worker|Listening on|Subscribing to|img_queue|vid_queue|ERROR|Exception|Traceback|WARNING|SUCCESS"
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
    elif [ "$FILTER_WORKER" = true ]; then
        log_container "$container" | filter_worker &
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
