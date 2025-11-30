#!/bin/bash
# Скрипт для просмотра логов всех служб в реальном времени с префиксами

# Получаем список имен контейнеров
CONTAINERS=(
    "deploy-bot-1"
    "deploy-worker-image-1"
    "deploy-worker-image-2-1"
    "deploy-worker-image-3-1"
    "deploy-api-1"
    "deploy-redis-1"
)

# Проверяем, какие контейнеры запущены
RUNNING_CONTAINERS=()
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        RUNNING_CONTAINERS+=("$container")
    fi
done

# Проверяем, найдены ли контейнеры
if [ ${#RUNNING_CONTAINERS[@]} -eq 0 ]; then
    echo "Не найдены запущенные контейнеры. Убедитесь, что сервисы запущены."
    exit 1
fi

echo "Просмотр логов всех служб в реальном времени (Ctrl+C для остановки)..."
echo "Контейнеры: ${RUNNING_CONTAINERS[*]}"
echo ""

# Функция для обработки логов с префиксом
log_with_prefix() {
    local container=$1
    docker logs -f "$container" 2>&1 | while IFS= read -r line; do
        echo "[$container] $line"
    done
}

# Запускаем логи для каждого контейнера в фоновом режиме
PIDS=()
for container in "${RUNNING_CONTAINERS[@]}"; do
    log_with_prefix "$container" &
    PIDS+=($!)
done

# Ждем завершения всех процессов
trap "kill ${PIDS[*]} 2>/dev/null; exit" INT TERM
wait

