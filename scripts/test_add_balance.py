"""Script to add test balance to user account."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.services.billing import BillingService
from loguru import logger


def add_test_balance(telegram_id: int, amount: int):
    """
    Add test balance to user account.
    
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
            
            logger.success(
                f"Balance added successfully:\n"
                f"  User: {telegram_id} (ID: {user.id})\n"
                f"  Amount: {amount} ₽\n"
                f"  Old balance: {old_balance} ₽\n"
                f"  New balance: {new_balance} ₽"
            )
            return True
        else:
            logger.error("Failed to add balance")
            return False
            
    except Exception as e:
        logger.error(f"Error adding test balance: {e}", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/test_add_balance.py <telegram_id> <amount>")
        print("Example: python scripts/test_add_balance.py 123456789 500")
        sys.exit(1)
    
    try:
        telegram_id = int(sys.argv[1])
        amount = int(sys.argv[2])
        
        if amount <= 0:
            print("Error: Amount must be greater than 0")
            sys.exit(1)
        
        success = add_test_balance(telegram_id, amount)
        sys.exit(0 if success else 1)
        
    except ValueError:
        print("Error: telegram_id and amount must be integers")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)









