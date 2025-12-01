#!/bin/bash
# Скрипт перезапуска всех сервисов

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/.."

cd "$DEPLOY_DIR"

echo "🔄 Перезапуск сервисов Media Lab..."

docker-compose -f docker-compose.prod.yml restart

echo "✅ Сервисы перезапущены"


