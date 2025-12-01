#!/bin/bash
# Скрипт для редактирования .env файла

cd /opt/media-lab

echo "Редактирование .env файла..."
echo ""
echo "Если nano не работает, попробуйте:"
echo "1. Выйти из nano: Ctrl+X"
echo "2. Использовать vi: vi .env"
echo "3. Или отредактировать через команды"
echo ""

# Проверка доступности редакторов
if command -v nano &> /dev/null; then
    nano .env
elif command -v vi &> /dev/null; then
    vi .env
else
    echo "Редакторы не найдены. Используйте команды для редактирования."
fi







