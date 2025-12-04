# Миграции базы данных

## 📋 Миграция 001: Добавление полей для скидок в operations

**Дата:** 2025-11-24  
**Описание:** Добавление полей `original_price` и `discount_percent` в таблицу `operations` для отслеживания скидок.

### Изменения:

- `original_price` (Integer, NULL) - Исходная цена до скидки
- `discount_percent` (Integer, NULL) - Процент скидки (10, 20, 30, etc.)

### Применение миграции:

#### Вариант 1: Через Python скрипт (рекомендуется)

```bash
# Локально
python app/db/migrations/apply_migration.py

# На сервере
docker-compose -f deploy/docker-compose.prod.yml exec api python app/db/migrations/apply_migration.py
```

#### Вариант 2: Через SQL напрямую

**Для SQLite:**
```bash
sqlite3 media_lab.db << EOF
ALTER TABLE operations ADD COLUMN original_price INTEGER NULL;
ALTER TABLE operations ADD COLUMN discount_percent INTEGER NULL;
EOF
```

**Для PostgreSQL:**
```sql
ALTER TABLE operations ADD COLUMN IF NOT EXISTS original_price INTEGER NULL;
ALTER TABLE operations ADD COLUMN IF NOT EXISTS discount_percent INTEGER NULL;
```

#### Вариант 3: Через Python REPL

```python
from app.db.base import engine, SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text("ALTER TABLE operations ADD COLUMN original_price INTEGER NULL"))
    db.execute(text("ALTER TABLE operations ADD COLUMN discount_percent INTEGER NULL"))
    db.commit()
    print("Migration applied successfully")
finally:
    db.close()
```

### Проверка миграции:

```python
from app.db.base import engine
from sqlalchemy import inspect

inspector = inspect(engine)
columns = [col["name"] for col in inspector.get_columns("operations")]

if "original_price" in columns and "discount_percent" in columns:
    print("✅ Migration applied successfully")
else:
    print("❌ Migration not applied")
```

---

## ⚠️ Важно

1. **Резервное копирование:** Перед применением миграции сделайте резервную копию БД
2. **Тестирование:** Протестируйте миграцию на тестовой БД
3. **Откат:** Если нужно откатить миграцию:
   ```sql
   -- SQLite не поддерживает DROP COLUMN напрямую
   -- Нужно пересоздать таблицу или использовать другой подход
   
   -- PostgreSQL:
   ALTER TABLE operations DROP COLUMN original_price;
   ALTER TABLE operations DROP COLUMN discount_percent;
   ```

---

**Дата:** 2025-11-24









