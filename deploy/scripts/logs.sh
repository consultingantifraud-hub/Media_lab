#!/bin/bash
# Скрипт просмотра логов

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/.."

cd "$DEPLOY_DIR"

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "📋 Логи всех сервисов (последние 100 строк):"
    echo ""
    docker-compose -f docker-compose.prod.yml logs --tail=100
else
    echo "📋 Логи сервиса: $SERVICE"
    echo ""
    docker-compose -f docker-compose.prod.yml logs --tail=100 -f "$SERVICE"
fi


