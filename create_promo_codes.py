#!/usr/bin/env python3
"""Script to create required discount codes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import SessionLocal
from app.services.discount import DiscountService
from app.db.models import DiscountCode
from loguru import logger

def create_promo_codes():
    """Create required discount codes."""
    db = SessionLocal()
    try:
        codes_to_create = [
            {"code": "WELCOME10", "discount_percent": 10},
            {"code": "SAVE20", "discount_percent": 20},
            {"code": "BONUS30", "discount_percent": 30},
            {"code": "FREE_ACCESS", "discount_percent": 0, "is_free_generation": False},
        ]
        
        created = []
        existing = []
        
        for code_data in codes_to_create:
            code = code_data["code"]
            existing_code = db.query(DiscountCode).filter(DiscountCode.code == code).first()
            
            if existing_code:
                # Update if exists but inactive
                if not existing_code.is_active:
                    existing_code.is_active = True
                    db.commit()
                    logger.info(f"✅ Reactivated {code}")
                else:
                    logger.info(f"ℹ️  {code} already exists and is active")
                existing.append(code)
            else:
                # Create new
                if code == "FREE_ACCESS":
                    DiscountService.create_discount_code(
                        db,
                        code=code,
                        discount_percent=0,
                        is_free_generation=False,
                        free_generations_count=None,
                        max_uses=None
                    )
                else:
                    DiscountService.create_discount_code(
                        db,
                        code=code,
                        discount_percent=code_data["discount_percent"],
                        max_uses=None
                    )
                logger.info(f"✅ Created {code} ({code_data['discount_percent']}%)")
                created.append(code)
        
        # Show all discount codes
        all_codes = db.query(DiscountCode).all()
        logger.info(f"\n📋 Всего промокодов в базе: {len(all_codes)}")
        for code in all_codes:
            uses_info = f"{code.current_uses}/{code.max_uses}" if code.max_uses else "Без ограничений"
            logger.info(
                f"  • {code.code}: {code.discount_percent}% "
                f"(использований: {uses_info}, активен: {code.is_active})"
            )
        
        logger.info(f"\n✅ Создано: {len(created)}, уже существовало: {len(existing)}")
        
    except Exception as e:
        logger.error(f"Error creating discount codes: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_promo_codes()

