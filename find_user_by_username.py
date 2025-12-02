#!/usr/bin/env python3
"""Скрипт для поиска пользователя по username."""

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

from app.db.models import User, Balance
from app.services.billing import BillingService

def find_user_by_username(username: str):
    """Найти пользователя по username."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Найти пользователя по username (без @)
        username_clean = username.lstrip("@")
        user = db.query(User).filter(User.username == username_clean).first()
        
        if not user:
            logger.error(f"Пользователь с username '{username}' не найден.")
            return None
        
        balance_kopecks = BillingService.get_user_balance(db, user.id)
        balance_rubles = balance_kopecks / 100.0
        
        logger.info(f"✅ Найден пользователь:")
        logger.info(f"   ID: {user.id}")
        logger.info(f"   Telegram ID: {user.telegram_id}")
        logger.info(f"   Username: @{user.username}" if user.username else "   Username: не указан")
        logger.info(f"   Имя: {user.first_name} {user.last_name or ''}".strip())
        logger.info(f"   Текущий баланс: {balance_rubles:.2f} ₽")
        
        return user.telegram_id
        
    except Exception as e:
        logger.error(f"Ошибка при поиске пользователя: {e}", exc_info=True)
        return None
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Использование: python find_user_by_username.py <username>")
        logger.info("Пример: python find_user_by_username.py dmitry_kolesnik")
        sys.exit(1)
    
    username = sys.argv[1]
    telegram_id = find_user_by_username(username)
    
    if telegram_id:
        logger.info(f"\nДля пополнения баланса используйте:")
        logger.info(f"python add_balance.py {telegram_id} 1000.0")
        sys.exit(0)
    else:
        sys.exit(1)

