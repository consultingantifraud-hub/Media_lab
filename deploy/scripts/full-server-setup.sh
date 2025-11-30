#!/bin/bash
# Полная автоматическая настройка сервера Media Lab
# Выполните этот скрипт на сервере: bash <(curl -s) или скопируйте и выполните

set -e

echo "🚀 Автоматическая настройка сервера Media Lab"
echo "=============================================="
echo ""

# Обновление системы
echo "[1/10] Обновление системы..."
apt update -qq
apt upgrade -y -qq
echo "✅ Система обновлена"
echo ""

# Установка необходимых пакетов
echo "[2/10] Установка необходимых пакетов..."
apt install -y -qq curl git wget nano htop ufw certbot python3-certbot-nginx unzip > /dev/null 2>&1
echo "✅ Пакеты установлены"
echo ""

# Установка Docker
echo "[3/10] Проверка Docker..."
if ! command -v docker &> /dev/null; then
    echo "Установка Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh > /dev/null 2>&1
    rm get-docker.sh
    echo "✅ Docker установлен"
else
    echo "✅ Docker уже установлен: $(docker --version)"
fi
echo ""

# Установка Docker Compose
echo "[4/10] Проверка Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    echo "Установка Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose установлен"
else
    echo "✅ Docker Compose уже установлен: $(docker-compose --version)"
fi
echo ""

# Настройка firewall
echo "[5/10] Настройка firewall..."
ufw --force enable > /dev/null 2>&1 || true
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1
echo "✅ Firewall настроен"
echo ""

# Создание директорий
echo "[6/10] Создание директорий..."
mkdir -p /opt/media-lab
mkdir -p /opt/backups/media-lab
chmod 755 /opt/media-lab
chmod 755 /opt/backups/media-lab
echo "✅ Директории созданы"
echo ""

# Создание директорий для медиа
echo "[7/10] Создание директорий для медиа..."
mkdir -p /opt/media-lab/media/{images,edits,face_swap,videos}
chmod -R 755 /opt/media-lab/media
echo "✅ Директории для медиа созданы"
echo ""

# Проверка Docker
echo "[8/10] Проверка Docker..."
docker --version
docker-compose --version
echo "✅ Docker готов к работе"
echo ""

# Информация о следующих шагах
echo "[9/10] Настройка завершена!"
echo ""
echo "[10/10] Готово!"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Сервер успешно настроен!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📝 Следующие шаги:"
echo ""
echo "1. Загрузите файлы проекта в /opt/media-lab"
echo "2. Настройте .env файл:"
echo "   cd /opt/media-lab"
echo "   cp deploy/env.prod.example .env"
echo "   nano .env"
echo ""
echo "3. Запустите сервисы:"
echo "   cd /opt/media-lab/deploy"
echo "   chmod +x scripts/*.sh monitoring/*.sh"
echo "   ./scripts/start.sh"
echo ""

