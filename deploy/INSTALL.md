# Инструкция по установке на VPS reg.ru

## Шаг 1: Подготовка сервера

Подключитесь к вашему VPS серверу reg.ru по SSH и выполните:

```bash
# Запустить скрипт автоматической настройки
cd /opt
sudo mkdir -p media-lab
sudo chown $USER:$USER media-lab
cd media-lab

# Загрузить файлы проекта (через git, scp или другой способ)
# После загрузки:
cd deploy
chmod +x scripts/*.sh
chmod +x monitoring/*.sh

# Запустить скрипт настройки
./scripts/setup.sh
```

**Важно:** После выполнения скрипта настройки необходимо перезайти в систему для применения изменений группы docker.

## Шаг 2: Конфигурация

```bash
cd /opt/media-lab

# Скопировать пример конфигурации
cp deploy/env.prod.example .env

# Отредактировать .env файл
nano .env
```

Заполните обязательные переменные:
- `tg_bot_token` - токен вашего Telegram бота (получить у @BotFather)
- `fal_api_key` - API ключ fal.ai (получить на https://fal.ai/dashboard/keys)
- `app_env=vps` - режим работы (должен быть "vps")

## Шаг 3: Создание директорий

```bash
cd /opt/media-lab

# Создать директории для медиа файлов
mkdir -p media/images media/edits media/face_swap media/videos

# Установить права доступа
chmod -R 755 media
```

## Шаг 4: Запуск

```bash
cd /opt/media-lab/deploy

# Запустить все сервисы
./scripts/start.sh

# Проверить статус
./scripts/status.sh

# Просмотреть логи
./scripts/logs.sh
```

## Шаг 5: Проверка работы

1. Проверьте статус контейнеров:
   ```bash
   docker ps
   ```

2. Проверьте логи бота:
   ```bash
   ./scripts/logs.sh bot
   ```

3. Протестируйте бота в Telegram - отправьте команду `/start`

4. Проверьте API:
   ```bash
   curl http://localhost:8000/health
   ```

## Настройка автозапуска (рекомендуется)

```bash
# Скопировать systemd service файлы
sudo cp deploy/systemd/*.service /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable media-lab-bot.service
sudo systemctl enable media-lab-worker.service
sudo systemctl enable media-lab-api.service
sudo systemctl enable media-lab-redis.service

# Запустить сервисы
sudo systemctl start media-lab-bot.service
sudo systemctl start media-lab-worker.service
sudo systemctl start media-lab-api.service
sudo systemctl start media-lab-redis.service
```

## Настройка Nginx (опционально)

Если вы хотите сделать API доступным через домен:

```bash
# Установить Nginx
sudo apt install nginx

# Скопировать конфигурацию
sudo cp deploy/nginx/media-lab.conf /etc/nginx/sites-available/media-lab

# Отредактировать конфигурацию (заменить your-domain.com на ваш домен)
sudo nano /etc/nginx/sites-available/media-lab

# Включить сайт
sudo ln -s /etc/nginx/sites-available/media-lab /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Настроить SSL (Let's Encrypt)
sudo certbot --nginx -d your-domain.com
```

## Управление сервисами

Все скрипты управления находятся в `deploy/scripts/`:

- `start.sh` - запуск всех сервисов
- `stop.sh` - остановка всех сервисов
- `restart.sh` - перезапуск всех сервисов
- `status.sh` - проверка статуса
- `logs.sh [service]` - просмотр логов
- `update.sh` - обновление проекта
- `backup.sh` - создание резервной копии

## Мониторинг

Скрипты мониторинга находятся в `deploy/monitoring/`:

- `healthcheck.sh` - проверка здоровья сервисов
- `cleanup.sh` - очистка старых данных и логов

Можно настроить cron для автоматического выполнения:

```bash
# Добавить в crontab
crontab -e

# Проверка здоровья каждый час
0 * * * * /opt/media-lab/deploy/monitoring/healthcheck.sh

# Очистка раз в неделю (воскресенье в 3:00)
0 3 * * 0 /opt/media-lab/deploy/monitoring/cleanup.sh

# Резервная копия каждый день в 2:00
0 2 * * * /opt/media-lab/deploy/scripts/backup.sh
```

## Решение проблем

См. раздел "Решение проблем" в `deploy/README.md`


