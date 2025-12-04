#!/bin/bash
# Скрипт для исправления текста Info на сервере

FILE="/opt/media-lab/app/bot/handlers/start.py"

# Исправляем опечатку
sed -i 's/нажммите/нажмите/g' "$FILE"
sed -i 's/нажмитее/нажмите/g' "$FILE"

# Проверяем результат
if grep -q "нажмите кнопку" "$FILE"; then
    echo "✅ Текст исправлен успешно"
    grep "Важно:" "$FILE"
else
    echo "❌ Ошибка исправления"
fi

# Перезапускаем бота
cd /opt/media-lab && docker-compose -f deploy/docker-compose.prod.yml restart bot


