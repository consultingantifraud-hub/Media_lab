#!/usr/bin/env python3
"""Скрипт для пополнения баланса всем пользователям."""

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

def add_balance_to_all_users(amount_rubles: float):
    """Пополнить баланс всем пользователям."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Получить всех пользователей
        users = db.query(User).all()
        
        if not users:
            logger.error("Пользователи не найдены.")
            return 0
        
        logger.info(f"Найдено пользователей: {len(users)}")
        logger.info(f"Сумма пополнения: {amount_rubles:.2f} ₽ на каждого пользователя")
        logger.info("-" * 80)
        
        success_count = 0
        error_count = 0
        
        for user in users:
            try:
                # Получить текущий баланс
                balance_kopecks_before = BillingService.get_user_balance(db, user.id)
                balance_rubles_before = balance_kopecks_before / 100.0
                
                # Пополнить баланс
                BillingService.add_balance(db, user.id, amount_rubles)
                db.commit()
                
                # Получить новый баланс
                balance_kopecks_after = BillingService.get_user_balance(db, user.id)
                balance_rubles_after = balance_kopecks_after / 100.0
                
                username_str = f"@{user.username}" if user.username else "не указан"
                logger.info(
                    f"✅ ID: {user.id:4d} | Telegram: {user.telegram_id:12d} | "
                    f"Username: {username_str:20s} | "
                    f"Баланс: {balance_rubles_before:8.2f} ₽ → {balance_rubles_after:8.2f} ₽"
                )
                success_count += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка при пополнении баланса для пользователя ID={user.id}, Telegram ID={user.telegram_id}: {e}")
                db.rollback()
                error_count += 1
        
        logger.info("-" * 80)
        logger.info(f"Итого:")
        logger.info(f"  ✅ Успешно: {success_count} пользователей")
        logger.info(f"  ❌ Ошибок: {error_count} пользователей")
        logger.info(f"  💰 Общая сумма пополнения: {success_count * amount_rubles:.2f} ₽")
        
        return success_count
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        db.rollback()
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Использование: python add_balance_all_users.py <amount_rubles>")
        logger.info("Пример: python add_balance_all_users.py 1000.0")
        logger.warning("⚠️  ВНИМАНИЕ: Эта операция пополнит баланс ВСЕМ пользователям!")
        sys.exit(1)
    
    try:
        amount_rubles = float(sys.argv[1])
        
        if amount_rubles <= 0:
            logger.error("Сумма должна быть положительным числом.")
            sys.exit(1)
        
        logger.warning("⚠️  ВНИМАНИЕ: Эта операция пополнит баланс ВСЕМ пользователям в базе данных!")
        logger.info(f"Сумма пополнения: {amount_rubles:.2f} ₽ на каждого пользователя")
        
        success_count = add_balance_to_all_users(amount_rubles)
        
        if success_count > 0:
            logger.info("✅ Операция завершена успешно!")
            sys.exit(0)
        else:
            logger.error("❌ Не удалось пополнить баланс ни одному пользователю.")
            sys.exit(1)
            
    except ValueError:
        logger.error("Ошибка: amount_rubles должен быть числом.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)





