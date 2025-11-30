#!/usr/bin/env python3
"""Script to create default discount codes in PostgreSQL database."""
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import SessionLocal
from app.services.discount import DiscountService
from app.db.models import DiscountCode
from loguru import logger

def create_default_discount_codes():
    """Create default discount codes."""
    db = SessionLocal()
    try:
        # Check if codes already exist
        existing_codes = db.query(DiscountCode).all()
        if existing_codes:
            logger.info(f"Found {len(existing_codes)} existing discount codes:")
            for code in existing_codes:
                logger.info(f"  - {code.code}: {code.discount_percent}% (active: {code.is_active})")
        
        # Create WELCOME10 (10% discount)
        welcome10 = db.query(DiscountCode).filter(DiscountCode.code == "WELCOME10").first()
        if not welcome10:
            DiscountService.create_discount_code(
                db,
                code="WELCOME10",
                discount_percent=10,
                max_uses=None,  # Без ограничений
            )
            logger.info("✅ Created WELCOME10 (10% discount)")
        else:
            logger.info("ℹ️  WELCOME10 already exists")
        
        # Create SAVE20 (20% discount)
        save20 = db.query(DiscountCode).filter(DiscountCode.code == "SAVE20").first()
        if not save20:
            DiscountService.create_discount_code(
                db,
                code="SAVE20",
                discount_percent=20,
                max_uses=None,  # Без ограничений
            )
            logger.info("✅ Created SAVE20 (20% discount)")
        else:
            logger.info("ℹ️  SAVE20 already exists")
        
        # Create BONUS30 (30% discount)
        bonus30 = db.query(DiscountCode).filter(DiscountCode.code == "BONUS30").first()
        if not bonus30:
            DiscountService.create_discount_code(
                db,
                code="BONUS30",
                discount_percent=30,
                max_uses=None,  # Без ограничений
            )
            logger.info("✅ Created BONUS30 (30% discount)")
        else:
            logger.info("ℹ️  BONUS30 already exists")
        
        # Create FREE_ACCESS (unlimited free operations)
        free_access = db.query(DiscountCode).filter(DiscountCode.code == "FREE_ACCESS").first()
        if not free_access:
            DiscountService.create_discount_code(
                db,
                code="FREE_ACCESS",
                discount_percent=0,
                is_free_generation=False,  # This is not for limited free operations
                free_generations_count=None,  # Unlimited
                max_uses=None  # Can be used by multiple users
            )
            logger.info("✅ Created FREE_ACCESS (unlimited free operations)")
        else:
            logger.info("ℹ️  FREE_ACCESS already exists")
        
        # Show all discount codes
        all_codes = db.query(DiscountCode).all()
        logger.info(f"\n📋 Всего промокодов в базе: {len(all_codes)}")
        for code in all_codes:
            uses_info = f"{code.current_uses}/{code.max_uses}" if code.max_uses else "Без ограничений"
            logger.info(
                f"  • {code.code}: {code.discount_percent}% "
                f"(использований: {uses_info}, активен: {code.is_active})"
            )
        
    except Exception as e:
        logger.error(f"Error creating discount codes: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_default_discount_codes()

