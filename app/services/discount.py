"""Discount code service for managing promo codes."""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from loguru import logger
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

from app.db.models import DiscountCode, UserDiscountCode, User, Payment, Operation
from app.db.base import SessionLocal


class DiscountService:
    """Service for managing discount codes."""

    @staticmethod
    def validate_discount_code(
        db: Session,
        code: str,
        user_id: Optional[int] = None
    ) -> Tuple[bool, Optional[DiscountCode], Optional[str]]:
        """
        Validate discount code.
        
        Returns:
            Tuple[bool, Optional[DiscountCode], Optional[str]]: 
            (is_valid, discount_code, error_message)
        """
        code = code.upper().strip()
        
        discount = db.query(DiscountCode).filter(
            DiscountCode.code == code
        ).first()

        if not discount:
            return False, None, "Промокод не найден"

        if not discount.is_active:
            return False, None, "Промокод неактивен"

        # Check validity dates
        now = datetime.utcnow()
        if discount.valid_from and discount.valid_from > now:
            return False, None, "Промокод еще не действителен"
        
        if discount.valid_until and discount.valid_until < now:
            return False, None, "Промокод истек"

        # Check max uses
        if discount.max_uses and discount.current_uses >= discount.max_uses:
            return False, None, "Промокод исчерпан"

        return True, discount, None

    @staticmethod
    def apply_discount_to_payment(
        db: Session,
        discount_code: DiscountCode,
        user_id: int,
        payment_id: int
    ) -> Tuple[int, int]:
        """
        Apply discount to payment amount.
        
        Returns:
            Tuple[int, int]: (discounted_amount, discount_amount)
        """
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise ValueError("Payment not found")

        original_amount = payment.amount
        
        # Calculate discount with proper rounding
        discount_amount = round(original_amount * discount_code.discount_percent / 100)
        discounted_amount = original_amount - discount_amount

        # Record usage
        user_discount = UserDiscountCode(
            user_id=user_id,
            discount_code_id=discount_code.id,
            payment_id=payment_id
        )
        db.add(user_discount)

        # Update discount code usage count
        discount_code.current_uses += 1
        db.commit()

        logger.info(
            f"Applied discount {discount_code.code} ({discount_code.discount_percent}%) "
            f"to payment {payment_id}: {original_amount}₽ -> {discounted_amount}₽"
        )

        return discounted_amount, discount_amount

    @staticmethod
    def apply_free_generation_code(
        db: Session,
        discount_code: DiscountCode,
        user_id: int
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Apply free generation code to user.
        
        Returns:
            Tuple[bool, Optional[str], Optional[int]]: 
            (success, error_message, free_generations_added)
        """
        if not discount_code.is_free_generation:
            return False, "Этот промокод не для бесплатных генераций", None

        if not discount_code.free_generations_count:
            return False, "Промокод не содержит бесплатных генераций", None

        # Check if user already used this code
        existing_usage = db.query(UserDiscountCode).filter(
            and_(
                UserDiscountCode.user_id == user_id,
                UserDiscountCode.discount_code_id == discount_code.id
            )
        ).first()

        if existing_usage:
            return False, "Вы уже использовали этот промокод", None

        # Add free operations to user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found", None

        user.free_operations_left += discount_code.free_generations_count

        # Record usage
        user_discount = UserDiscountCode(
            user_id=user_id,
            discount_code_id=discount_code.id
        )
        db.add(user_discount)

        # Update discount code usage count
        discount_code.current_uses += 1
        db.commit()

        logger.info(
            f"Applied free generation code {discount_code.code} "
            f"to user {user_id}: +{discount_code.free_generations_count} free operations"
        )

        return True, None, discount_code.free_generations_count

    @staticmethod
    def activate_free_access(
        db: Session,
        discount_code: DiscountCode,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Activate free access for user (unlimited free operations).
        
        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        # Check if user already used this code
        existing_usage = db.query(UserDiscountCode).filter(
            and_(
                UserDiscountCode.user_id == user_id,
                UserDiscountCode.discount_code_id == discount_code.id
            )
        ).first()

        if existing_usage:
            return False, "Вы уже использовали этот промокод"

        # Activate free access
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        user.has_free_access = True

        # Record usage
        user_discount = UserDiscountCode(
            user_id=user_id,
            discount_code_id=discount_code.id
        )
        db.add(user_discount)

        # Update discount code usage count
        discount_code.current_uses += 1
        db.commit()

        logger.info(
            f"Activated free access for user {user_id} with code {discount_code.code}"
        )

        return True, None

    @staticmethod
    def create_discount_code(
        db: Session,
        code: str,
        discount_percent: int,
        max_uses: Optional[int] = None,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        is_free_generation: bool = False,
        free_generations_count: Optional[int] = None
    ) -> DiscountCode:
        """Create a new discount code."""
        discount = DiscountCode(
            code=code.upper().strip(),
            discount_percent=discount_percent,
            max_uses=max_uses,
            valid_from=valid_from,
            valid_until=valid_until,
            is_free_generation=is_free_generation,
            free_generations_count=free_generations_count
        )
        db.add(discount)
        db.commit()
        logger.info(f"Created discount code: {code} ({discount_percent}%)")
        return discount

    @staticmethod
    def get_discount_info(db: Session, code: str) -> Optional[Dict[str, Any]]:
        """Get discount code information."""
        discount = db.query(DiscountCode).filter(
            DiscountCode.code == code.upper().strip()
        ).first()

        if not discount:
            return None

        return {
            "code": discount.code,
            "discount_percent": discount.discount_percent,
            "is_active": discount.is_active,
            "max_uses": discount.max_uses,
            "current_uses": discount.current_uses,
            "is_free_generation": discount.is_free_generation,
            "free_generations_count": discount.free_generations_count,
            "valid_from": discount.valid_from.isoformat() if discount.valid_from else None,
            "valid_until": discount.valid_until.isoformat() if discount.valid_until else None,
        }


def init_default_discount_codes(db: Session):
    """Initialize default discount codes (10%, 20%, 30%) and free access code."""
    codes = [
        {"code": "WELCOME10", "percent": 10},
        {"code": "SAVE20", "percent": 20},
        {"code": "BONUS30", "percent": 30},
    ]

    for code_data in codes:
        existing = db.query(DiscountCode).filter(
            DiscountCode.code == code_data["code"]
        ).first()
        
        if not existing:
            DiscountService.create_discount_code(
                db,
                code=code_data["code"],
                discount_percent=code_data["percent"],
                max_uses=None  # Без ограничений
            )
            logger.info(f"Created default discount code: {code_data['code']} ({code_data['percent']}%)")
    
    # Create free access code (for admin/unlimited free operations)
    free_access_code = db.query(DiscountCode).filter(
        DiscountCode.code == "FREE_ACCESS"
    ).first()
    
    if not free_access_code:
        DiscountService.create_discount_code(
            db,
            code="FREE_ACCESS",
            discount_percent=0,
            is_free_generation=False,  # This is not for limited free operations
            free_generations_count=None,  # Unlimited
            max_uses=None  # Can be used by multiple users
        )
        logger.info("Created free access code: FREE_ACCESS (unlimited free operations)")

