#!/usr/bin/env python3
"""Update user profiles from recent operations/messages."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import User, Operation
from sqlalchemy import desc
from datetime import datetime, timezone
import json

def update_user_profiles():
    """Update user profiles - note that we can't get Telegram data from DB alone."""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        print(f"\nНайдено пользователей: {len(users)}")
        print("\nПользователи с пустыми полями:")
        print("="*80)
        
        empty_count = 0
        for user in users:
            has_empty = False
            empty_fields = []
            
            if not user.username:
                has_empty = True
                empty_fields.append("username")
            if not user.first_name:
                has_empty = True
                empty_fields.append("first_name")
            if not user.last_name:
                has_empty = True
                empty_fields.append("last_name")
            if not user.language_code:
                has_empty = True
                empty_fields.append("language_code")
            if user.last_activity_at is None:
                has_empty = True
                empty_fields.append("last_activity_at")
            
            if has_empty:
                empty_count += 1
                print(f"ID: {user.id}, Telegram ID: {user.telegram_id}")
                print(f"  Пустые поля: {', '.join(empty_fields)}")
                print()
        
        print(f"Всего пользователей с пустыми полями: {empty_count}")
        print("\n" + "="*80)
        print("\n⚠️  ВАЖНО:")
        print("Данные профиля (username, first_name, last_name) можно получить только")
        print("из Telegram API при обращении пользователя к боту.")
        print("\nЭти данные будут автоматически обновляться при следующем обращении")
        print("пользователя к боту, если все вызовы get_or_create_user передают")
        print("объект telegram_user.")
        print("\n" + "="*80)
        
    finally:
        db.close()


if __name__ == "__main__":
    update_user_profiles()





