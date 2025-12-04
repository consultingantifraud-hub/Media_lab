#!/bin/bash
set -e

echo "=== Копирование sqlalchemy из worker-image-1 в образ deploy-worker-image:latest ==="

# Создаем и запускаем временный контейнер из образа
echo "1. Создаем и запускаем временный контейнер..."
CONTAINER_ID=$(docker create deploy-worker-image:latest sleep 3600)
docker start $CONTAINER_ID
sleep 2

# Копируем sqlalchemy из worker-image-1
echo "2. Копируем sqlalchemy из worker-image-1..."
docker exec deploy-worker-image-1 tar -czf /tmp/sqlalchemy.tar.gz -C /usr/local/lib/python3.12/site-packages sqlalchemy sqlalchemy-2.0.44.dist-info 2>/dev/null || {
    echo "Ошибка: не удалось создать архив sqlalchemy"
    docker stop $CONTAINER_ID
    docker rm $CONTAINER_ID
    exit 1
}

# Копируем архив в временный контейнер
echo "3. Копируем архив в временный контейнер..."
docker cp deploy-worker-image-1:/tmp/sqlalchemy.tar.gz /tmp/sqlalchemy.tar.gz
docker cp /tmp/sqlalchemy.tar.gz $CONTAINER_ID:/tmp/sqlalchemy.tar.gz

# Распаковываем в контейнере
echo "4. Распаковываем sqlalchemy в контейнере..."
docker exec $CONTAINER_ID tar -xzf /tmp/sqlalchemy.tar.gz -C /usr/local/lib/python3.12/site-packages/ 2>/dev/null || {
    echo "Ошибка: не удалось распаковать sqlalchemy"
    docker stop $CONTAINER_ID
    docker rm $CONTAINER_ID
    exit 1
}

# Проверяем установку
echo "5. Проверяем установку sqlalchemy..."
docker exec $CONTAINER_ID python -c "import sqlalchemy; print('SQLAlchemy version:', sqlalchemy.__version__)" || {
    echo "Ошибка: sqlalchemy не установлен корректно"
    docker stop $CONTAINER_ID
    docker rm $CONTAINER_ID
    exit 1
}

# Коммитим изменения в новый образ
echo "6. Сохраняем изменения в образ..."
docker commit $CONTAINER_ID deploy-worker-image:latest

# Останавливаем и удаляем временный контейнер
echo "7. Останавливаем и удаляем временный контейнер..."
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "8. Пересоздаем контейнеры worker-image-2 и worker-image-3..."
cd /opt/media-lab/deploy
docker-compose -f docker-compose.prod.yml up -d --force-recreate worker-image-2 worker-image-3

echo "9. Проверяем наличие sqlalchemy..."
sleep 3
echo "worker-image-2:"
docker exec deploy-worker-image-2-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"
echo "worker-image-3:"
docker exec deploy-worker-image-3-1 pip list | grep -i sqlalchemy || echo "SQLAlchemy не найден!"

echo "=== Готово! ==="







