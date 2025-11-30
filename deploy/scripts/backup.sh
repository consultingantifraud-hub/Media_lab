#!/bin/bash
# Скрипт резервного копирования

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/media-lab}"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "💾 Создание резервной копии Media Lab..."

# Резервная копия медиа файлов
if [ -d "$PROJECT_DIR/media" ]; then
    echo "Копирование медиа файлов..."
    tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" -C "$PROJECT_DIR" media/
fi

# Резервная копия Redis данных (если доступна)
if docker ps | grep -q media-lab-redis; then
    echo "Копирование данных Redis..."
    docker-compose -f "$PROJECT_DIR/deploy/docker-compose.prod.yml" exec -T redis redis-cli SAVE
    docker cp "$(docker-compose -f "$PROJECT_DIR/deploy/docker-compose.prod.yml" ps -q redis):/data/dump.rdb" "$BACKUP_DIR/redis_$DATE.rdb" 2>/dev/null || true
fi

# Резервная копия конфигурации
echo "Копирование конфигурации..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" -C "$PROJECT_DIR" .env deploy/

echo "✅ Резервная копия создана: $BACKUP_DIR"
echo ""
echo "Файлы резервной копии:"
ls -lh "$BACKUP_DIR" | grep "$DATE"

# Удаление старых резервных копий (старше 30 дней)
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.rdb" -mtime +30 -delete

echo ""
echo "Старые резервные копии (старше 30 дней) удалены"

