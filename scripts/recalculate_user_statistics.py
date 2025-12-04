#!/usr/bin/env python3
"""Recalculate user_statistics.total_spent with correct price conversion."""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import UserStatistics, Operation, OperationStatus

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
    # Get all users with statistics
    all_stats = db.query(UserStatistics).all()
    
    print(f"Пересчет total_spent для {len(all_stats)} пользователей...")
    
    for stats in all_stats:
        # Get all charged/free operations for this user
        operations = db.query(Operation).filter(
            Operation.user_id == stats.user_id,
            Operation.status.in_([OperationStatus.CHARGED, OperationStatus.FREE])
        ).all()
        
        # Recalculate total_spent
        correct_total_spent = 0.0
        for op in operations:
            price_rubles = convert_price_to_rubles(op.price, op.created_at)
            correct_total_spent += price_rubles
        
        old_total_spent = stats.total_spent
        stats.total_spent = correct_total_spent
        
        if abs(old_total_spent - correct_total_spent) > 0.01:
            print(f"User {stats.user_id}: {old_total_spent:.2f} → {correct_total_spent:.2f} ₽")
    
    db.commit()
    print("\n✅ Пересчет завершен!")
    
finally:
    db.close()





