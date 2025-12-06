"""Billing service for managing user balance and operations."""
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from loguru import logger
from typing import Optional, Tuple
import os

from app.db.models import User, Balance, Operation, OperationStatus
from app.db.base import SessionLocal
from app.services.pricing import get_operation_price, get_price_with_discount

# Price per operation from environment (legacy, kept for backward compatibility)
PRICE_PER_OPERATION = int(os.getenv("PRICE_PER_OPERATION", "10"))


class BillingService:
    """Service for managing billing operations."""

    @staticmethod
    def _normalize_is_premium(value: Optional[bool]) -> bool:
        """Ensure is_premium is never None (None -> False)."""
        return bool(value) if value is not None else False

    @staticmethod
    def get_or_create_user(
        db: Session, 
        telegram_id: int,
        telegram_user: Optional[object] = None  # aiogram User object
    ) -> Tuple[User, bool]:
        """
        Get or create user by telegram_id.
        
        Args:
            db: Database session
            telegram_id: Telegram user ID
            telegram_user: Optional aiogram User object with profile information
        
        Returns:
            Tuple[User, bool]: (user, is_new)
        """
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        is_new = False
        
        # Normalize legacy nullable fields (always enforce bool)
        if user:
            normalized_existing = BillingService._normalize_is_premium(user.is_premium)
            if user.is_premium != normalized_existing:
                user.is_premium = normalized_existing
                db.commit()
                db.refresh(user)

        # Update user profile if telegram_user is provided
        if telegram_user and user:
            updated = False
            if hasattr(telegram_user, 'username') and telegram_user.username != user.username:
                user.username = telegram_user.username
                updated = True
            if hasattr(telegram_user, 'first_name') and telegram_user.first_name != user.first_name:
                user.first_name = telegram_user.first_name
                updated = True
            if hasattr(telegram_user, 'last_name'):
                if telegram_user.last_name != user.last_name:
                    user.last_name = telegram_user.last_name
                    updated = True
            if hasattr(telegram_user, 'language_code') and telegram_user.language_code != user.language_code:
                user.language_code = telegram_user.language_code
                updated = True
            # CRITICAL: getattr returns None if attribute exists but is None, not the default
            # So we need to check explicitly
            if hasattr(telegram_user, "is_premium"):
                incoming_premium = telegram_user.is_premium
            else:
                incoming_premium = user.is_premium
            # Always normalize, even if incoming_premium is None
            normalized_premium = BillingService._normalize_is_premium(incoming_premium)
            # Always update if normalized value differs from current, or if current is None
            if normalized_premium != user.is_premium or user.is_premium is None:
                user.is_premium = normalized_premium
                # CRITICAL: Verify assignment worked
                if user.is_premium is None:
                    logger.error(
                        "CRITICAL: User %s.is_premium is None after assignment! Forcing via __dict__.",
                        user.id
                    )
                    user.__dict__['is_premium'] = False
                    object.__setattr__(user, 'is_premium', False)
                updated = True
            if updated:
                from datetime import datetime, timezone
                from sqlalchemy import inspect as sa_inspect
                user.last_activity_at = datetime.now(timezone.utc)
                # CRITICAL: Force normalize is_premium one more time before commit
                if user.is_premium is None:
                    logger.error(
                        "CRITICAL: User %s had is_premium=None right before commit! Forcing False.",
                        user.id
                    )
                    user.is_premium = False
                # Check SQLAlchemy's internal state
                insp = sa_inspect(user)
                if insp.attrs.is_premium.value is None:
                    logger.error(
                        "CRITICAL: User %s SQLAlchemy state has is_premium=None! Forcing False.",
                        user.id
                    )
                    user.is_premium = False
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(user, 'is_premium')
                logger.info(
                    "USER UPDATE: id=%s, is_premium=%s, last_activity_at=%s",
                    user.id,
                    user.is_premium,
                    user.last_activity_at,
                )
                # Final check: ensure is_premium is not None in the object's dict
                if hasattr(user, '__dict__') and user.__dict__.get('is_premium') is None:
                    logger.error(
                        "CRITICAL: User %s.__dict__['is_premium'] is None! Forcing False in __dict__.",
                        user.id
                    )
                    user.__dict__['is_premium'] = False
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(user, 'is_premium')
                db.commit()
                logger.debug(f"Updated user profile: telegram_id={telegram_id}")

        # Final guard: ensure is_premium is always boolean before returning
        if user:
            normalized_final = BillingService._normalize_is_premium(user.is_premium)
            if user.is_premium != normalized_final:
                user.is_premium = normalized_final
                db.commit()
                db.refresh(user)
        
        if not user:
            # Create new user with starting balance of 30 rubles
            user_data = {
                "telegram_id": telegram_id,
                "free_operations_left": 0,
                "is_premium": BillingService._normalize_is_premium(
                    getattr(telegram_user, "is_premium", None) if telegram_user else False
                ),
            }
            
            # Add Telegram profile information if available
            if telegram_user:
                if hasattr(telegram_user, 'username'):
                    user_data["username"] = telegram_user.username
                if hasattr(telegram_user, 'first_name'):
                    user_data["first_name"] = telegram_user.first_name
                if hasattr(telegram_user, 'last_name'):
                    user_data["last_name"] = telegram_user.last_name
                if hasattr(telegram_user, 'language_code'):
                    user_data["language_code"] = telegram_user.language_code
                user_data["is_premium"] = BillingService._normalize_is_premium(
                    getattr(telegram_user, "is_premium", user_data["is_premium"])
                )
                from datetime import datetime, timezone
                user_data["last_activity_at"] = datetime.now(timezone.utc)
            
            user = User(**user_data)
            db.add(user)
            db.flush()  # Get user.id
            
            # Create balance with 30 rubles starting bonus
            STARTING_BALANCE = 30
            balance = Balance(user_id=user.id, balance=STARTING_BALANCE)
            db.add(balance)
            
            # Create user statistics
            from app.db.models import UserStatistics
            stats = UserStatistics(user_id=user.id)
            db.add(stats)
            
            try:
                db.commit()
                is_new = True
                logger.info(f"Created new user: telegram_id={telegram_id}, starting_balance={STARTING_BALANCE}₽")
            except IntegrityError:
                db.rollback()
                # User might have been created concurrently
                user = db.query(User).filter(User.telegram_id == telegram_id).first()
                if not user:
                    raise
        
        return user, is_new

    @staticmethod
    def get_user_balance(db: Session, user_id: int) -> int:
        """Get user balance in rubles."""
        balance = db.query(Balance).filter(Balance.user_id == user_id).first()
        if not balance:
            return 0
        return balance.balance

    @staticmethod
    def get_free_operations_left(db: Session, user_id: int) -> int:
        """Get remaining free operations count."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return 0
        return max(0, user.free_operations_left)

    @staticmethod
    def reserve_operation(
        db: Session,
        user_id: int,
        operation_type: str,
        task_id: Optional[str] = None,
        model: Optional[str] = None,
        is_nano_banana_pro: bool = False,
        discount_percent: Optional[int] = None,
        prompt: Optional[str] = None,
        image_count: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Reserve operation (check balance and create PENDING operation, but don't charge yet).
        Charge will happen only after successful completion via confirm_operation.
        
        Args:
            db: Database session
            user_id: User ID
            operation_type: Type of operation (generate, edit, merge, prompt_generation, face_swap, add_text)
            task_id: Optional task ID (job_id)
            model: Optional model name (for determining Nano Banana Pro)
            is_nano_banana_pro: Explicit flag if it's Nano Banana Pro
            discount_percent: Optional discount percentage (10, 20, 30, etc.)
        
        Returns:
            Tuple[bool, Optional[str], Optional[int]]: 
            (success, error_message, operation_id)
        """
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            return False, "User not found", None

        # Get operation price
        logger.debug(f"reserve_operation: operation_type={operation_type}, model={model}, is_nano_banana_pro={is_nano_banana_pro}")
        price, discount_amount = get_price_with_discount(
            operation_type=operation_type,
            discount_percent=discount_percent,
            model=model,
            is_nano_banana_pro=is_nano_banana_pro
        )
        logger.info(f"reserve_operation: calculated price={price}₽ (discount={discount_amount}₽) for operation_type={operation_type}, model={model}")

        # Check if user has free access (unlimited free operations)
        if user.has_free_access:
            # Truncate prompt if too long (max 2000 characters)
            prompt_truncated = None
            if prompt:
                prompt_truncated = prompt[:2000] if len(prompt) > 2000 else prompt
            
            operation = Operation(
                user_id=user_id,
                type=operation_type,
                price=0,
                status=OperationStatus.FREE,
                task_id=task_id,
                model=model,  # Model used
                prompt=prompt_truncated,  # User prompt (truncated)
                image_count=image_count  # Number of images (for merge operations)
            )
            db.add(operation)
            db.commit()
            logger.info(f"Free access operation: user_id={user_id}, type={operation_type} (has_free_access=True)")
            return True, None, operation.id

        balance = db.query(Balance).filter(Balance.user_id == user_id).with_for_update().first()
        if not balance:
            balance = Balance(user_id=user_id, balance=0)
            db.add(balance)
            db.flush()

        # Convert price to kopecks (multiply by 100) for storage
        price_kopecks = int(round(price * 100))
        
        # Check balance (but don't charge yet) - balance is in rubles, convert to kopecks for comparison
        if balance.balance * 100 < price_kopecks:
            db.rollback()
            return False, f"Insufficient balance. Need {price:.2f}₽, have {balance.balance}₽", None

        # Create PENDING operation (reserve, but don't charge yet)
        # Calculate original price if discount was applied
        # IMPORTANT: Use the same model parameter to ensure correct price calculation (e.g., Seedream = 7.5₽, not 9₽)
        original_price_kopecks = None
        if discount_percent and discount_percent > 0:
            original_price = get_operation_price(operation_type, model, is_nano_banana_pro)
            original_price_kopecks = int(round(original_price * 100))
            logger.debug(f"reserve_operation: calculated original_price={original_price}₽ ({original_price_kopecks} kopecks) for operation_type={operation_type}, model={model}")
        
        # Truncate prompt if too long (max 2000 characters)
        prompt_truncated = None
        if prompt:
            prompt_truncated = prompt[:2000] if len(prompt) > 2000 else prompt
        
        operation = Operation(
            user_id=user_id,
            type=operation_type,
            price=price_kopecks,  # Final price after discount in kopecks
            original_price=original_price_kopecks,  # Original price before discount in kopecks
            discount_percent=discount_percent,  # Discount percentage if applied
            status=OperationStatus.PENDING,  # Will be charged only after success
            task_id=task_id,
            model=model,  # Model used
            prompt=prompt_truncated,  # User prompt (truncated)
            image_count=image_count  # Number of images (for merge operations)
        )
        db.add(operation)
        db.flush()  # Убеждаемся, что операция сохранена и получила ID
        operation_id = operation.id
        
        # Проверяем, что операция действительно получила ID
        if not operation_id:
            db.rollback()
            logger.error(f"Failed to get operation ID after flush for user_id={user_id}")
            return False, "Failed to create operation", None
        
        try:
            db.commit()  # Фиксируем транзакцию
            logger.debug(f"Committed operation {operation_id} to database")
        except Exception as commit_error:
            db.rollback()
            logger.error(f"Failed to commit operation {operation_id}: {commit_error}", exc_info=True)
            return False, f"Failed to commit operation: {commit_error}", None
        
        # Проверяем, что операция действительно сохранена после commit
        try:
            # Создаем новую сессию для проверки
            from app.db.base import SessionLocal
            check_db = SessionLocal()
            check_op = check_db.query(Operation).filter(Operation.id == operation_id).first()
            if not check_op:
                logger.error(f"Operation {operation_id} not found in database after commit! This is a critical error.")
                check_db.close()
                return False, "Operation was not saved to database", None
            check_db.close()
            logger.debug(f"Verified operation {operation_id} exists in database after commit")
        except Exception as verify_error:
            logger.warning(f"Failed to verify operation {operation_id} after commit: {verify_error}", exc_info=True)
            # Не возвращаем ошибку, так как commit уже прошел
        
        # Синхронизируем БД с общим файлом для воркеров с network_mode: host
        # Примечание: БД уже находится в /tmp/media_lab_shared.db, синхронизация не нужна
        # Но оставляем код для обратной совместимости
        try:
            import shutil
            # Получаем путь к БД из URL
            db_url = str(db.bind.url)
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")
                # Если БД уже в общем месте, синхронизация не нужна
                if "/app/db/" in db_path or "/tmp/media_lab_shared.db" in db_path:
                    logger.debug(f"Database already at shared location: {db_path}")
                else:
                    # Старая логика синхронизации для обратной совместимости
                    shared_db_path = "/app/db/media_lab_shared.db"
                    if os.path.exists(db_path) and db_path != shared_db_path:
                        try:
                            os.makedirs(os.path.dirname(shared_db_path), exist_ok=True)
                            shutil.copy2(db_path, shared_db_path)
                            logger.info(f"Synced database to shared location: {shared_db_path} (from {db_path})")
                        except Exception as e:
                            logger.warning(f"Failed to sync database: {e}")
                    elif not os.path.exists(db_path):
                        logger.warning(f"Database file not found at {db_path}, cannot sync")
        except Exception as sync_error:
            logger.warning(f"Failed to sync database to shared location: {sync_error}", exc_info=True)
        
        logger.info(
            f"Reserved operation: user_id={user_id}, type={operation_type}, "
            f"price={price:.2f}₽ ({price_kopecks} kopecks), operation_id={operation_id}, status=PENDING"
        )
        return True, None, operation_id

    @staticmethod
    def _update_user_statistics(db: Session, operation: Operation) -> None:
        """
        Update user statistics after operation completion.
        
        Args:
            db: Database session
            operation: Completed operation
        """
        try:
            from app.db.models import UserStatistics
            import json
            from datetime import datetime, timezone
            
            stats = db.query(UserStatistics).filter(UserStatistics.user_id == operation.user_id).first()
            if not stats:
                stats = UserStatistics(user_id=operation.user_id)
                db.add(stats)
                db.flush()
            
            # Update counters
            stats.total_operations += 1
            if operation.status == OperationStatus.CHARGED or operation.status == OperationStatus.FREE:
                # Convert price to rubles based on operation date
                # Operations before 2025-11-25 09:30 UTC are in rubles (old format)
                # Operations after are in kopecks (new format)
                from datetime import datetime, timezone
                KOPECKS_MIGRATION_DATETIME = datetime(2025, 11, 25, 9, 30, 0, tzinfo=timezone.utc)
                
                if operation.created_at:
                    # SQLite returns naive datetime, assume UTC
                    if operation.created_at.tzinfo is None:
                        created_at_utc = operation.created_at.replace(tzinfo=timezone.utc)
                    else:
                        created_at_utc = operation.created_at.astimezone(timezone.utc)
                    
                    if created_at_utc < KOPECKS_MIGRATION_DATETIME:
                        # Old format: price is already in rubles
                        price_rubles = float(operation.price)
                    else:
                        # New format: price is in kopecks, convert to rubles
                        price_rubles = float(operation.price) / 100.0
                else:
                    # Fallback heuristic: if price > 100, assume kopecks
                    if operation.price > 100:
                        price_rubles = float(operation.price) / 100.0
                    else:
                        price_rubles = float(operation.price)
                
                stats.total_spent += price_rubles
            
            # Update operations by type
            ops_by_type = json.loads(stats.operations_by_type) if stats.operations_by_type else {}
            ops_by_type[operation.type] = ops_by_type.get(operation.type, 0) + 1
            stats.operations_by_type = json.dumps(ops_by_type)
            
            # Update models used
            if operation.model:
                models_used = json.loads(stats.models_used) if stats.models_used else {}
                models_used[operation.model] = models_used.get(operation.model, 0) + 1
                stats.models_used = json.dumps(models_used)
            
            # Update first and last operation timestamps
            now = datetime.now(timezone.utc)
            if not stats.first_operation_at:
                stats.first_operation_at = now
            stats.last_operation_at = now
            
            db.commit()
            logger.debug(f"Updated statistics for user_id={operation.user_id}")
        except Exception as e:
            logger.warning(f"Failed to update user statistics: {e}", exc_info=True)
            # Don't fail the operation if statistics update fails
            db.rollback()

    @staticmethod
    def confirm_operation(db: Session, operation_id: int) -> bool:
        """
        Confirm operation and charge user (called after successful completion).
        
        Returns:
            bool: Success
        """
        # Убеждаемся, что operation_id - это int
        if not isinstance(operation_id, int):
            try:
                operation_id = int(operation_id)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid operation_id type: {type(operation_id)}, value: {operation_id}, error: {e}")
                return False
        
        logger.info(f"Confirming operation: operation_id={operation_id} (type: {type(operation_id).__name__})")
        
        # Проверяем, существует ли операция (без блокировки сначала)
        operation_check = db.query(Operation).filter(Operation.id == operation_id).first()
        if not operation_check:
            # Проверяем последние операции для диагностики
            recent_ops = db.query(Operation).order_by(Operation.id.desc()).limit(10).all()
            logger.error(
                f"Operation not found: operation_id={operation_id}. "
                f"Recent operations (last 10): {[(op.id, op.status, op.user_id, op.type) for op in recent_ops]}"
            )
            # Пробуем найти операцию по другим критериям
            all_ops = db.query(Operation).filter(Operation.status == OperationStatus.PENDING).all()
            logger.error(
                f"All PENDING operations: {[(op.id, op.user_id, op.type, op.price) for op in all_ops]}"
            )
            return False
        
        # Теперь получаем с блокировкой для обновления
        operation = db.query(Operation).filter(Operation.id == operation_id).with_for_update().first()
        if not operation:
            logger.error(f"Operation not found with lock: operation_id={operation_id}")
            return False

        if operation.status != OperationStatus.PENDING:
            logger.warning(
                f"Operation cannot be confirmed (not PENDING): "
                f"operation_id={operation_id}, status={operation.status}"
            )
            return False

        if operation.price == 0:
            # Free operation, just mark as completed
            operation.status = OperationStatus.FREE
            db.commit()
            # Update statistics
            BillingService._update_user_statistics(db, operation)
            logger.info(f"Confirmed free operation: operation_id={operation_id}")
            return True

        # Charge from balance
        balance = db.query(Balance).filter(Balance.user_id == operation.user_id).with_for_update().first()
        if not balance:
            balance = Balance(user_id=operation.user_id, balance=0)
            db.add(balance)
            db.flush()

        # Check balance again (might have changed)
        # operation.price is in kopecks, balance.balance is in rubles
        price_rubles = operation.price / 100.0
        if balance.balance < price_rubles:
            logger.error(
                f"Insufficient balance to confirm operation: "
                f"operation_id={operation_id}, need={price_rubles:.2f}₽, have={balance.balance}₽"
            )
            operation.status = OperationStatus.FAILED
            db.commit()
            return False

        # Charge from balance (convert kopecks to rubles)
        balance.balance -= price_rubles
        operation.status = OperationStatus.CHARGED
        db.commit()
        
        # Update statistics
        BillingService._update_user_statistics(db, operation)
        
        # Синхронизируем БД с общим файлом для воркеров с network_mode: host
        # Если операция подтверждена в shared DB, синхронизируем обратно в бота
        try:
            import shutil
            db_url = str(db.bind.url)
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")
                shared_db_path = "/tmp/media_lab_shared.db"
                bot_db_path = "/app/media_lab.db"
                
                if db_path == shared_db_path:
                    # Worker confirmed operation in shared DB, sync back to bot
                    if os.path.exists(shared_db_path) and os.path.exists(bot_db_path):
                        shutil.copy2(shared_db_path, bot_db_path)
                        logger.info(f"Synced database from shared location back to bot: {bot_db_path} (from {shared_db_path})")
                elif db_path != shared_db_path and os.path.exists(db_path):
                    # Bot confirmed operation, sync to shared location
                    shutil.copy2(db_path, shared_db_path)
                    logger.info(f"Synced database to shared location after charge: {shared_db_path} (from {db_path})")
                elif not os.path.exists(db_path):
                    logger.warning(f"Database file not found at {db_path}, cannot sync")
        except Exception as sync_error:
            logger.warning(f"Failed to sync database: {sync_error}", exc_info=True)
        
        price_rubles = operation.price / 100.0
        logger.info(
            f"Confirmed and charged operation: operation_id={operation_id}, "
            f"type={operation.type}, price={price_rubles:.2f}₽ ({operation.price} kopecks), "
            f"new_balance={balance.balance:.2f}₽"
        )
        return True

    @staticmethod
    def fail_operation(db: Session, operation_id: int) -> bool:
        """
        Mark operation as failed (no charge).
        
        Returns:
            bool: Success
        """
        operation = db.query(Operation).filter(Operation.id == operation_id).first()
        if not operation:
            logger.error(f"Operation not found: operation_id={operation_id}")
            return False

        if operation.status == OperationStatus.CHARGED:
            logger.warning(
                f"Operation already charged, cannot mark as failed: "
                f"operation_id={operation_id}"
            )
            return False

        if operation.status == OperationStatus.FREE:
            # Free operation, just mark as failed
            operation.status = OperationStatus.FAILED
            db.commit()
            logger.info(f"Marked free operation as failed: operation_id={operation_id}")
            return True

        # Mark as failed (no charge for PENDING operations)
        operation.status = OperationStatus.FAILED
        db.commit()
        
        logger.info(
            f"Marked operation as failed (no charge): operation_id={operation_id}, "
            f"type={operation.type}, price={operation.price}₽"
        )
        return True

    @staticmethod
    def charge_operation(
        db: Session,
        user_id: int,
        operation_type: str,
        task_id: Optional[str] = None,
        model: Optional[str] = None,
        is_nano_banana_pro: bool = False,
        discount_percent: Optional[int] = None,
        prompt: Optional[str] = None,
        image_count: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Legacy method - redirects to reserve_operation for backward compatibility.
        Use reserve_operation for new code.
        """
        return BillingService.reserve_operation(
            db, user_id, operation_type, task_id, model, is_nano_banana_pro, discount_percent, prompt, image_count
        )

    @staticmethod
    def refund_operation(db: Session, operation_id: int) -> bool:
        """
        Refund operation (return money to user).
        
        Returns:
            bool: Success
        """
        operation = db.query(Operation).filter(Operation.id == operation_id).first()
        if not operation:
            logger.error(f"Operation not found: operation_id={operation_id}")
            return False

        if operation.status != OperationStatus.CHARGED:
            logger.warning(f"Operation cannot be refunded: operation_id={operation_id}, status={operation.status}")
            return False

        if operation.price == 0:
            # Free operation, just mark as refunded
            operation.status = OperationStatus.REFUNDED
            db.commit()
            return True

        # Refund money to balance
        balance = db.query(Balance).filter(Balance.user_id == operation.user_id).with_for_update().first()
        if not balance:
            balance = Balance(user_id=operation.user_id, balance=0)
            db.add(balance)
            db.flush()

        # Refund: operation.price is in kopecks, balance.balance is in rubles
        balance.balance += operation.price / 100.0
        operation.status = OperationStatus.REFUNDED
        db.commit()
        logger.info(f"Refunded operation: operation_id={operation_id}, amount={operation.price}₽, new_balance={balance.balance}₽")
        return True

    @staticmethod
    def add_balance(db: Session, user_id: int, amount: int) -> bool:
        """
        Add balance to user account.
        
        Returns:
            bool: Success
        """
        balance = db.query(Balance).filter(Balance.user_id == user_id).with_for_update().first()
        if not balance:
            balance = Balance(user_id=user_id, balance=0)
            db.add(balance)
            db.flush()

        balance.balance += amount
        db.commit()
        logger.info(f"Added balance: user_id={user_id}, amount={amount}₽, new_balance={balance.balance}₽")
        return True

    @staticmethod
    def get_user_info(db: Session, telegram_id: int) -> Optional[dict]:
        """
        Get user billing information.
        
        Returns:
            dict with balance, free_operations_left, has_free_access, or None if user not found
        """
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return None

        balance = db.query(Balance).filter(Balance.user_id == user.id).first()
        balance_amount = balance.balance if balance else 0

        return {
            "balance": balance_amount,
            "free_operations_left": 0,  # Deprecated: no longer used
            "free_operations_total": 0,  # Deprecated: no longer used
            "has_free_access": user.has_free_access,
        }

    @staticmethod
    def get_user_operations(
        db: Session,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> list[dict]:
        """
        Get user operations history.
        
        Returns:
            List of operation dicts with type, price, status, created_at, discount info
        """
        from sqlalchemy import desc
        
        operations = db.query(Operation).filter(
            Operation.user_id == user_id
        ).order_by(desc(Operation.created_at)).limit(limit).offset(offset).all()
        
        result = []
        for op in operations:
            result.append({
                "id": op.id,
                "type": op.type,
                "price": op.price,
                "original_price": op.original_price,
                "discount_percent": op.discount_percent,
                "status": op.status.value,
                "created_at": op.created_at,
                "task_id": op.task_id,
            })
        
        return result

    @staticmethod
    def get_operations_count(db: Session, user_id: int) -> int:
        """Get total count of user operations."""
        return db.query(Operation).filter(Operation.user_id == user_id).count()


# Convenience functions
def get_user_info(telegram_id: int) -> Optional[dict]:
    """Get user billing info (creates session)."""
    db = SessionLocal()
    try:
        return BillingService.get_user_info(db, telegram_id)
    finally:
        db.close()


