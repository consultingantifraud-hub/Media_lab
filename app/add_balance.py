#!/usr/bin/env python3
"""Script to add balance to user account."""
import sys
from app.db.base import SessionLocal
from app.services.billing import BillingService

def add_balance_to_user(telegram_id: int, amount: int) -> None:
    """Add balance to user by telegram_id."""
    db = SessionLocal()
    try:
        # Get user by telegram_id
        from app.db.models import User
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            print(f"❌ User with telegram_id={telegram_id} not found")
            sys.exit(1)
        
        # Add balance
        success = BillingService.add_balance(db, user.id, amount)
        
        if success:
            # Get updated balance
            from app.db.models import Balance
            balance = db.query(Balance).filter(Balance.user_id == user.id).first()
            print(f"✅ Successfully added {amount}₽ to user telegram_id={telegram_id} (user_id={user.id})")
            print(f"💰 New balance: {balance.balance}₽")
        else:
            print(f"❌ Failed to add balance")
            sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_balance.py <telegram_id> <amount>")
        print("Example: python add_balance.py 902547985 1000")
        sys.exit(1)
    
    telegram_id = int(sys.argv[1])
    amount = int(sys.argv[2])
    
    add_balance_to_user(telegram_id, amount)

