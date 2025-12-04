#!/usr/bin/env python3
"""Script to add balance to user account."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.services.billing import BillingService
from loguru import logger


def add_balance(telegram_id: int, amount: int):
    """
    Add balance to user account.
    
    Args:
        telegram_id: Telegram user ID
        amount: Amount to add in rubles
    """
    db = SessionLocal()
    try:
        # Get or create user
        user, created = BillingService.get_or_create_user(db, telegram_id)
        
        if created:
            logger.info(f"Created new user: telegram_id={telegram_id}, user_id={user.id}")
        else:
            logger.info(f"Found existing user: telegram_id={telegram_id}, user_id={user.id}")
        
        # Get current balance
        user_info = BillingService.get_user_info(db, telegram_id)
        old_balance = user_info["balance"] if user_info else 0
        
        # Add balance
        success = BillingService.add_balance(db, user.id, amount)
        
        if success:
            # Get updated balance
            user_info = BillingService.get_user_info(db, telegram_id)
            new_balance = user_info["balance"] if user_info else 0
            
            print("\n" + "="*50)
            print("✅ БАЛАНС УСПЕШНО ПОПОЛНЕН")
            print("="*50)
            print(f"👤 Пользователь: {telegram_id} (ID: {user.id})")
            print(f"💰 Сумма пополнения: {amount} ₽")
            print(f"📊 Старый баланс: {old_balance} ₽")
            print(f"📊 Новый баланс: {new_balance} ₽")
            print("="*50 + "\n")
            
            logger.success(
                f"Balance added successfully: user_id={user.id}, "
                f"amount={amount}₽, old_balance={old_balance}₽, new_balance={new_balance}₽"
            )
            return True
        else:
            print("\n❌ ОШИБКА: Не удалось пополнить баланс\n")
            logger.error("Failed to add balance")
            return False
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
        logger.error(f"Error adding balance: {e}", exc_info=True)
        return False
    finally:
        db.close()


def show_balance(telegram_id: int):
    """Show current user balance."""
    db = SessionLocal()
    try:
        user_info = BillingService.get_user_info(db, telegram_id)
        if user_info:
            print("\n" + "="*50)
            print("📊 ТЕКУЩИЙ БАЛАНС")
            print("="*50)
            print(f"👤 Пользователь: {telegram_id}")
            print(f"💰 Баланс: {user_info['balance']} ₽")
            print(f"🎁 Бесплатных операций: {user_info['free_operations_left']} / {user_info['free_operations_total']}")
            print(f"⭐ Бесплатный доступ: {'Да' if user_info['has_free_access'] else 'Нет'}")
            print("="*50 + "\n")
        else:
            print(f"\n❌ Пользователь {telegram_id} не найден\n")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n" + "="*50)
        print("💳 СКРИПТ ПОПОЛНЕНИЯ БАЛАНСА")
        print("="*50)
        print("\nИспользование:")
        print("  python scripts/add_balance.py <telegram_id> <amount>")
        print("  python scripts/add_balance.py <telegram_id> --show")
        print("\nПримеры:")
        print("  python scripts/add_balance.py 902547985 1000  # Пополнить на 1000 ₽")
        print("  python scripts/add_balance.py 902547985 --show  # Показать баланс")
        print("\n" + "="*50 + "\n")
        sys.exit(1)
    
    try:
        telegram_id = int(sys.argv[1])
        
        if len(sys.argv) == 3 and sys.argv[2] == "--show":
            show_balance(telegram_id)
            sys.exit(0)
        
        if len(sys.argv) < 3:
            print("❌ Ошибка: Укажите сумму для пополнения или --show для просмотра баланса")
            sys.exit(1)
        
        amount = int(sys.argv[2])
        
        if amount <= 0:
            print("❌ Ошибка: Сумма должна быть больше 0")
            sys.exit(1)
        
        success = add_balance(telegram_id, amount)
        sys.exit(0 if success else 1)
        
    except ValueError:
        print("❌ Ошибка: telegram_id и amount должны быть целыми числами")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)








