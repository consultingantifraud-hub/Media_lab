#!/bin/bash
set -e

echo "=== Установка sqlalchemy в образ deploy-worker-image:latest ==="

# Создаем и запускаем временный контейнер из образа
echo "1. Создаем и запускаем временный контейнер..."
CONTAINER_ID=$(docker create deploy-worker-image:latest sleep 3600)
docker start $CONTAINER_ID
sleep 2

# Устанавливаем sqlalchemy в контейнер
echo "2. Устанавливаем sqlalchemy..."
docker exec $CONTAINER_ID pip install --no-cache-dir sqlalchemy>=2.0.0 || {
    echo "Ошибка: не удалось установить sqlalchemy в контейнер"
    docker stop $CONTAINER_ID
    docker rm $CONTAINER_ID
    exit 1
}

# Коммитим изменения в новый образ
echo "3. Сохраняем изменения в образ..."
docker commit $CONTAINER_ID deploy-worker-image:latest

# Останавливаем и удаляем временный контейнер
echo "4. Останавливаем и удаляем временный контейнер..."
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "5. Пересоздаем контейнеры worker-image-2 и worker-image-3..."
cd /opt/media-lab/deploy
docker-compose -f docker-compose.prod.yml up -d --force-recreate worker-image-2 worker-image-3

echo "6. Проверяем наличие sqlalchemy..."
sleep 3
echo "worker-image-2:"
docker exec deploy-worker-image-2-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"
echo "worker-image-3:"
docker exec deploy-worker-image-3-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"

echo "=== Готово! ==="

