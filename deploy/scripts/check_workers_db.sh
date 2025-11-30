#!/bin/bash
# Скрипт для проверки подключения всех воркеров к базе данных

echo "=========================================="
echo "ПРОВЕРКА ПОДКЛЮЧЕНИЯ ВОРКЕРОВ К БД"
echo "=========================================="
echo ""

WORKERS=(1 2 3 4 5 6 7 8 9 10 11 12 13 14 15)
TOTAL_WORKERS=${#WORKERS[@]}
SUCCESS_COUNT=0
FAIL_COUNT=0

for i in "${WORKERS[@]}"; do
    if [ $i -eq 1 ]; then
        container="deploy-worker-image-1"
    else
        container="deploy-worker-image-$i-1"
    fi
    
    echo "--- Worker $i ($container) ---"
    
    # Проверяем, запущен ли контейнер
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "❌ Контейнер не запущен"
        ((FAIL_COUNT++))
        continue
    fi
    
    # Проверяем DATABASE_URL
    db_url=$(docker exec "$container" env | grep DATABASE_URL | cut -d'=' -f2)
    if [ -z "$db_url" ]; then
        echo "❌ DATABASE_URL не установлен"
        ((FAIL_COUNT++))
        continue
    fi
    
    echo "  DATABASE_URL: $db_url"
    
    # Проверяем наличие файла БД
    db_path=$(echo "$db_url" | sed 's|sqlite:///||')
    if docker exec "$container" test -f "$db_path"; then
        db_size=$(docker exec "$container" stat -c%s "$db_path" 2>/dev/null || echo "0")
        db_size_kb=$((db_size / 1024))
        echo "  ✅ Файл БД существует: $db_path ($db_size_kb KB)"
    else
        echo "  ⚠️  Файл БД не найден: $db_path"
    fi
    
    # Проверяем подключение к БД
    if docker exec "$container" python -c "
from app.db.base import SessionLocal
from app.db.models import Operation
from sqlalchemy import desc
try:
    db = SessionLocal()
    ops = db.query(Operation).order_by(desc(Operation.id)).limit(1).all()
    print('  ✅ Подключение к БД успешно')
    if ops:
        print(f'  Последняя операция: ID={ops[0].id}, Status={ops[0].status}')
    db.close()
except Exception as e:
    print(f'  ❌ Ошибка подключения: {e}')
    exit(1)
" 2>&1 | grep -q "✅"; then
        echo "  ✅ Проверка БД пройдена"
        ((SUCCESS_COUNT++))
    else
        echo "  ❌ Ошибка при проверке БД"
        ((FAIL_COUNT++))
    fi
    echo ""
done

echo "=========================================="
echo "ИТОГИ:"
echo "  Всего воркеров: $TOTAL_WORKERS"
echo "  ✅ Успешно: $SUCCESS_COUNT"
echo "  ❌ Ошибок: $FAIL_COUNT"
echo "=========================================="

if [ $FAIL_COUNT -eq 0 ]; then
    exit 0
else
    exit 1
fi

