#!/bin/bash
# Скрипт запуска всех сервисов

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_DIR="$PROJECT_DIR/deploy"

cd "$DEPLOY_DIR"

echo "🚀 Запуск сервисов Media Lab..."

# Проверка наличия .env файла
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ Ошибка: файл .env не найден в $PROJECT_DIR"
    echo "Скопируйте deploy/.env.prod.example в .env и заполните необходимые переменные"
    exit 1
fi

# Запуск через docker-compose
docker-compose -f docker-compose.prod.yml up -d

echo "✅ Сервисы запущены"
echo ""
echo "Проверка статуса:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "Просмотр логов:"
echo "  docker-compose -f docker-compose.prod.yml logs -f"

