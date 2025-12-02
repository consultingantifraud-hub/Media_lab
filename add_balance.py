#!/usr/bin/env python3
"""Скрипт для пополнения баланса пользователя."""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://media_lab_user:media_lab_password_change_me@postgres:5432/media_lab"
)

# Import models
from app.db.models import User, Balance
from app.services.billing import BillingService

def add_balance_to_user(telegram_id: int, amount_rubles: float):
    """Пополнить баланс пользователя."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Найти пользователя по telegram_id
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            logger.error(f"Пользователь с telegram_id {telegram_id} не найден.")
            return False
        
        logger.info(f"Найден пользователь: ID={user.id}, Telegram ID={user.telegram_id}, Username={user.username}")
        
        # Получить текущий баланс
        balance_kopecks = BillingService.get_user_balance(db, user.id)
        balance_rubles = balance_kopecks / 100.0
        logger.info(f"Текущий баланс: {balance_kopecks} копеек ({balance_rubles:.2f} ₽)")
        
        # Пополнить баланс
        BillingService.add_balance(db, user.id, amount_rubles)
        db.commit()
        
        # Получить новый баланс
        new_balance_kopecks = BillingService.get_user_balance(db, user.id)
        new_balance_rubles = new_balance_kopecks / 100.0
        logger.info(f"Баланс пополнен на {amount_rubles:.2f} ₽")
        logger.info(f"Новый баланс: {new_balance_kopecks} копеек ({new_balance_rubles:.2f} ₽)")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при пополнении баланса: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        logger.error("Использование: python add_balance.py <telegram_id> <amount_rubles>")
        logger.info("Пример: python add_balance.py 123456789 1000.0")
        sys.exit(1)
    
    try:
        telegram_id = int(sys.argv[1])
        amount_rubles = float(sys.argv[2])
        
        success = add_balance_to_user(telegram_id, amount_rubles)
        if success:
            logger.info("✅ Баланс успешно пополнен!")
            sys.exit(0)
        else:
            logger.error("❌ Не удалось пополнить баланс.")
            sys.exit(1)
            
    except ValueError:
        logger.error("Ошибка: telegram_id должен быть целым числом, amount_rubles - числом.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)

