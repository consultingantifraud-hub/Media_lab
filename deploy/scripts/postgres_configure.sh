#!/bin/bash
# Скрипт настройки параметров PostgreSQL через ALTER SYSTEM
# Выполняется один раз для настройки autovacuum

LOG_FILE="/opt/media-lab/logs/postgres-configure.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Настройка параметров PostgreSQL ==="

# Проверяем, что контейнер PostgreSQL запущен
if ! docker ps | grep -q deploy-postgres-1; then
    log "❌ Контейнер PostgreSQL не запущен!"
    exit 1
fi

# Настройка autovacuum параметров
log "Настройка autovacuum параметров..."

docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab <<EOF >> "$LOG_FILE" 2>&1
-- Включаем autovacuum (обычно включен по умолчанию)
ALTER SYSTEM SET autovacuum = on;

-- Интервал между запусками autovacuum (1 минута)
ALTER SYSTEM SET autovacuum_naptime = '1min';

-- Пороговые значения для запуска vacuum
ALTER SYSTEM SET autovacuum_vacuum_threshold = 50;
ALTER SYSTEM SET autovacuum_analyze_threshold = 50;

-- Масштабные факторы (10% мертвых строк для vacuum, 5% для analyze)
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.1;
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.05;

-- Максимальное количество воркеров autovacuum
ALTER SYSTEM SET autovacuum_max_workers = 3;

-- Задержка для снижения нагрузки
ALTER SYSTEM SET autovacuum_vacuum_cost_delay = 20;

-- Перезагружаем конфигурацию
SELECT pg_reload_conf();
EOF

if [ $? -eq 0 ]; then
    log "✅ Параметры PostgreSQL настроены успешно"
    log "⚠️ Для применения некоторых параметров может потребоваться перезапуск PostgreSQL"
else
    log "⚠️ Ошибка при настройке параметров"
fi

log "Текущие настройки autovacuum:"
docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -c "SELECT name, setting, unit FROM pg_settings WHERE name LIKE 'autovacuum%' ORDER BY name;" >> "$LOG_FILE" 2>&1

log "=== Настройка завершена! ==="
log ""

exit 0

