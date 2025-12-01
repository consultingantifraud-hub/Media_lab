#!/bin/bash
# Автоматическая настройка сервера Media Lab
# Выполните этот скрипт на сервере один раз

set -e

echo "🚀 Автоматическая настройка сервера Media Lab"
echo "=============================================="
echo ""

# Шаг 1: Обновление системы
echo "[1/8] Обновление системы..."
apt update -qq
apt upgrade -y -qq
echo "✅ Система обновлена"
echo ""

# Шаг 2: Установка необходимых пакетов
echo "[2/8] Установка необходимых пакетов..."
apt install -y -qq curl git wget nano htop ufw certbot python3-certbot-nginx unzip > /dev/null 2>&1
echo "✅ Пакеты установлены"
echo ""

# Шаг 3: Установка Docker
echo "[3/8] Проверка Docker..."
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

# Шаг 4: Установка Docker Compose
echo "[4/8] Проверка Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    echo "Установка Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose установлен"
else
    echo "✅ Docker Compose уже установлен: $(docker-compose --version)"
fi
echo ""

# Шаг 5: Настройка firewall
echo "[5/8] Настройка firewall..."
ufw --force enable > /dev/null 2>&1 || true
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1
echo "✅ Firewall настроен"
echo ""

# Шаг 6: Создание директорий
echo "[6/8] Создание директорий..."
mkdir -p /opt/media-lab
mkdir -p /opt/backups/media-lab
mkdir -p /opt/media-lab/media/{images,edits,face_swap,videos}
chmod -R 755 /opt/media-lab
echo "✅ Директории созданы"
echo ""

# Шаг 7: Проверка установки
echo "[7/8] Проверка установки..."
docker --version
docker-compose --version
echo "✅ Все компоненты установлены"
echo ""

# Шаг 8: Готово
echo "[8/8] Настройка завершена!"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Сервер успешно настроен!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Следующий шаг: загрузка файлов проекта на сервер"
echo ""







