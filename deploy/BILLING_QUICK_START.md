# Быстрый старт: Система биллинга

## 🚀 За 5 минут до запуска

### 1. Установить зависимости

```bash
pip install sqlalchemy alembic
# или если используете PostgreSQL:
pip install sqlalchemy alembic psycopg2-binary
```

### 2. Обновить .env

Добавьте в `.env`:

```bash
# Billing
PRICE_PER_OPERATION=10
FREE_OPERATIONS_COUNT=4

# Database (SQLite для начала)
DATABASE_URL=sqlite:///./media_lab.db

# YooKassa (получите в личном кабинете)
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_RETURN_URL=https://t.me/your_bot
YOOKASSA_CURRENCY=RUB
YOOKASSA_WEBHOOK_URL=https://your-domain.com/yookassa/webhook
```

### 3. Применить миграции

```bash
cd /opt/media-lab
alembic upgrade head
```

### 4. Подключить роутеры

**app/bot/main.py:**
```python
from app.bot.handlers import billing
# ...
router.include_router(billing.router)
```

**app/web/api.py:**
```python
from app.web import billing
# ...
app.include_router(billing.router)
```

### 5. Добавить декоратор в платные обработчики

Пример:
```python
from app.bot.handlers.billing import check_balance_decorator

@router.message(...)
@check_balance_decorator("generate")  # или "edit", "merge", и т.д.
async def handle_generate(message: Message, operation_id: int):
    # ваш код
```

### 6. Перезапустить

```bash
sudo systemctl restart media-lab-bot
sudo systemctl restart media-lab-api
```

## ✅ Готово!

Теперь бот работает с биллингом. Подробности в `BILLING_DEPLOYMENT.md`.




