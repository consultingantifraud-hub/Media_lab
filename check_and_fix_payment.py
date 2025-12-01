#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from app.db.base import SessionLocal
from app.db.models import Payment, PaymentStatus, User, Balance
from app.services.billing import BillingService
from app.services.payment import PaymentService

db = SessionLocal()
try:
    user = db.query(User).filter(User.telegram_id == 444349639).first()
    if not user:
        print('User not found')
        sys.exit(1)
    
    # Find payment for 210₽ (21000 kopecks)
    payment = db.query(Payment).filter(
        Payment.user_id == user.id,
        Payment.yookassa_payment_id == '30bf7bad-000f-5000-b000-144b8eb19a73'
    ).first()
    
    if not payment:
        print('Payment not found')
        sys.exit(1)
    
    print(f'Payment ID: {payment.id}')
    print(f'Amount in DB: {payment.amount} kopecks ({payment.amount / 100.0:.2f}₽)')
    print(f'Status: {payment.status.value}')
    print(f'YooKassa ID: {payment.yookassa_payment_id}')
    
    # Check status from YooKassa
    print('\nChecking status from YooKassa...')
    payment_data = PaymentService.check_payment_status_from_yookassa(db, payment.yookassa_payment_id)
    
    if payment_data:
        print(f'YooKassa status: {payment_data.get("status")}')
        print(f'Paid: {payment_data.get("paid")}')
        
        if payment_data.get("status") == "succeeded" and payment_data.get("paid"):
            # Payment was successful
            print('\n✅ Payment was successful!')
            
            # Check if balance was topped up correctly
            # Original payment amount should be 21000 kopecks (210₽)
            # But due to discount, only 14700 kopecks (147₽) was added
            # Need to add the difference: 21000 - 14700 = 6300 kopecks (63₽)
            
            original_amount = 21000  # 210₽ in kopecks
            current_payment_amount = payment.amount  # Amount stored in DB
            
            if current_payment_amount < original_amount:
                difference = original_amount - current_payment_amount
                print(f'\n⚠️ Balance was topped up with discounted amount: {current_payment_amount} kopecks ({current_payment_amount / 100.0:.2f}₽)')
                print(f'Should be: {original_amount} kopecks ({original_amount / 100.0:.2f}₽)')
                print(f'Difference: {difference} kopecks ({difference / 100.0:.2f}₽)')
                
                # Get current balance
                balance = db.query(Balance).filter(Balance.user_id == user.id).first()
                balance_before = balance.balance if balance else 0
                
                # Add difference to balance
                print(f'\nAdding difference to balance...')
                success = BillingService.add_balance(db, user.id, int(difference / 100.0))
                
                if success:
                    balance_after = BillingService.get_user_balance(db, user.id)
                    print(f'✅ Balance updated successfully!')
                    print(f'Balance before: {balance_before} kopecks ({balance_before / 100.0:.2f}₽)')
                    print(f'Balance after: {balance_after} kopecks ({balance_after / 100.0:.2f}₽)')
                    print(f'Added: {difference} kopecks ({difference / 100.0:.2f}₽)')
                else:
                    print('❌ Failed to add balance')
            else:
                print(f'✅ Balance was already topped up correctly: {current_payment_amount} kopecks ({current_payment_amount / 100.0:.2f}₽)')
        else:
            print(f'\n⏳ Payment status: {payment_data.get("status")}, paid: {payment_data.get("paid")}')
    else:
        print('❌ Failed to check payment status from YooKassa')
        
finally:
    db.close()

