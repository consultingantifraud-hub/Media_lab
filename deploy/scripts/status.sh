#!/bin/bash
# Скрипт проверки статуса сервисов

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/.."

cd "$DEPLOY_DIR"

echo "📊 Статус сервисов Media Lab:"
echo ""

docker-compose -f docker-compose.prod.yml ps

echo ""
echo "📈 Использование ресурсов:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

echo ""
echo "💾 Использование дискового пространства Docker:"
docker system df

