#!/usr/bin/env python3
"""Test price conversion logic."""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import Operation
from sqlalchemy import desc

# Same logic as in export_statistics_to_excel.py
KOPECKS_MIGRATION_DATETIME = datetime(2025, 11, 25, 9, 30, 0, tzinfo=timezone.utc)

def convert_price_to_rubles(price: int | None, created_at: datetime | None) -> float:
    if price is None or price == 0:
        return 0.0
    
    if created_at is not None:
        if created_at.tzinfo is None:
            created_at_utc = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at_utc = created_at.astimezone(timezone.utc)
        
        if created_at_utc < KOPECKS_MIGRATION_DATETIME:
            return float(price)
        else:
            return float(price) / 100.0
    
    if price > 100:
        return float(price) / 100.0
    else:
        return float(price)

db = SessionLocal()
try:
    operations = db.query(Operation).filter(
        Operation.status.in_(["charged", "free"])
    ).order_by(desc(Operation.created_at)).limit(30).all()
    
    print("Проверка конвертации цен:")
    print("=" * 100)
    print(f"{'ID':<5} | {'Тип':<15} | {'Цена в БД':<12} | {'Дата':<20} | {'Конвертировано':<15} | {'Ожидаемое':<15}")
    print("-" * 100)
    
    total_revenue_old = 0.0
    total_revenue_new = 0.0
    
    for op in operations:
        price_rubles = convert_price_to_rubles(op.price, op.created_at)
        date_str = op.created_at.strftime("%Y-%m-%d %H:%M") if op.created_at else "None"
        
        # Determine expected value
        if op.created_at:
            if op.created_at.replace(tzinfo=timezone.utc) < KOPECKS_MIGRATION_DATETIME:
                expected = float(op.price)
            else:
                expected = float(op.price) / 100.0
        else:
            expected = price_rubles
        
        status_mark = "✓" if abs(price_rubles - expected) < 0.01 else "✗"
        
        print(f"{op.id:<5} | {op.type:<15} | {op.price:<12} | {date_str:<20} | {price_rubles:<15.2f} | {expected:<15.2f} {status_mark}")
        
        if op.status == "charged":
            if op.created_at and op.created_at.replace(tzinfo=timezone.utc) < KOPECKS_MIGRATION_DATETIME:
                total_revenue_old += price_rubles
            else:
                total_revenue_new += price_rubles
    
    print("-" * 100)
    print(f"Всего выручка (старые операции): {total_revenue_old:.2f} ₽")
    print(f"Всего выручка (новые операции): {total_revenue_new:.2f} ₽")
    print(f"Всего выручка: {total_revenue_old + total_revenue_new:.2f} ₽")
    
    # Check all operations
    all_ops = db.query(Operation).filter(
        Operation.status.in_(["charged", "free"])
    ).all()
    
    total_all = 0.0
    for op in all_ops:
        if op.status == "charged":
            price_rubles = convert_price_to_rubles(op.price, op.created_at)
            total_all += price_rubles
    
    print(f"\nОбщая выручка (все операции): {total_all:.2f} ₽")
    
finally:
    db.close()





