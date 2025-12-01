#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/media-lab')
from app.db.base import SessionLocal
from app.db.models import Payment, PaymentStatus, User, Balance

db = SessionLocal()
try:
    user = db.query(User).filter(User.telegram_id == 444349639).first()
    if user:
        payments = db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.id.desc()).limit(10).all()
        balance = db.query(Balance).filter(Balance.user_id == user.id).first()
        
        print(f'User ID: {user.id}, Telegram ID: {user.telegram_id}')
        print(f'Current balance: {balance.balance if balance else 0} kopecks ({balance.balance / 100.0 if balance else 0:.2f}₽)')
        print(f'\nPayments:')
        total_added = 0
        for p in payments:
            status_icon = '✅' if p.status == PaymentStatus.SUCCEEDED else '⏳' if p.status == PaymentStatus.PENDING else '❌'
            print(f'  {status_icon} ID: {p.id}, Amount: {p.amount} kopecks ({p.amount / 100.0:.2f}₽), Status: {p.status.value}, YooKassa ID: {p.yookassa_payment_id}')
            if p.status == PaymentStatus.SUCCEEDED:
                total_added += p.amount
        print(f'\nTotal succeeded payments: {total_added} kopecks ({total_added / 100.0:.2f}₽)')
    else:
        print('User not found')
finally:
    db.close()

