# Быстрый старт развертывания на VPS reg.ru

## Минимальные шаги для запуска

### 1. Подготовка сервера (один раз)

```bash
# Выполнить скрипт автоматической настройки
chmod +x deploy/scripts/setup.sh
./deploy/scripts/setup.sh

# Перезайти в систему для применения изменений группы docker
exit
```

### 2. Загрузка проекта

```bash
# Создать директорию
sudo mkdir -p /opt/media-lab
sudo chown $USER:$USER /opt/media-lab
cd /opt/media-lab

# Загрузить файлы проекта (через git, scp или другой способ)
# Например, через git:
git clone <your-repo-url> .

# Или через scp с локальной машины:
# scp -r /path/to/Media_lab/* user@your-server:/opt/media-lab/
```

### 3. Настройка конфигурации

```bash
cd /opt/media-lab

# Скопировать пример конфигурации
cp deploy/.env.prod.example .env

# Отредактировать .env файл
nano .env
# Заполнить: tg_bot_token, fal_api_key, app_env=vps

# Создать директории для медиа
mkdir -p media/images media/edits media/face_swap media/videos
```

### 4. Запуск

```bash
cd /opt/media-lab/deploy

# Сделать скрипты исполняемыми
chmod +x scripts/*.sh

# Запустить все сервисы
./scripts/start.sh

# Проверить статус
./scripts/status.sh

# Просмотреть логи
./scripts/logs.sh
```

### 5. Проверка работы

```bash
# Проверить статус контейнеров
docker ps

# Проверить логи бота
docker-compose -f docker-compose.prod.yml logs bot

# Проверить API
curl http://localhost:8000/health

# Протестировать бота в Telegram
```

## Управление

```bash
cd /opt/media-lab/deploy

# Запуск
./scripts/start.sh

# Остановка
./scripts/stop.sh

# Перезапуск
./scripts/restart.sh

# Статус
./scripts/status.sh

# Логи
./scripts/logs.sh [service_name]

# Обновление
./scripts/update.sh

# Резервная копия
./scripts/backup.sh
```

## Решение проблем

### Бот не запускается

```bash
# Проверить логи
./scripts/logs.sh bot

# Проверить переменные окружения
docker-compose -f docker-compose.prod.yml exec bot env | grep TG_BOT_TOKEN
```

### Воркер не обрабатывает задачи

```bash
# Проверить логи воркера
./scripts/logs.sh worker-image

# Проверить Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping
```

### Нехватка места

```bash
# Очистить Docker
docker system prune -a --volumes

# Очистить старые логи
find /opt/media-lab/logs -name "*.log" -mtime +30 -delete
```

## Полезные команды

```bash
# Просмотр использования ресурсов
docker stats

# Просмотр использования диска
docker system df
df -h

# Просмотр логов конкретного сервиса
docker-compose -f docker-compose.prod.yml logs -f bot
docker-compose -f docker-compose.prod.yml logs -f worker-image
docker-compose -f docker-compose.prod.yml logs -f api

# Перезапуск конкретного сервиса
docker-compose -f docker-compose.prod.yml restart bot
docker-compose -f docker-compose.prod.yml restart worker-image
```

