#!/usr/bin/env python3
"""Check AI assistant questions in database."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import AiAssistantQuestion, User

if __name__ == "__main__":
    db = SessionLocal()
    try:
        count = db.query(AiAssistantQuestion).count()
        print(f"Total questions in DB: {count}")
        
        if count > 0:
            questions = db.query(AiAssistantQuestion).limit(5).all()
            print("\nSample questions:")
            for q in questions:
                user = db.query(User).filter(User.id == q.user_id).first()
                print(f"ID: {q.id}, User ID: {q.user_id}, Telegram ID: {user.telegram_id if user else 'N/A'}, Question: {q.question[:50] if q.question else 'N/A'}...")
        else:
            print("No questions found in database")
    finally:
        db.close()




