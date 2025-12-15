"""Payment service for YooKassa integration."""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from loguru import logger
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import os
import httpx
import uuid
import hmac
import hashlib
import base64
import time

from app.db.models import User, Payment, PaymentStatus, Balance
from app.db.base import SessionLocal
from app.services.billing import BillingService

# YooKassa configuration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/neurostudio_ai_bot")
YOOKASSA_CURRENCY = os.getenv("YOOKASSA_CURRENCY", "RUB")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3"
YOOKASSA_WEBHOOK_URL = os.getenv("YOOKASSA_WEBHOOK_URL", "")
PAYMENT_RECONCILE_BATCH_SIZE = int(os.getenv("PAYMENT_RECONCILE_BATCH_SIZE", "50"))
PAYMENT_RECONCILE_GRACE_SECONDS = int(os.getenv("PAYMENT_RECONCILE_GRACE_SECONDS", "20"))
PAYMENT_RECONCILE_MAX_AGE_SECONDS = int(os.getenv("PAYMENT_RECONCILE_MAX_AGE_SECONDS", str(12 * 3600)))
PAYMENT_STALE_RECHECK_SECONDS = int(os.getenv("PAYMENT_STALE_RECHECK_SECONDS", str(24 * 3600)))
PAYMENT_RECONCILE_INTERVAL_SECONDS = int(os.getenv("PAYMENT_RECONCILE_INTERVAL_SECONDS", "20"))


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
            # Увеличиваем timeout для SSL handshake и добавляем retry логику
            # SSL handshake может занимать больше времени при проблемах с сетью
            timeout_config = httpx.Timeout(
                connect=60.0,  # Timeout for establishing connection (including SSL handshake) - увеличено до 60 сек
                read=60.0,     # Timeout for reading response - увеличено до 60 сек
                write=30.0,    # Timeout for writing request
                pool=30.0      # Timeout for getting connection from pool
            )
            
            # Retry логика для надежности
            max_retries = 3
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    with httpx.Client(timeout=timeout_config) as client:
                        response = client.post(
                            f"{YOOKASSA_API_URL}/payments",
                            json=payment_data,
                            headers={
                                "Authorization": f"Basic {auth_b64}",
                                "Content-Type": "application/json",
                                "Idempotence-Key": payment_id_for_url
                            }
                        )
                    # Если запрос успешен, выходим из цикла retry
                    break
                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, OSError) as e:
                    # OSError может включать SSL handshake errors (_ssl.c:993: The handshake operation timed out)
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                        logger.warning(f"YooKassa API request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                        import time
                        time.sleep(wait_time)
                    else:
                        logger.error(f"YooKassa API request failed after {max_retries} attempts: {e}")
                        raise
                except Exception as e:
                    # Для других ошибок не делаем retry
                    last_exception = e
                    raise
            
            # Если все попытки не удались, выбрасываем последнее исключение
            if last_exception and 'response' not in locals():
                raise last_exception

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

        payment = (
            db.query(Payment)
            .filter(Payment.yookassa_payment_id == yookassa_payment_id)
            .with_for_update()
            .first()
        )

        if not payment:
            logger.error(f"Payment not found: yookassa_payment_id={yookassa_payment_id}")
            return False

        webhook_amount_value = payment_object.get("amount", {}).get("value")
        if webhook_amount_value:
            webhook_amount_kopecks = int(float(webhook_amount_value) * 100)
            if webhook_amount_kopecks != payment.amount:
                logger.error(
                    f"Amount mismatch for payment {payment.id}: "
                    f"DB={payment.amount} kopecks, webhook={webhook_amount_kopecks} kopecks"
                )

        success, _ = PaymentService._finalize_payment_credit(
            db,
            payment,
            raw_payload=webhook_data,
            source="webhook",
        )
        if not success:
            logger.error(f"Failed to finalize webhook payment: payment_id={payment.id}")
        return success

    @staticmethod
    def _handle_payment_canceled(db: Session, payment_object: Dict[str, Any]) -> bool:
        """Handle canceled payment event."""
        yookassa_payment_id = payment_object.get("id")
        if not yookassa_payment_id:
            logger.error("No payment ID in canceled payment webhook")
            return False

        payment = (
            db.query(Payment)
            .filter(Payment.yookassa_payment_id == yookassa_payment_id)
            .with_for_update()
            .first()
        )

        if not payment:
            logger.error(f"Payment not found for cancellation: yookassa_payment_id={yookassa_payment_id}")
            return False

        payment.status = PaymentStatus.CANCELED
        payment.raw_data = payment_object
        db.commit()

        logger.info(f"Payment canceled: payment_id={payment.id}, yookassa_id={yookassa_payment_id}")
        return True

    @staticmethod
    def _finalize_payment_credit(
        db: Session,
        payment: Payment,
        *,
        source: str,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, bool]:
        """
        Apply credit for successful payment in a single transaction.
        
        Returns:
            tuple[bool, bool]: (operation_success, credited_now_flag)
        """
        if not payment:
            logger.error(f"{source}: payment object is missing")
            return False, False

        try:
            payment = (
                db.query(Payment)
                .filter(Payment.id == payment.id)
                .with_for_update()
                .one_or_none()
            )
            if not payment:
                logger.error(f"{source}: payment row missing during finalize")
                return False, False
            if payment.credited_at:
                if payment.status != PaymentStatus.SUCCEEDED:
                    payment.status = PaymentStatus.SUCCEEDED
                    db.flush()
                logger.info(
                    f"{source}: payment already credited at {payment.credited_at} (payment_id={payment.id})"
                )
                return True, False
            if payment.status == PaymentStatus.SUCCEEDED:
                logger.info(f"{source}: payment already succeeded (payment_id={payment.id})")
                return True, False

            balance = (
                db.query(Balance)
                .filter(Balance.user_id == payment.user_id)
                .with_for_update()
                .first()
            )
            if not balance:
                balance = Balance(user_id=payment.user_id, balance=0)
                db.add(balance)
                db.flush()

            balance_before = balance.balance
            balance.balance += payment.amount
            credited_now = True

            if raw_payload is not None:
                merged_payload: Any = raw_payload
                if isinstance(raw_payload, dict):
                    merged_payload = raw_payload.copy()
                    existing_metadata = {}
                    if isinstance(payment.raw_data, dict):
                        existing_metadata = payment.raw_data.get("metadata") or {}
                    metadata = dict(merged_payload.get("metadata") or {})
                    return_payment_id = existing_metadata.get("return_payment_id")
                    if return_payment_id and "return_payment_id" not in metadata:
                        metadata["return_payment_id"] = return_payment_id
                    if metadata:
                        merged_payload["metadata"] = metadata
                payment.raw_data = merged_payload

            payment.status = PaymentStatus.SUCCEEDED
            payment.credited_at = datetime.now(timezone.utc)
            db.flush()

            balance_after = balance.balance
            user = db.query(User).filter(User.id == payment.user_id).first()
            db.commit()

            amount_rubles = payment.amount / 100.0
            balance_before_rubles = balance_before / 100.0
            balance_after_rubles = balance_after / 100.0
            logger.info(
                f"{source}: payment finalized "
                f"(payment_id={payment.id}, yookassa_id={payment.yookassa_payment_id}, "
                f"amount={amount_rubles:.2f}₽, balance_before={balance_before_rubles:.2f}₽, "
                f"balance_after={balance_after_rubles:.2f}₽)"
            )

            if user and credited_now:
                try:
                    from app.core.telegram_sync import send_message_sync

                    send_message_sync(
                        chat_id=user.telegram_id,
                        text=(
                            f"🎉 **Оплата прошла успешно!**\n\n"
                            f"💰 Ваш баланс пополнен на {amount_rubles:.2f}₽\n"
                            f"💵 Текущий баланс: {balance_after_rubles:.2f}₽"
                        ),
                        parse_mode="Markdown",
                    )
                    logger.info(f"{source}: payment notification sent to user {user.telegram_id}")
                except Exception as notify_err:
                    logger.error(
                        f"{source}: failed to send payment notification to user {user.telegram_id}: {notify_err}",
                        exc_info=True,
                    )
            return True, credited_now
        except Exception as exc:
            db.rollback()
            logger.error(
                f"{source}: failed to finalize payment_id={payment.id if payment else 'unknown'}: {exc}",
                exc_info=True,
            )
            return False, False

    @staticmethod
    def _mark_payment_stale(db: Session, payment: Payment, reason: str) -> None:
        """Mark payment as STALE to reduce reconcile frequency."""
        if payment.status == PaymentStatus.STALE:
            # Update metadata only
            note = {
                "stale_reason": reason,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            if isinstance(payment.raw_data, dict):
                payload = payment.raw_data.copy()
            else:
                payload = {}
            payload["stale_info"] = note
            payment.raw_data = payload
            db.commit()
            return

        note = {
            "stale_reason": reason,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(payment.raw_data, dict):
            payload = payment.raw_data.copy()
        else:
            payload = {}
        payload["stale_info"] = note
        payment.raw_data = payload
        payment.status = PaymentStatus.STALE
        db.commit()

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
            payment_lookup = (
                db.query(Payment)
                .filter(Payment.yookassa_payment_id == yookassa_payment_id)
                .first()
            )
            if not payment_lookup:
                logger.warning(f"Payment not found in DB: yookassa_id={yookassa_payment_id}")
                return None

            # Make request to YooKassa
            auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
            auth_bytes = auth_string.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

            # Увеличиваем timeout для SSL handshake и добавляем retry логику
            # SSL handshake может занимать больше времени при проблемах с сетью
            timeout_config = httpx.Timeout(
                connect=60.0,  # Timeout for establishing connection (including SSL handshake) - увеличено до 60 сек
                read=60.0,     # Timeout for reading response - увеличено до 60 сек
                write=30.0,    # Timeout for writing request
                pool=30.0      # Timeout for getting connection from pool
            )
            
            # Retry логика для надежности
            max_retries = 3
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    with httpx.Client(timeout=timeout_config) as client:
                        response = client.get(
                            f"{YOOKASSA_API_URL}/payments/{yookassa_payment_id}",
                            headers={
                                "Authorization": f"Basic {auth_b64}",
                                "Content-Type": "application/json",
                            }
                        )
                    # Если запрос успешен, выходим из цикла retry
                    break
                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, OSError) as e:
                    # OSError может включать SSL handshake errors (_ssl.c:993: The handshake operation timed out)
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                        logger.warning(f"YooKassa API request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                        import time
                        time.sleep(wait_time)
                    else:
                        logger.error(f"YooKassa API request failed after {max_retries} attempts: {e}")
                        raise
                except Exception as e:
                    # Для других ошибок не делаем retry
                    last_exception = e
                    raise
            
            # Если все попытки не удались, выбрасываем последнее исключение
            if last_exception and 'response' not in locals():
                raise last_exception

            if response.status_code == 404:
                logger.warning(f"YooKassa payment not found: yookassa_id={yookassa_payment_id}")
                return {
                    "status": "not_found",
                    "paid": False,
                    "payment_id": payment_lookup.id,
                    "amount": payment_lookup.amount / 100.0,
                    "credited": False,
                }

            if response.status_code != 200:
                logger.error(f"YooKassa API error: {response.status_code}, {response.text}")
                return None

            payment_data = response.json()
            status = payment_data.get("status")
            paid = payment_data.get("paid", False)

            query = db.query(Payment).filter(
                Payment.yookassa_payment_id == yookassa_payment_id
            )
            if status in {"succeeded", "canceled"}:
                query = query.with_for_update()

            payment = query.first()

            if not payment:
                logger.warning(f"Payment not found in DB: yookassa_id={yookassa_payment_id}")
                return None

            if status == "succeeded":
                if not paid:
                    logger.warning(f"Payment {payment.id} is marked succeeded but paid flag is false, skipping credit")
                else:
                    processed, credited_now = PaymentService._finalize_payment_credit(
                        db,
                        payment,
                        raw_payload=payment_data,
                        source="status_check",
                    )
                    if not processed:
                        logger.error(f"Failed to finalize payment via status_check: payment_id={payment.id}")
                    else:
                        payment_data["credited_now"] = credited_now
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
                "credited": payment_data.get("credited_now", False),
            }

        except Exception as e:
            logger.error(f"Error checking payment status: {e}", exc_info=True)
            return None

    @staticmethod
    def _check_status_with_retry(
        db: Session,
        payment: Payment,
        *,
        max_attempts: int = 3,
    ) -> Optional[Dict[str, Any]]:
        delay = 2
        for attempt in range(1, max_attempts + 1):
            result = PaymentService.check_payment_status_from_yookassa(db, payment.yookassa_payment_id)
            if result is not None:
                return result
            if attempt < max_attempts:
                logger.warning(
                    "Retrying YooKassa status check for payment_id=%s (attempt %s/%s)",
                    payment.id,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(delay)
                delay = min(delay * 2, 30)
        return None

    @staticmethod
    def reconcile_pending_payments(
        batch_size: int = PAYMENT_RECONCILE_BATCH_SIZE,
        min_age_seconds: int = PAYMENT_RECONCILE_GRACE_SECONDS,
    ) -> Dict[str, int]:
        """
        Check provider state for pending payments and apply credit if needed.
        Returns summary statistics for logging.
        """
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.warning("YooKassa credentials not configured, skipping reconciliation")
            return {
                "scanned": 0,
                "processed": 0,
                "succeeded": 0,
                "canceled": 0,
                "credited": 0,
                "stale": 0,
                "errors": 0,
            }

        db = SessionLocal()
        stats = {
            "scanned": 0,
            "processed": 0,
            "succeeded": 0,
            "canceled": 0,
            "credited": 0,
            "stale": 0,
            "errors": 0,
        }
        try:
            now = datetime.now(timezone.utc)
            grace_cutoff = now - timedelta(seconds=min_age_seconds)
            stale_cutoff = now - timedelta(seconds=PAYMENT_RECONCILE_MAX_AGE_SECONDS)
            stale_recheck_cutoff = now - timedelta(seconds=PAYMENT_STALE_RECHECK_SECONDS)

            remaining = batch_size

            fresh_pending = (
                db.query(Payment)
                .filter(Payment.status == PaymentStatus.PENDING)
                .filter(Payment.created_at.isnot(None))
                .filter(Payment.created_at < grace_cutoff)
                .filter(Payment.created_at >= stale_cutoff)
                .order_by(Payment.created_at)
                .limit(max(0, remaining))
                .all()
            )
            remaining -= len(fresh_pending)

            aged_pending: list[Payment] = []
            if remaining > 0:
                aged_pending = (
                    db.query(Payment)
                    .filter(Payment.status == PaymentStatus.PENDING)
                    .filter(Payment.created_at.isnot(None))
                    .filter(Payment.created_at < stale_cutoff)
                    .order_by(Payment.created_at)
                    .limit(max(0, remaining))
                    .all()
                )
                remaining -= len(aged_pending)

            stale_retry: list[Payment] = []
            if remaining > 0:
                stale_retry = (
                    db.query(Payment)
                    .filter(Payment.status == PaymentStatus.STALE)
                    .filter(Payment.updated_at <= stale_recheck_cutoff)
                    .order_by(Payment.updated_at)
                    .limit(max(0, remaining))
                    .all()
                )
                remaining -= len(stale_retry)

            stats["scanned"] = len(fresh_pending) + len(aged_pending) + len(stale_retry)

            for payment in fresh_pending:
                if not payment.yookassa_payment_id:
                    logger.error(f"Skipping payment without provider ID: payment_id={payment.id}")
                    stats["errors"] += 1
                    continue

                prev_status = payment.status
                stats["processed"] += 1
                result = PaymentService._check_status_with_retry(db, payment)
                if result is None:
                    stats["errors"] += 1
                    continue

                db.refresh(payment)
                if payment.status == PaymentStatus.SUCCEEDED and prev_status != PaymentStatus.SUCCEEDED:
                    stats["succeeded"] += 1
                    stats["credited"] += 1
                if payment.status == PaymentStatus.CANCELED and prev_status != PaymentStatus.CANCELED:
                    stats["canceled"] += 1

            for payment in aged_pending:
                if not payment.yookassa_payment_id:
                    logger.error(f"Skipping old payment without provider ID: payment_id={payment.id}")
                    stats["errors"] += 1
                    continue

                prev_status = payment.status
                stats["processed"] += 1
                result = PaymentService._check_status_with_retry(db, payment, max_attempts=1)
                if result is None:
                    if prev_status != PaymentStatus.STALE:
                        stats["stale"] += 1
                    PaymentService._mark_payment_stale(db, payment, "provider_error")
                    continue

                status = (result.get("status") or "").lower()
                if status == "succeeded":
                    db.refresh(payment)
                    if payment.status == PaymentStatus.SUCCEEDED and prev_status != PaymentStatus.SUCCEEDED:
                        stats["succeeded"] += 1
                        stats["credited"] += 1
                    continue

                if status in {"canceled", "expired"}:
                    payment.status = PaymentStatus.CANCELED
                    payment.raw_data = result
                    db.commit()
                    if prev_status != PaymentStatus.CANCELED:
                        stats["canceled"] += 1
                    continue

                if prev_status != PaymentStatus.STALE:
                    stats["stale"] += 1
                PaymentService._mark_payment_stale(db, payment, status or "unknown")

            for payment in stale_retry:
                if not payment.yookassa_payment_id:
                    logger.error(f"Skipping stale payment without provider ID: payment_id={payment.id}")
                    stats["errors"] += 1
                    continue

                prev_status = payment.status
                stats["processed"] += 1
                result = PaymentService._check_status_with_retry(db, payment, max_attempts=1)
                if result is None:
                    PaymentService._mark_payment_stale(db, payment, "provider_error_retry")
                    continue

                status = (result.get("status") or "").lower()
                if status == "succeeded":
                    db.refresh(payment)
                    if payment.status == PaymentStatus.SUCCEEDED and prev_status != PaymentStatus.SUCCEEDED:
                        stats["succeeded"] += 1
                        stats["credited"] += 1
                    continue

                if status in {"canceled", "expired"}:
                    payment.status = PaymentStatus.CANCELED
                    payment.raw_data = result
                    db.commit()
                    if prev_status != PaymentStatus.CANCELED:
                        stats["canceled"] += 1
                    continue

                PaymentService._mark_payment_stale(db, payment, status or "pending")

            if stats["stale"]:
                logger.warning(
                    "Marked %s payments as stale (YooKassa unreachable or not_found)",
                    stats["stale"],
                )
            return stats
        except Exception as exc:
            logger.error(f"Failed to reconcile pending payments: {exc}", exc_info=True)
            stats["errors"] += 1
            return stats
        finally:
            db.close()


# Convenience functions
def create_payment(telegram_id: int, amount: int, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create payment (creates session)."""
    db = SessionLocal()
    try:
        user, _ = BillingService.get_or_create_user(db, telegram_id)
        return PaymentService.create_payment(db, user.id, amount, description)
    finally:
        db.close()

