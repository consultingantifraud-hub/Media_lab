#!/usr/bin/env python3
"""Script to test discount codes."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.services.discount import DiscountService
from loguru import logger


def list_discount_codes():
    """List all discount codes."""
    db = SessionLocal()
    try:
        from app.db.models import DiscountCode
        
        codes = db.query(DiscountCode).all()
        
        print("\n" + "="*80)
        print("📋 СПИСОК ПРОМОКОДОВ")
        print("="*80)
        
        if not codes:
            print("Промокоды не найдены.")
        else:
            for code in codes:
                print(f"\n🎟️  Промокод: {code.code}")
                print(f"   Скидка: {code.discount_percent}%")
                print(f"   Активен: {'Да' if code.is_active else 'Нет'}")
                print(f"   Использований: {code.current_uses}" + (f" / {code.max_uses}" if code.max_uses else " / без ограничений"))
                if code.valid_from:
                    print(f"   Действителен с: {code.valid_from.strftime('%d.%m.%Y %H:%M')}")
                if code.valid_until:
                    print(f"   Действителен до: {code.valid_until.strftime('%d.%m.%Y %H:%M')}")
                if code.is_free_generation:
                    print(f"   Бесплатные генерации: {code.free_generations_count or 'неограниченно'}")
        
        print("\n" + "="*80 + "\n")
        
    finally:
        db.close()


def create_test_discount(code: str, percent: int, max_uses: int = None):
    """Create a test discount code."""
    db = SessionLocal()
    try:
        discount = DiscountService.create_discount_code(
            db,
            code=code,
            discount_percent=percent,
            max_uses=max_uses
        )
        
        print("\n" + "="*80)
        print("✅ ПРОМОКОД СОЗДАН")
        print("="*80)
        print(f"🎟️  Код: {discount.code}")
        print(f"💰 Скидка: {discount.discount_percent}%")
        print(f"📊 Макс. использований: {max_uses or 'без ограничений'}")
        print("="*80 + "\n")
        
        return discount
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
        logger.error(f"Error creating discount code: {e}", exc_info=True)
        return None
    finally:
        db.close()


def test_discount_code(code: str, telegram_id: int):
    """Test discount code validation."""
    db = SessionLocal()
    try:
        from app.services.billing import BillingService
        
        user, _ = BillingService.get_or_create_user(db, telegram_id)
        
        is_valid, discount, error_msg = DiscountService.validate_discount_code(
            db, code, user.id
        )
        
        print("\n" + "="*80)
        print("🧪 ТЕСТ ПРОМОКОДА")
        print("="*80)
        print(f"🎟️  Промокод: {code}")
        print(f"👤 Пользователь: {telegram_id} (ID: {user.id})")
        
        if is_valid and discount:
            print(f"✅ Промокод валиден!")
            print(f"💰 Скидка: {discount.discount_percent}%")
            print(f"📊 Использований: {discount.current_uses}" + (f" / {discount.max_uses}" if discount.max_uses else " / без ограничений"))
        else:
            print(f"❌ Промокод невалиден: {error_msg}")
        
        print("="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n" + "="*80)
        print("🎟️  СКРИПТ ТЕСТИРОВАНИЯ СКИДОК")
        print("="*80)
        print("\nИспользование:")
        print("  python scripts/test_discounts.py list")
        print("  python scripts/test_discounts.py create <code> <percent> [max_uses]")
        print("  python scripts/test_discounts.py test <code> <telegram_id>")
        print("\nПримеры:")
        print("  python scripts/test_discounts.py list")
        print("  python scripts/test_discounts.py create TEST20 20 100")
        print("  python scripts/test_discounts.py test TEST20 8097935741")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_discount_codes()
    elif command == "create":
        if len(sys.argv) < 4:
            print("❌ Ошибка: Укажите код и процент скидки")
            print("Пример: python scripts/test_discounts.py create TEST20 20")
            sys.exit(1)
        code = sys.argv[2].upper()
        percent = int(sys.argv[3])
        max_uses = int(sys.argv[4]) if len(sys.argv) > 4 else None
        create_test_discount(code, percent, max_uses)
    elif command == "test":
        if len(sys.argv) < 4:
            print("❌ Ошибка: Укажите код и telegram_id")
            print("Пример: python scripts/test_discounts.py test TEST20 8097935741")
            sys.exit(1)
        code = sys.argv[2].upper()
        telegram_id = int(sys.argv[3])
        test_discount_code(code, telegram_id)
    else:
        print(f"❌ Неизвестная команда: {command}")
        sys.exit(1)





