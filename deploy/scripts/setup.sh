#!/bin/bash
# Скрипт первоначальной настройки VPS сервера

set -e

echo "🔧 Настройка VPS сервера для Media Lab..."

# Обновление системы
echo "Обновление системы..."
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
echo "Установка необходимых пакетов..."
sudo apt install -y \
    curl \
    git \
    wget \
    nano \
    htop \
    ufw \
    certbot \
    python3-certbot-nginx

# Установка Docker
if ! command -v docker &> /dev/null; then
    echo "Установка Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker установлен. Необходимо перезайти в систему для применения изменений группы docker"
fi

# Установка Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "Установка Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose установлен"
fi

# Настройка firewall
echo "Настройка firewall..."
sudo ufw --force enable
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
echo "✅ Firewall настроен"

# Создание директорий
echo "Создание директорий..."
sudo mkdir -p /opt/media-lab
sudo mkdir -p /opt/backups/media-lab
sudo chown $USER:$USER /opt/media-lab
sudo chown $USER:$USER /opt/backups/media-lab

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "Следующие шаги:"
echo "1. Перезайдите в систему для применения изменений группы docker"
echo "2. Загрузите проект в /opt/media-lab"
echo "3. Скопируйте deploy/.env.prod.example в .env и заполните переменные"
echo "4. Запустите: cd /opt/media-lab/deploy && ./scripts/start.sh"

