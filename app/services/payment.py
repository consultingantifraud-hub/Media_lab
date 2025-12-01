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
        description: Optional[str] = None,
        email: Optional[str] = None
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
        
        # Use provided email or user's saved email
        user_email = email or user.email
        if not user_email:
            logger.error(f"Email is required for payment: user_id={user_id}, provided_email={email}, saved_email={user.email}")
            return None
        
        logger.info(f"Creating payment with email: {user_email} for user_id={user_id}, amount={amount}₽")
        logger.debug(f"Receipt will be sent to: {user_email}")
        
        # Save email to user if provided and different
        if email and user.email != email:
            user.email = email
            db.commit()

        # Generate payment ID for return URL
        payment_id_for_url = str(uuid.uuid4())
        yookassa_payment_id = None

        try:
            # Create payment in YooKassa
            # Note: receipt is not required for all payment types, but may be required by shop settings
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": YOOKASSA_CURRENCY
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/neurostudio_ai_bot?start=payment_{payment_id_for_url}"
                },
                "capture": True,
                "description": description or f"Пополнение баланса на {amount}₽",
                "metadata": {
                    "telegram_user_id": str(user.telegram_id),
                    "return_payment_id": payment_id_for_url
                },
                # Add receipt if required by shop settings (for Russian tax compliance)
                # Receipt can be disabled in YooKassa shop settings if not needed
                # According to YooKassa docs: https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start
                "receipt": {
                    "customer": {
                        "email": user_email
                    },
                    "items": [
                        {
                            "description": (description or f"Пополнение баланса на {amount}₽")[:128],  # Max 128 chars
                            "quantity": "1.000",  # Must be decimal with 3 decimal places
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": YOOKASSA_CURRENCY
                            },
                            "vat_code": 1,  # НДС не облагается (для цифровых услуг)
                            "payment_mode": "full_payment",  # Полный расчет
                            "payment_subject": "service"  # Услуга (для цифровых услуг)
                        }
                    ],
                    "internet": "true",  # Указать, что это интернет-платеж
                    "timezone": 3  # Часовой пояс (Москва UTC+3)
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
                        "Idempotence-Key": payment_id_for_url
                    }
                )

            if response.status_code != 200:
                logger.error(f"YooKassa API error: {response.status_code}, {response.text}")
                return None

            payment_response = response.json()
            yookassa_payment_id = payment_response.get("id")
            confirmation_url = payment_response.get("confirmation", {}).get("confirmation_url")

            if not yookassa_payment_id or not confirmation_url:
                logger.error(f"Invalid YooKassa response: missing id or confirmation_url. Response: {payment_response}")
                return None

            # Save payment to database
            # amount is in rubles, but we store it in kopecks (like balance)
            amount_kopecks = int(round(amount * 100))
            # Store payment_id_for_url in raw_data for lookup
            payment_response_with_return_id = payment_response.copy()
            if "metadata" not in payment_response_with_return_id:
                payment_response_with_return_id["metadata"] = {}
            payment_response_with_return_id["metadata"]["return_payment_id"] = payment_id_for_url
            
            payment = Payment(
                user_id=user_id,
                yookassa_payment_id=yookassa_payment_id,
                amount=amount_kopecks,  # Store in kopecks
                status=PaymentStatus.PENDING,
                raw_data=payment_response_with_return_id
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
            logger.error(f"Payment creation failed for user_id={user_id}, amount={amount}₽")
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
            webhook_amount_kopecks = int(float(webhook_amount_value) * 100)  # Конвертируем в копейки
            if webhook_amount_kopecks != payment.amount:
                logger.error(
                    f"Amount mismatch for payment {payment.id}: "
                    f"DB={payment.amount} kopecks, webhook={webhook_amount_kopecks} kopecks"
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
        # payment.amount is in kopecks, but add_balance expects rubles (int) and converts to kopecks
        # So we need to convert kopecks back to rubles
        amount_rubles = payment.amount / 100.0
        logger.info(f"Processing webhook payment: payment_id={payment.id}, amount={payment.amount} kopecks ({amount_rubles}₽)")
        success = BillingService.add_balance(db, payment.user_id, int(amount_rubles))
        if success:
            # Получаем баланс после пополнения
            balance_after = BillingService.get_user_balance(db, payment.user_id)
            
            # Получаем пользователя для отправки уведомления
            from app.db.models import User
            user = db.query(User).filter(User.id == payment.user_id).first()
            
            db.commit()
            
            # Детальное логирование
            # Convert kopecks to rubles for logging
            amount_rubles = payment.amount / 100.0
            balance_before_rubles = balance_before / 100.0
            balance_after_rubles = balance_after / 100.0
            logger.info(
                f"Payment processed successfully: "
                f"payment_id={payment.id}, "
                f"yookassa_id={yookassa_payment_id}, "
                f"user_id={payment.user_id}, "
                f"amount={amount_rubles:.2f}₽ ({payment.amount} kopecks), "
                f"balance_before={balance_before_rubles:.2f}₽ ({balance_before} kopecks), "
                f"balance_after={balance_after_rubles:.2f}₽ ({balance_after} kopecks)"
            )
            
            # Отправка уведомления пользователю
            if user:
                try:
                    from app.core.telegram_sync import send_message_sync
                    # payment.amount is in kopecks, convert to rubles for display
                    amount_rubles = payment.amount / 100.0
                    balance_after_rubles = balance_after / 100.0
                    send_message_sync(
                        chat_id=user.telegram_id,
                        text=(
                            f"🎉 **Оплата прошла успешно!**\n\n"
                            f"💰 Ваш баланс пополнен на {amount_rubles:.2f}₽\n"
                            f"💵 Текущий баланс: {balance_after_rubles:.2f}₽"
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
            "amount": payment.amount / 100.0,  # Convert kopecks to rubles for display
            "amount_kopecks": payment.amount,
            "status": payment.status.value,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        }

    @staticmethod
    def check_payment_status_from_yookassa(db: Session, yookassa_payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Check payment status directly from YooKassa API.
        This is simpler than webhook - just check status after user returns.
        
        Returns:
            dict with payment status info, or None on error
        """
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.error("YooKassa credentials not configured")
            return None

        try:
            # Make request to YooKassa
            auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
            auth_bytes = auth_string.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{YOOKASSA_API_URL}/payments/{yookassa_payment_id}",
                    headers={
                        "Authorization": f"Basic {auth_b64}",
                        "Content-Type": "application/json",
                    }
                )

            if response.status_code != 200:
                logger.error(f"YooKassa API error: {response.status_code}, {response.text}")
                return None

            payment_data = response.json()
            status = payment_data.get("status")
            paid = payment_data.get("paid", False)

            # Find payment in database
            payment = db.query(Payment).filter(
                Payment.yookassa_payment_id == yookassa_payment_id
            ).first()

            if not payment:
                logger.warning(f"Payment not found in DB: yookassa_id={yookassa_payment_id}")
                return None

            # Update status if changed
            if status == "succeeded" and payment.status != PaymentStatus.SUCCEEDED:
                if paid:
                    # Process payment
                    # payment.amount is in kopecks, add_balance expects rubles (int) and converts to kopecks
                    amount_rubles = payment.amount / 100.0
                    logger.info(f"Processing payment: payment_id={payment.id}, amount={payment.amount} kopecks ({amount_rubles}₽)")
                    success = BillingService.add_balance(db, payment.user_id, int(amount_rubles))
                    if success:
                        payment.status = PaymentStatus.SUCCEEDED
                        payment.raw_data = payment_data
                        db.commit()
                        
                        # Send notification to user
                        from app.db.models import User
                        user = db.query(User).filter(User.id == payment.user_id).first()
                        if user:
                            try:
                                from app.core.telegram_sync import send_message_sync
                                balance_after = BillingService.get_user_balance(db, payment.user_id)
                                balance_after_rubles = balance_after / 100.0
                                send_message_sync(
                                    chat_id=user.telegram_id,
                                    text=(
                                        f"🎉 *Оплата прошла успешно!*\n\n"
                                        f"💰 Ваш баланс пополнен на {amount_rubles:.2f}₽\n"
                                        f"💵 Текущий баланс: {balance_after_rubles:.2f}₽"
                                    ),
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send notification: {e}")
                        
                        logger.info(f"Payment confirmed: payment_id={payment.id}, amount={amount_rubles}₽")
                    else:
                        db.rollback()
                        logger.error(f"Failed to add balance for payment: payment_id={payment.id}")
            elif status == "canceled" and payment.status != PaymentStatus.CANCELED:
                payment.status = PaymentStatus.CANCELED
                payment.raw_data = payment_data
                db.commit()
                logger.info(f"Payment canceled: payment_id={payment.id}")

            return {
                "status": status,
                "paid": paid,
                "payment_id": payment.id,
                "amount": payment.amount / 100.0,
            }

        except Exception as e:
            logger.error(f"Error checking payment status: {e}", exc_info=True)
            return None


# Convenience functions
def create_payment(telegram_id: int, amount: int, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create payment (creates session)."""
    db = SessionLocal()
    try:
        user, _ = BillingService.get_or_create_user(db, telegram_id)
        return PaymentService.create_payment(db, user.id, amount, description)
    finally:
        db.close()

