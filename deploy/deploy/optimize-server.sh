#!/bin/bash
# Скрипт оптимизации сервера для поддержки 50 пользователей

set -e

echo "=== Оптимизация сервера для поддержки 50 пользователей ==="
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Пожалуйста, запустите скрипт от root${NC}"
    exit 1
fi

cd /opt/media-lab/deploy

echo -e "${YELLOW}1. Резервное копирование текущей конфигурации...${NC}"
cp docker-compose.prod.yml docker-compose.prod.yml.backup.$(date +%Y%m%d_%H%M%S)
echo -e "${GREEN}✓ Резервная копия создана${NC}"
echo ""

echo -e "${YELLOW}2. Применение оптимизированной конфигурации...${NC}"
if [ -f docker-compose.prod.yml.optimized ]; then
    cp docker-compose.prod.yml.optimized docker-compose.prod.yml
    echo -e "${GREEN}✓ Оптимизированная конфигурация применена${NC}"
else
    echo -e "${RED}✗ Файл docker-compose.prod.yml.optimized не найден${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}3. Настройка системных параметров Linux...${NC}"
# Уменьшаем swappiness для уменьшения использования swap
sysctl -w vm.swappiness=10
echo "vm.swappiness=10" >> /etc/sysctl.conf

# Оптимизация параметров памяти
sysctl -w vm.dirty_ratio=15
sysctl -w vm.dirty_background_ratio=5
echo "vm.dirty_ratio=15" >> /etc/sysctl.conf
echo "vm.dirty_background_ratio=5" >> /etc/sysctl.conf

echo -e "${GREEN}✓ Системные параметры настроены${NC}"
echo ""

echo -e "${YELLOW}4. Настройка лимитов для процессов...${NC}"
cat >> /etc/security/limits.conf << EOF
# Media Lab оптимизация
* soft nofile 65535
* hard nofile 65535
* soft nproc 4096
* hard nproc 4096
EOF
echo -e "${GREEN}✓ Лимиты процессов настроены${NC}"
echo ""

echo -e "${YELLOW}5. Перезапуск сервисов с новой конфигурацией...${NC}"
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
echo -e "${GREEN}✓ Сервисы перезапущены${NC}"
echo ""

echo -e "${YELLOW}6. Проверка состояния сервисов...${NC}"
sleep 5
docker-compose -f docker-compose.prod.yml ps
echo ""

echo -e "${YELLOW}7. Проверка использования памяти...${NC}"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
echo ""

echo -e "${GREEN}=== Оптимизация завершена! ==="
echo ""
echo "Ожидаемые улучшения:"
echo "  • Экономия памяти: ~70-90 MB"
echo "  • Память на пользователя: ~15-20 MB (вместо 31 MB)"
echo "  • Поддержка до 50 пользователей при текущей мощности"
echo ""
echo "Мониторинг:"
echo "  docker stats"
echo "  docker-compose -f docker-compose.prod.yml logs -f"
echo ""




