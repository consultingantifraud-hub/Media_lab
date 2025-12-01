# Инструкция по сборке Docker образов локально

## Шаг 1: Проверка Docker
```powershell
docker ps
```
Если Docker работает, увидите список контейнеров.

## Шаг 2: Сборка образов

Выполните команды по очереди в PowerShell (в директории `C:\MAIN\Bots\Media_lab`):

### Образ бота:
```powershell
docker build -f docker/Dockerfile.bot -t deploy-bot:latest .
docker save deploy-bot:latest -o bot.tar
```

### Образ API:
```powershell
docker build -f docker/Dockerfile.api -t deploy-api:latest .
docker save deploy-api:latest -o api.tar
```

### Образ Worker:
```powershell
docker build -f docker/Dockerfile.worker -t deploy-worker-image:latest .
docker save deploy-worker-image:latest -o worker-image.tar
```

## Шаг 3: Загрузка на сервер

```powershell
scp bot.tar reg-ru-neurostudio:/tmp/
scp api.tar reg-ru-neurostudio:/tmp/
scp worker-image.tar reg-ru-neurostudio:/tmp/
```

## Шаг 4: Импорт образов на сервере

```powershell
ssh reg-ru-neurostudio "docker load -i /tmp/bot.tar && docker tag deploy-bot:latest deploy-bot:latest && rm /tmp/bot.tar"
ssh reg-ru-neurostudio "docker load -i /tmp/api.tar && docker tag deploy-api:latest deploy-api:latest && rm /tmp/api.tar"
ssh reg-ru-neurostudio "docker load -i /tmp/worker-image.tar && docker tag deploy-worker-image:latest deploy-worker-image:latest && rm /tmp/worker-image.tar"
```

## Шаг 5: Запуск сервисов

```powershell
ssh reg-ru-neurostudio "cd /opt/media-lab/deploy && ./scripts/start.sh"
```

---

**Примечание:** Сборка каждого образа может занять 5-15 минут в зависимости от скорости интернета и мощности ПК.






