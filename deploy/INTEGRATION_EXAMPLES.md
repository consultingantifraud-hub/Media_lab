# Примеры интеграции биллинга

## 📝 Пример 1: Подключение роутеров

### app/bot/main.py

```python
# ... существующий код ...

from app.bot.handlers import billing

# После создания диспетчера
dp = Dispatcher(...)

# Подключить роутер биллинга
dp.include_router(billing.router)

# ... остальной код ...
```

### app/web/api.py

```python
from fastapi import FastAPI
from app.web import billing

app = FastAPI()

# Подключить webhook роутер
app.include_router(billing.router)

# ... остальные роутеры ...
```

## 📝 Пример 2: Добавление кнопки в главное меню

### app/bot/handlers/start.py

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def build_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Создать", callback_data="create"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit"),
        ],
        [
            InlineKeyboardButton(text="🔗 Объединить", callback_data="merge"),
            InlineKeyboardButton(text="📝 Добавить текст", callback_data="add_text"),
        ],
        [
            InlineKeyboardButton(text="🔄 Заменить лицо", callback_data="face_swap"),
            InlineKeyboardButton(text="✨ Ретушь", callback_data="retouch"),
        ],
        [
            InlineKeyboardButton(text="⬆️ Улучшить", callback_data="upscale"),
        ],
        [
            InlineKeyboardButton(text="💰 Оплатить / Баланс", callback_data="payment_menu"),
        ],
    ])
```

## 📝 Пример 3: Интеграция в обработчик генерации

### До интеграции:

```python
@router.message(F.text)
async def handle_generate(message: Message):
    prompt = message.text
    # Создать задачу
    task = queue.enqueue(generate_image_task, prompt=prompt)
    await message.answer("Генерирую...")
```

### После интеграции:

```python
from app.bot.handlers.billing import check_balance_decorator

@router.message(F.text)
@check_balance_decorator("generate")
async def handle_generate(message: Message, operation_id: int):
    prompt = message.text
    # operation_id автоматически передан декоратором
    # Создать задачу с operation_id
    task = queue.enqueue(
        generate_image_task,
        prompt=prompt,
        operation_id=operation_id  # для связи с операцией биллинга
    )
    await message.answer("Генерирую...")
```

## 📝 Пример 4: Обработка ошибок в воркере

### app/workers/image_worker.py

```python
from app.services.billing import BillingService
from app.db.base import SessionLocal
from loguru import logger

def generate_image_task(prompt: str, operation_id: int = None):
    """
    Генерация изображения с обработкой ошибок биллинга.
    
    Args:
        prompt: Текст промпта
        operation_id: ID операции биллинга (для возврата средств при ошибке)
    """
    try:
        # Ваш код генерации через Fal.ai
        result = fal_client.generate(prompt=prompt)
        return result
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        
        # Вернуть средства при ошибке (если операция была платной)
        if operation_id:
            db = SessionLocal()
            try:
                # Проверить, была ли операция платной
                from app.db.models import Operation, OperationStatus
                operation = db.query(Operation).filter(Operation.id == operation_id).first()
                
                if operation and operation.status == OperationStatus.CHARGED:
                    # Вернуть средства
                    BillingService.refund_operation(db, operation_id)
                    logger.info(f"Refunded operation due to error: operation_id={operation_id}")
            finally:
                db.close()
        
        raise  # Пробросить ошибку дальше
```

## 📝 Пример 5: Использование operation_id в задаче

При создании задачи в очереди передавайте `operation_id`:

```python
# В обработчике бота
task_data = {
    "prompt": prompt,
    "user_id": user_id,
    "chat_id": chat_id,
    "operation_id": operation_id,  # Добавить operation_id
    # ... другие данные ...
}

task = queue.enqueue(process_image_task, **task_data)
```

В воркере используйте `operation_id` для связи с операцией биллинга:

```python
def process_image_task(prompt: str, user_id: int, chat_id: int, operation_id: int):
    # Сохранить operation_id в задаче для возможного возврата средств
    # ...
```

## 📝 Пример 6: Проверка баланса без декоратора

Если нужно проверить баланс вручную:

```python
from app.services.billing import BillingService
from app.db.base import SessionLocal

async def check_user_balance(telegram_id: int) -> tuple[bool, str]:
    """
    Проверить баланс пользователя.
    
    Returns:
        (has_balance, error_message)
    """
    db = SessionLocal()
    try:
        user, _ = BillingService.get_or_create_user(db, telegram_id)
        success, error_msg, operation_id = BillingService.charge_operation(
            db, user.id, "generate"
        )
        return success, error_msg, operation_id
    finally:
        db.close()
```

## 📝 Пример 7: Получение информации о балансе

```python
from app.services.billing import get_user_info

async def show_balance_info(telegram_id: int):
    """Показать информацию о балансе."""
    info = get_user_info(telegram_id)
    if info:
        text = (
            f"Баланс: {info['balance']} ₽\n"
            f"Бесплатных операций: {info['free_operations_left']} из {info['free_operations_total']}"
        )
        return text
    return "Ошибка получения информации"
```




