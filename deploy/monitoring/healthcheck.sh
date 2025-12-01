#!/bin/bash
# Скрипт проверки здоровья сервисов

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_DIR="$PROJECT_DIR/deploy"

cd "$DEPLOY_DIR"

EXIT_CODE=0

echo "🏥 Проверка здоровья сервисов Media Lab..."
echo ""

# Проверка Redis
echo -n "Redis: "
if docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    EXIT_CODE=1
fi

# Проверка API
echo -n "API: "
if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    EXIT_CODE=1
fi

# Проверка бота
echo -n "Bot: "
if docker-compose -f docker-compose.prod.yml ps bot | grep -q "Up"; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    EXIT_CODE=1
fi

# Проверка воркера
echo -n "Worker: "
if docker-compose -f docker-compose.prod.yml ps worker-image | grep -q "Up"; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    EXIT_CODE=1
fi

# Проверка использования ресурсов
echo ""
echo "📊 Использование ресурсов:"
MEMORY_USAGE=$(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2}')
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}')
echo "  Память: $MEMORY_USAGE"
echo "  Диск: $DISK_USAGE"

# Проверка очереди Redis
echo ""
echo "📋 Очередь задач:"
QUEUE_SIZE=$(docker-compose -f docker-compose.prod.yml exec -T redis redis-cli LLEN rq:queue:img_queue 2>/dev/null || echo "0")
echo "  Задач в очереди: $QUEUE_SIZE"

exit $EXIT_CODE


