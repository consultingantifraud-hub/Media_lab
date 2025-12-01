#!/bin/bash
# Скрипт для настройки автоматической очистки Docker на сервере

set -e

echo "=== Настройка автоматической очистки Docker ==="
echo ""

# Проверяем права
if [ "$EUID" -ne 0 ]; then 
    echo "ОШИБКА: Скрипт должен запускаться от root"
    exit 1
fi

# Создаем директорию для логов
mkdir -p /opt/media-lab/logs
chmod 755 /opt/media-lab/logs

# Делаем скрипт исполняемым
chmod +x /opt/media-lab/server-cleanup-auto.sh

# Проверяем существующий crontab
CRON_FILE="/tmp/crontab_media_lab"
crontab -l > "$CRON_FILE" 2>/dev/null || touch "$CRON_FILE"

# Проверяем, не добавлена ли уже задача
if grep -q "server-cleanup-auto.sh" "$CRON_FILE"; then
    echo "⚠️  Задача очистки уже существует в crontab"
    echo "Текущий crontab:"
    cat "$CRON_FILE"
    echo ""
    read -p "Заменить существующую задачу? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено"
        rm "$CRON_FILE"
        exit 0
    fi
    # Удаляем старую задачу
    grep -v "server-cleanup-auto.sh" "$CRON_FILE" > "${CRON_FILE}.new" || touch "${CRON_FILE}.new"
    mv "${CRON_FILE}.new" "$CRON_FILE"
fi

# Добавляем новую задачу
echo "" >> "$CRON_FILE"
echo "# Автоматическая очистка Docker каждый день в 02:00 МСК" >> "$CRON_FILE"
echo "TZ=Europe/Moscow" >> "$CRON_FILE"
echo "0 2 * * * /opt/media-lab/server-cleanup-auto.sh >/dev/null 2>&1" >> "$CRON_FILE"

# Устанавливаем новый crontab
crontab "$CRON_FILE"
rm "$CRON_FILE"

echo "✅ Автоматическая очистка настроена!"
echo ""
echo "Расписание:"
echo "  Время: 02:00 МСК (каждый день)"
echo "  Команда: /opt/media-lab/server-cleanup-auto.sh"
echo ""
echo "Текущий crontab:"
crontab -l
echo ""
echo "Логи будут сохраняться в: /opt/media-lab/logs/docker-cleanup.log"
echo ""
echo "Для проверки логов выполните:"
echo "  tail -f /opt/media-lab/logs/docker-cleanup.log"
echo ""
echo "Для тестового запуска выполните:"
echo "  /opt/media-lab/server-cleanup-auto.sh"
echo ""

