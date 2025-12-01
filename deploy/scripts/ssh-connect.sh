#!/bin/bash
# Скрипт для подключения к SSH серверу
# Использование: ./ssh-connect.sh [server_name]

set -e

SERVER_NAME="${1:-reg-ru-neurostudio}"

echo "🔐 Подключение к SSH серверу..."

# Проверка наличия SSH клиента
if ! command -v ssh &> /dev/null; then
    echo "❌ SSH клиент не найден!"
    echo "Установите OpenSSH: sudo apt install openssh-client"
    exit 1
fi

# Проверка наличия конфигурации SSH
if [ -f ~/.ssh/config ]; then
    if grep -q "^Host ${SERVER_NAME}" ~/.ssh/config; then
        echo "✅ Найдена конфигурация для сервера: ${SERVER_NAME}"
    else
        echo "⚠️  Конфигурация для '${SERVER_NAME}' не найдена в ~/.ssh/config"
        echo "Используется прямое подключение..."
    fi
else
    echo "⚠️  Файл ~/.ssh/config не найден"
    echo "Создайте конфигурацию на основе ssh_config.example"
fi

# Подключение
echo "Подключение к серверу: ${SERVER_NAME}"
ssh "${SERVER_NAME}"

