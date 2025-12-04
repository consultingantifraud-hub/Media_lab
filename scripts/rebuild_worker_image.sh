#!/bin/bash
set -e

echo "=== Пересборка образа deploy-worker-image:latest ==="

cd /opt/media-lab/deploy

echo "1. Останавливаем контейнеры worker-image-2 и worker-image-3..."
docker-compose -f docker-compose.prod.yml stop worker-image-2 worker-image-3 || true

echo "2. Пересобираем образ worker-image..."
cd /opt/media-lab
docker build -f docker/Dockerfile.worker -t deploy-worker-image:latest . || {
    echo "Ошибка при сборке образа!"
    exit 1
}

echo "3. Пересоздаем контейнеры worker-image-2 и worker-image-3..."
cd /opt/media-lab/deploy
docker-compose -f docker-compose.prod.yml up -d --force-recreate worker-image-2 worker-image-3

echo "4. Проверяем статус контейнеров..."
sleep 3
docker-compose -f docker-compose.prod.yml ps worker-image-2 worker-image-3

echo "5. Проверяем наличие sqlalchemy в контейнерах..."
echo "worker-image-2:"
docker exec deploy-worker-image-2-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"
echo "worker-image-3:"
docker exec deploy-worker-image-3-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"

echo "=== Готово! ==="







