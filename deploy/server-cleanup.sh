#!/bin/bash
# Скрипт для очистки Docker на сервере
# Безопасно для работающих контейнеров

echo "=== Очистка Docker на сервере ==="
echo ""

# Показываем текущее состояние
echo "Текущее использование Docker:"
docker system df
echo ""

# 1. Удаление неиспользуемых образов (dangling images)
echo "1. Удаление неиспользуемых образов..."
docker image prune -f
echo ""

# 2. Удаление неиспользуемых build cache
echo "2. Очистка Build Cache..."
docker builder prune -f
echo ""

# 3. Удаление остановленных контейнеров
echo "3. Удаление остановленных контейнеров..."
docker container prune -f
echo ""

# 4. Удаление неиспользуемых volumes
echo "4. Удаление неиспользуемых volumes..."
docker volume prune -f
echo ""

# Показываем результат
echo "Результат после очистки:"
docker system df
echo ""

echo "=== Очистка завершена! ==="
echo "Работающие контейнеры не затронуты."




