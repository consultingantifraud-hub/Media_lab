# Команды для выполнения на сервере

Скопируйте и выполните эти команды в терминале сервера, где вы подключены:

## Шаг 1: Обновление системы и установка пакетов

```bash
apt update && apt upgrade -y
apt install -y curl git wget nano htop ufw certbot python3-certbot-nginx unzip
```

## Шаг 2: Установка Docker

```bash
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi
```

## Шаг 3: Установка Docker Compose

```bash
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi
```

## Шаг 4: Настройка firewall

```bash
ufw --force enable
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
```

## Шаг 5: Создание директорий

```bash
mkdir -p /opt/media-lab
mkdir -p /opt/backups/media-lab
mkdir -p /opt/media-lab/media/{images,edits,face_swap,videos}
chmod -R 755 /opt/media-lab
```

## Шаг 6: Проверка установки

```bash
docker --version
docker-compose --version
```

После выполнения этих команд сообщите мне, и я продолжу с загрузкой файлов проекта на сервер.







