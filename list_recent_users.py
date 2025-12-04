#!/usr/bin/env python3
"""Скрипт для вывода последних пользователей."""

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

from app.db.models import User
from app.services.billing import BillingService

def list_recent_users(limit: int = 10):
    """Вывести последних пользователей."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        users = db.query(User).order_by(User.id.desc()).limit(limit).all()
        
        if not users:
            logger.info("Пользователи не найдены.")
            return
        
        logger.info(f"Последние {len(users)} пользователей:")
        logger.info("-" * 80)
        
        for u in users:
            balance_kopecks = BillingService.get_user_balance(db, u.id)
            balance_rubles = balance_kopecks / 100.0
            username_str = f"@{u.username}" if u.username else "не указан"
            name_str = f"{u.first_name} {u.last_name or ''}".strip() or "не указано"
            
            logger.info(f"ID: {u.id:4d} | Telegram ID: {u.telegram_id:12d} | Username: {username_str:20s} | Имя: {name_str:30s} | Баланс: {balance_rubles:8.2f} ₽")
        
        logger.info("-" * 80)
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
    finally:
        db.close()

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    list_recent_users(limit)





