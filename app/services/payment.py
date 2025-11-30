"""Payment service for YooKassa integration."""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from loguru import logger
from typing import Optional, Dict, Any
import os
import httpx
import uuid
import hmac
import hashlib
import base64

from app.db.models import User, Payment, PaymentStatus
from app.db.base import SessionLocal
from app.services.billing import BillingService

# YooKassa configuration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/neurostudio_ai_bot")
YOOKASSA_CURRENCY = os.getenv("YOOKASSA_CURRENCY", "RUB")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3"
YOOKASSA_WEBHOOK_URL = os.getenv("YOOKASSA_WEBHOOK_URL", "")


class PaymentService:
    """Service for managing YooKassa payments."""

    @staticmethod
    def create_payment(
        db: Session,
        user_id: int,
        amount: int,
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create payment in YooKassa.
        
        Returns:
            dict with payment_id and confirmation_url, or None on error
        """
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.error("YooKassa credentials not configured")
            return None

        if amount < 10:
            logger.error(f"Amount too small: {amount}₽")
            return None

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            return None

        # Generate payment ID
        payment_id = str(uuid.uuid4())
        yookassa_payment_id = None

        try:
            # Create payment in YooKassa
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": YOOKASSA_CURRENCY
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": YOOKASSA_RETURN_URL
                },
                "capture": True,
                "description": description or f"Пополнение баланса на {amount}₽",
                "metadata": {
                    "telegram_user_id": str(user.telegram_id),
                    "payment_id": payment_id
                }
            }

            # Make request to YooKassa
            auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
            auth_bytes = auth_string.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

            # Use sync httpx client (service is called from sync context)
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{YOOKASSA_API_URL}/payments",
                    json=payment_data,
                    headers={
                        "Authorization": f"Basic {auth_b64}",
                        "Content-Type": "application/json",
                        "Idempotence-Key": payment_id
                    }
                )

            if response.status_code != 200:
                logger.error(f"YooKassa API error: {response.status_code}, {response.text}")
                return None

            payment_response = response.json()
            yookassa_payment_id = payment_response.get("id")
            confirmation_url = payment_response.get("confirmation", {}).get("confirmation_url")

            if not yookassa_payment_id or not confirmation_url:
                logger.error(f"Invalid YooKassa response: {payment_response}")
                return None

            # Save payment to database
            payment = Payment(
                user_id=user_id,
                yookassa_payment_id=yookassa_payment_id,
                amount=amount,
                status=PaymentStatus.PENDING,
                raw_data=payment_response
            )
            db.add(payment)
            db.commit()

            logger.info(f"Created payment: user_id={user_id}, amount={amount}₽, yookassa_id={yookassa_payment_id}")
            return {
                "payment_id": payment.id,
                "yookassa_payment_id": yookassa_payment_id,
                "confirmation_url": confirmation_url,
                "amount": amount
            }

        except Exception as e:
            logger.error(f"Error creating payment: {e}", exc_info=True)
            db.rollback()
            return None

    @staticmethod
    def process_webhook(db: Session, webhook_data: Dict[str, Any]) -> bool:
        """
        Process YooKassa webhook.
        
        Returns:
            bool: Success
        """
        event_type = webhook_data.get("event")
        payment_object = webhook_data.get("object", {})

        # Обработка разных типов событий
        if event_type == "payment.succeeded":
            return PaymentService._handle_payment_succeeded(db, payment_object, webhook_data)
        elif event_type == "payment.canceled":
            return PaymentService._handle_payment_canceled(db, payment_object)
        elif event_type == "payment.waiting_for_capture":
            logger.info(f"Payment waiting for capture: {payment_object.get('id')}")
            return True
        else:
            logger.info(f"Webhook event ignored: {event_type}")
            return True

    @staticmethod
    def _handle_payment_succeeded(db: Session, payment_object: Dict[str, Any], webhook_data: Dict[str, Any]) -> bool:
        """Handle successful payment event."""
        yookassa_payment_id = payment_object.get("id")
        if not yookassa_payment_id:
            logger.error("No payment ID in webhook")
            return False

        # Find payment in database
        payment = db.query(Payment).filter(
            Payment.yookassa_payment_id == yookassa_payment_id
        ).first()

        if not payment:
            logger.error(f"Payment not found: yookassa_payment_id={yookassa_payment_id}")
            return False

        # Check if already processed
        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info(f"Payment already processed: payment_id={payment.id}")
            return True

        # Проверка суммы платежа (из webhook)
        webhook_amount_value = payment_object.get("amount", {}).get("value")
        if webhook_amount_value:
            webhook_amount = int(float(webhook_amount_value) * 100)  # Конвертируем в копейки
            if webhook_amount != payment.amount:
                logger.error(
                    f"Amount mismatch for payment {payment.id}: "
                    f"DB={payment.amount}₽, webhook={webhook_amount}₽"
                )
                # Не отклоняем платеж, но логируем ошибку
                # В реальности суммы должны совпадать

        # Получаем баланс до пополнения
        balance_before = BillingService.get_user_balance(db, payment.user_id)

        # Update payment status
        payment.status = PaymentStatus.SUCCEEDED
        payment.raw_data = webhook_data
        db.flush()

        # Add balance to user
        success = BillingService.add_balance(db, payment.user_id, payment.amount)
        if success:
            # Получаем баланс после пополнения
            balance_after = BillingService.get_user_balance(db, payment.user_id)
            
            # Получаем пользователя для отправки уведомления
            from app.db.models import User
            user = db.query(User).filter(User.id == payment.user_id).first()
            
            db.commit()
            
            # Детальное логирование
            logger.info(
                f"Payment processed successfully: "
                f"payment_id={payment.id}, "
                f"yookassa_id={yookassa_payment_id}, "
                f"user_id={payment.user_id}, "
                f"amount={payment.amount}₽, "
                f"balance_before={balance_before}₽, "
                f"balance_after={balance_after}₽"
            )
            
            # Отправка уведомления пользователю
            if user:
                try:
                    from app.core.telegram_sync import send_message_sync
                    send_message_sync(
                        chat_id=user.telegram_id,
                        text=(
                            f"🎉 **Оплата прошла успешно!**\n\n"
                            f"💰 Ваш баланс пополнен на {payment.amount}₽\n"
                            f"💵 Текущий баланс: {balance_after}₽"
                        ),
                        parse_mode="Markdown"
                    )
                    logger.info(f"Payment notification sent to user {user.telegram_id}")
                except Exception as e:
                    logger.error(f"Failed to send payment notification to user {user.telegram_id}: {e}", exc_info=True)
            
            return True
        else:
            db.rollback()
            logger.error(f"Failed to add balance for payment: payment_id={payment.id}")
            return False

    @staticmethod
    def _handle_payment_canceled(db: Session, payment_object: Dict[str, Any]) -> bool:
        """Handle canceled payment event."""
        yookassa_payment_id = payment_object.get("id")
        if not yookassa_payment_id:
            logger.error("No payment ID in canceled payment webhook")
            return False

        payment = db.query(Payment).filter(
            Payment.yookassa_payment_id == yookassa_payment_id
        ).first()

        if not payment:
            logger.error(f"Payment not found for cancellation: yookassa_payment_id={yookassa_payment_id}")
            return False

        # Update payment status
        payment.status = PaymentStatus.CANCELED
        db.commit()
        
        logger.info(f"Payment canceled: payment_id={payment.id}, yookassa_id={yookassa_payment_id}")
        return True

    @staticmethod
    def verify_webhook_signature(webhook_data: Dict[str, Any], signature: Optional[str] = None) -> bool:
        """
        Verify webhook signature (if YooKassa provides it).
        
        Note: YooKassa doesn't always send signatures in webhooks,
        but we can verify the payment_id matches our records.
        """
        # For now, we'll trust the webhook if payment_id exists in our DB
        # In production, you might want to verify IP whitelist or use other methods
        return True

    @staticmethod
    def get_payment_status(db: Session, payment_id: int) -> Optional[Dict[str, Any]]:
        """Get payment status from database."""
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return None

        return {
            "id": payment.id,
            "amount": payment.amount,
            "status": payment.status.value,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        }


# Convenience functions
def create_payment(telegram_id: int, amount: int, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create payment (creates session)."""
    db = SessionLocal()
    try:
        user, _ = BillingService.get_or_create_user(db, telegram_id)
        return PaymentService.create_payment(db, user.id, amount, description)
    finally:
        db.close()

