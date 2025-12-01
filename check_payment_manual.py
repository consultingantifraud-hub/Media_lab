#!/usr/bin/env python3
"""Script to check payment status manually."""
import sys
sys.path.insert(0, '/app')

from app.services.payment import PaymentService
from app.db.base import SessionLocal

if __name__ == "__main__":
    payment_id = "30be87d8-000f-5000-b000-1fb3c78815c3"
    db = SessionLocal()
    try:
        print(f"Checking payment: {payment_id}")
        result = PaymentService.check_payment_status_from_yookassa(db, payment_id)
        if result:
            print(f"✅ Status: {result['status']}")
            print(f"✅ Paid: {result['paid']}")
            print(f"✅ Amount: {result.get('amount', 0)}")
            print(f"✅ Payment ID: {result.get('payment_id', 'N/A')}")
        else:
            print("❌ Failed to check payment status")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

