#!/bin/bash
# Скрипт остановки всех сервисов

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/.."

cd "$DEPLOY_DIR"

echo "🛑 Остановка сервисов Media Lab..."

docker-compose -f docker-compose.prod.yml down

echo "✅ Сервисы остановлены"


