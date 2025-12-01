# Развертывание на VPS сервере reg.ru

Инструкция по развертыванию Telegram Media Generator Service на VPS сервере reg.ru.

## 📋 Требования

- VPS сервер с Ubuntu 20.04+ или Debian 11+
- **Минимум:** 2 ГБ RAM, 2 CPU ядра, 20 ГБ SSD
- **Рекомендуется:** 4 ГБ RAM, 2-4 CPU ядра, 50 ГБ SSD (для 10-30 пользователей)
- Docker и Docker Compose установлены
- Открытые порты: 80, 443 (для API, опционально), 6379 (Redis, только локально)

**💡 Рекомендации по выбору сервера:** См. `SERVER_RECOMMENDATIONS.md` или `QUICK_SERVER_CHOICE.md`

**🔐 Настройка SSH подключения:** См. `SSH_SETUP.md` для подробной инструкции по настройке SSH подключения к серверу.

## 🚀 Быстрый старт

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker и Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезайти в систему для применения изменений группы docker
exit
# (войти снова)
```

### 2. Клонирование проекта

```bash
# Создать директорию для проекта
sudo mkdir -p /opt/media-lab
sudo chown $USER:$USER /opt/media-lab
cd /opt/media-lab

# Клонировать репозиторий (или загрузить файлы)
git clone <your-repo-url> .
# или
# Загрузить файлы через scp/sftp
```

### 3. Настройка окружения

```bash
cd /opt/media-lab

# Скопировать пример конфигурации
cp deploy/.env.prod.example .env

# Отредактировать .env файл
nano .env
```

**Важно:** Заполните все необходимые переменные:
- `tg_bot_token` - токен Telegram бота
- `fal_api_key` - API ключ fal.ai
- `app_env=vps` - режим работы
- `redis_url` - URL Redis (по умолчанию `redis://redis:6379/0` для Docker)

### 4. Создание директорий

```bash
# Создать директории для медиа файлов
mkdir -p media/images media/edits media/face_swap media/videos

# Установить права доступа
chmod -R 755 media
```

### 5. Запуск сервисов

```bash
cd /opt/media-lab/deploy

# Использовать production docker-compose
docker-compose -f docker-compose.prod.yml up -d --build

# Проверить статус
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f
```

### 6. Настройка systemd (опционально, для автозапуска)

```bash
# Скопировать service файлы
sudo cp deploy/systemd/*.service /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable media-lab-bot.service
sudo systemctl enable media-lab-worker.service
sudo systemctl enable media-lab-api.service

# Запустить сервисы
sudo systemctl start media-lab-bot.service
sudo systemctl start media-lab-worker.service
sudo systemctl start media-lab-api.service

# Проверить статус
sudo systemctl status media-lab-bot.service
```

## 🔧 Управление сервисами

### Через Docker Compose

```bash
cd /opt/media-lab/deploy

# Запуск
docker-compose -f docker-compose.prod.yml up -d

# Остановка
docker-compose -f docker-compose.prod.yml down

# Перезапуск
docker-compose -f docker-compose.prod.yml restart

# Просмотр логов
docker-compose -f docker-compose.prod.yml logs -f bot
docker-compose -f docker-compose.prod.yml logs -f worker-image
docker-compose -f docker-compose.prod.yml logs -f api

# Обновление после изменений в коде
docker-compose -f docker-compose.prod.yml up -d --build
```

### Через systemd

```bash
# Бот
sudo systemctl start media-lab-bot.service
sudo systemctl stop media-lab-bot.service
sudo systemctl restart media-lab-bot.service
sudo systemctl status media-lab-bot.service

# Воркер
sudo systemctl start media-lab-worker.service
sudo systemctl stop media-lab-worker.service
sudo systemctl restart media-lab-worker.service
sudo systemctl status media-lab-worker.service

# API
sudo systemctl start media-lab-api.service
sudo systemctl stop media-lab-api.service
sudo systemctl restart media-lab-api.service
sudo systemctl status media-lab-api.service
```

### Через скрипты управления

```bash
cd /opt/media-lab/deploy

# Запуск всех сервисов
./scripts/start.sh

# Остановка всех сервисов
./scripts/stop.sh

# Перезапуск всех сервисов
./scripts/restart.sh

# Просмотр статуса
./scripts/status.sh

# Просмотр логов
./scripts/logs.sh
```

## 📊 Мониторинг

### Проверка работоспособности

```bash
# Проверить статус контейнеров
docker ps

# Проверить логи бота
docker-compose -f docker-compose.prod.yml logs --tail=100 bot

# Проверить логи воркера
docker-compose -f docker-compose.prod.yml logs --tail=100 worker-image

# Проверить Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# Проверить API
curl http://localhost:8000/health
```

### Использование ресурсов

```bash
# Использование дискового пространства
df -h

# Использование памяти
free -h

# Использование Docker
docker system df
docker stats
```

## 🔒 Безопасность

### Firewall (UFW)

```bash
# Установить UFW
sudo apt install ufw

# Разрешить SSH
sudo ufw allow 22/tcp

# Разрешить HTTP/HTTPS (если используете nginx)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Включить firewall
sudo ufw enable
sudo ufw status
```

### Обновление системы

```bash
# Регулярно обновлять систему
sudo apt update && sudo apt upgrade -y

# Обновлять Docker образы
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

## 📝 Логи

Логи сохраняются в:
- Docker контейнеры: `docker-compose logs`
- Systemd: `journalctl -u media-lab-*.service`
- Файлы логов: `/opt/media-lab/logs/` (если настроено)

## 🔄 Обновление

```bash
cd /opt/media-lab

# Получить последние изменения
git pull

# Пересобрать и перезапустить
cd deploy
docker-compose -f docker-compose.prod.yml up -d --build

# Или использовать скрипт обновления
./scripts/update.sh
```

## 🐛 Решение проблем

### Бот не запускается

```bash
# Проверить логи
docker-compose -f docker-compose.prod.yml logs bot

# Проверить переменные окружения
docker-compose -f docker-compose.prod.yml exec bot env | grep TG_BOT_TOKEN

# Проверить подключение к Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping
```

### Воркер не обрабатывает задачи

```bash
# Проверить логи воркера
docker-compose -f docker-compose.prod.yml logs worker-image

# Проверить очередь Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli
> KEYS *
> LLEN rq:queue:img_queue
```

### Нехватка места на диске

```bash
# Очистить неиспользуемые Docker ресурсы
docker system prune -a --volumes

# Очистить старые логи
find /opt/media-lab/logs -name "*.log" -mtime +30 -delete

# Очистить старые медиа файлы (осторожно!)
find /opt/media-lab/media -type f -mtime +90 -delete
```

## 📞 Поддержка

При возникновении проблем проверьте:
1. Логи сервисов
2. Статус контейнеров Docker
3. Использование ресурсов сервера
4. Настройки firewall
5. Правильность конфигурации `.env`

