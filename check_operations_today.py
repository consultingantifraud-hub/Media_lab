#!/usr/bin/env python3
"""Проверка всех операций за сегодня с разными статусами."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import SessionLocal
from app.db.models import Operation, OperationStatus
from datetime import datetime, timezone
from collections import Counter

db = SessionLocal()

# Сегодня: 30.11.2025
today_start = datetime(2025, 11, 30, 0, 0, 0, tzinfo=timezone.utc)
today_end = datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc)

# Все операции за сегодня
all_ops = db.query(Operation).filter(
    Operation.created_at >= today_start,
    Operation.created_at < today_end
).order_by(Operation.created_at.desc()).all()

print(f"\n=== ВСЕ ОПЕРАЦИИ ЗА 30.11.2025 ===\n")
print(f"Всего операций: {len(all_ops)}\n")

# Группировка по статусам
status_counter = Counter(op.status.value for op in all_ops)
print("Статусы операций:")
for status, count in status_counter.most_common():
    print(f"  {status}: {count}")

# Группировка по типам
type_counter = Counter(op.type for op in all_ops)
print("\nТипы операций:")
for op_type, count in type_counter.most_common():
    print(f"  {op_type}: {count}")

# Операции, которые попадут в экспорт (charged или free)
exported_ops = [op for op in all_ops if op.status in [OperationStatus.CHARGED, OperationStatus.FREE]]
print(f"\nОперации для экспорта (charged/free): {len(exported_ops)}")

# Операции, которые НЕ попадут в экспорт
not_exported_ops = [op for op in all_ops if op.status not in [OperationStatus.CHARGED, OperationStatus.FREE]]
if not_exported_ops:
    print(f"\n⚠️ Операции, которые НЕ попали в экспорт ({len(not_exported_ops)}):")
    for op in not_exported_ops:
        print(f"  ID: {op.id}, Тип: {op.type}, Статус: {op.status.value}, Дата: {op.created_at}")

# Детализация всех операций
print("\n=== ДЕТАЛИЗАЦИЯ ВСЕХ ОПЕРАЦИЙ ===\n")
for op in all_ops:
    export_mark = "✅" if op.status in [OperationStatus.CHARGED, OperationStatus.FREE] else "❌"
    print(f"{export_mark} ID: {op.id}, Тип: {op.type}, Статус: {op.status.value}, "
          f"Дата: {op.created_at.strftime('%d.%m.%Y %H:%M:%S') if op.created_at else 'N/A'}, "
          f"Цена: {op.price}, Модель: {op.model or 'N/A'}")

db.close()

