#!/usr/bin/env python3
"""Проверка моделей в базе данных"""

import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import SessionLocal
from app.db.models import Operation
from sqlalchemy import func, distinct
from collections import Counter

db = SessionLocal()
try:
    # Получаем все уникальные модели из операций
    print("=" * 60)
    print("Все уникальные модели в операциях:")
    print("=" * 60)
    
    models = db.query(Operation.model).filter(
        Operation.model.isnot(None),
        Operation.model != ""
    ).distinct().all()
    
    model_counts = {}
    for (model,) in models:
        count = db.query(func.count(Operation.id)).filter(Operation.model == model).scalar()
        model_counts[model] = count
    
    # Сортируем по количеству операций
    for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {repr(model):50} {count:5} операций")
    
    # Проверяем конкретно flux-2-flex
    print("\n" + "=" * 60)
    print("Операции с flux-2-flex (разные варианты написания):")
    print("=" * 60)
    
    flux_ops = db.query(Operation.model, func.count(Operation.id)).filter(
        Operation.model.isnot(None),
        Operation.model.ilike('%flux%')
    ).group_by(Operation.model).all()
    
    for model, count in flux_ops:
        print(f"  {repr(model):50} {count:5} операций")
        
    # Тестируем функцию get_model_cost_rub для реальных моделей
    print("\n" + "=" * 60)
    print("Тест get_model_cost_rub для реальных моделей из БД:")
    print("=" * 60)
    
    from scripts.export_statistics_to_excel import get_model_cost_rub
    
    for model, count in flux_ops:
        cost = get_model_cost_rub(model)
        print(f"  {repr(model):50} cost={cost:8.2f} руб. ({count} операций)")
        
finally:
    db.close()

