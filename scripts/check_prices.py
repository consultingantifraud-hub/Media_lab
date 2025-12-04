#!/usr/bin/env python3
"""Check actual price values in database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import Operation
from sqlalchemy import func, desc
from datetime import datetime

db = SessionLocal()
try:
    # Get sample operations
    operations = db.query(
        Operation.id,
        Operation.type,
        Operation.price,
        Operation.status,
        Operation.created_at
    ).order_by(desc(Operation.created_at)).limit(20).all()
    
    print("Последние 20 операций:")
    print("ID | Тип | Цена | Статус | Дата")
    print("-" * 80)
    for op in operations:
        date_str = op.created_at.strftime("%Y-%m-%d %H:%M") if op.created_at else "None"
        print(f"{op.id} | {op.type} | {op.price} | {op.status} | {date_str}")
    
    # Check price distribution
    print("\n\nРаспределение цен:")
    price_dist = db.query(
        Operation.price,
        func.count(Operation.id).label('count')
    ).filter(
        Operation.status == "charged"
    ).group_by(Operation.price).order_by(Operation.price).all()
    
    print("Цена | Количество операций")
    print("-" * 40)
    for price, count in price_dist:
        print(f"{price} | {count}")
    
    # Check min/max prices
    min_price = db.query(func.min(Operation.price)).filter(Operation.status == "charged").scalar()
    max_price = db.query(func.max(Operation.price)).filter(Operation.status == "charged").scalar()
    avg_price = db.query(func.avg(Operation.price)).filter(Operation.status == "charged").scalar()
    
    print(f"\n\nМинимальная цена: {min_price}")
    print(f"Максимальная цена: {max_price}")
    print(f"Средняя цена: {avg_price:.2f}")
    
finally:
    db.close()





