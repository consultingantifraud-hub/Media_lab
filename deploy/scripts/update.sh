#!/bin/bash
# Скрипт обновления проекта

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_DIR="$PROJECT_DIR/deploy"

cd "$PROJECT_DIR"

echo "🔄 Обновление проекта Media Lab..."

# Если используется git
if [ -d ".git" ]; then
    echo "Получение последних изменений из git..."
    git pull
fi

cd "$DEPLOY_DIR"

echo "Пересборка и перезапуск контейнеров..."
docker-compose -f docker-compose.prod.yml up -d --build

echo "✅ Обновление завершено"

echo ""
echo "Проверка статуса:"
docker-compose -f docker-compose.prod.yml ps

