#!/bin/bash
# Скрипт для просмотра логов бота и воркеров в реальном времени с префиксами

CONTAINERS=(
    "deploy-bot-1"
    "deploy-worker-image-1"
    "deploy-worker-image-2-1"
    "deploy-worker-image-3-1"
)

# Проверяем запущенные контейнеры
RUNNING=()
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        RUNNING+=("$container")
    fi
done

if [ ${#RUNNING[@]} -eq 0 ]; then
    echo "Не найдены запущенные контейнеры бота и воркеров"
    exit 1
fi

echo "Просмотр логов бота и воркеров в реальном времени (Ctrl+C для остановки)"
echo "Контейнеры: ${RUNNING[*]}"
echo ""

# Запускаем логи для каждого контейнера с префиксом
for container in "${RUNNING[@]}"; do
    docker logs -f "$container" 2>&1 | sed "s/^/[$container] /" &
done

# Ждем завершения всех процессов
trap "kill $(jobs -p) 2>/dev/null; exit" INT TERM
wait

