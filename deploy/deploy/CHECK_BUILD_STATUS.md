# Проверка статуса сборки Docker

## Быстрые команды для проверки:

```bash
# Проверить процессы сборки
ssh reg-ru-neurostudio "pgrep -f docker-compose"

# Проверить логи сборки
ssh reg-ru-neurostudio "tail -50 /tmp/docker-build.log"

# Проверить собранные образы
ssh reg-ru-neurostudio "docker images"

# Проверить статус контейнеров
ssh reg-ru-neurostudio "cd /opt/media-lab/deploy && docker-compose -f docker-compose.prod.yml ps"
```

## Если сборка зависла:

1. **Остановить сборку:**
```bash
ssh reg-ru-neurostudio "pkill -f 'docker-compose.*build'"
```

2. **Попробовать собрать образы по одному:**
```bash
ssh reg-ru-neurostudio "cd /opt/media-lab/deploy && docker-compose -f docker-compose.prod.yml build bot"
ssh reg-ru-neurostudio "cd /opt/media-lab/deploy && docker-compose -f docker-compose.prod.yml build api"
ssh reg-ru-neurostudio "cd /opt/media-lab/deploy && docker-compose -f docker-compose.prod.yml build worker-image"
```

3. **Или использовать готовые образы без сборки (если возможно)**







