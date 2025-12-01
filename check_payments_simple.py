import sys
sys.path.insert(0, '/app')
from app.db.base import SessionLocal
from app.db.models import Payment, User, Balance

db = SessionLocal()
try:
    user = db.query(User).filter(User.telegram_id == 444349639).first()
    if user:
        payments = db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.id.desc()).all()
        balance = db.query(Balance).filter(Balance.user_id == user.id).first()
        
        print(f'Balance: {balance.balance if balance else 0} kopecks ({balance.balance / 100.0 if balance else 0:.2f}₽)')
        print('\nPayments:')
        total = 0
        for p in payments:
            status_icon = '✅' if p.status.value == 'succeeded' else '⏳' if p.status.value == 'pending' else '❌'
            print(f'{status_icon} ID {p.id}: {p.amount} kopecks ({p.amount / 100.0:.2f}₽), Status: {p.status.value}')
            if p.status.value == 'succeeded':
                total += p.amount
        print(f'\nTotal succeeded: {total} kopecks ({total / 100.0:.2f}₽)')
    else:
        print('User not found')
finally:
    db.close()

