#!/usr/bin/env python3
"""Test AI assistant questions export."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import AiAssistantQuestion, User
from sqlalchemy import desc

if __name__ == "__main__":
    db = SessionLocal()
    try:
        # Check total count
        total_count = db.query(AiAssistantQuestion).count()
        print(f"Total questions in DB: {total_count}")
        
        if total_count == 0:
            print("❌ No questions found in database!")
            print("This means questions are not being logged.")
        else:
            print(f"✅ Found {total_count} questions")
            
            # Test the exact query used in export
            print("\nTesting export query...")
            ai_questions = db.query(
                AiAssistantQuestion,
                User.telegram_id,
                User.username,
                User.first_name
            ).join(
                User, AiAssistantQuestion.user_id == User.id
            ).order_by(
                desc(AiAssistantQuestion.created_at)
            ).all()
            
            print(f"Query returned {len(ai_questions)} rows")
            
            if len(ai_questions) > 0:
                print("\nFirst 3 questions:")
                for i, (q, tg_id, username, first_name) in enumerate(ai_questions[:3], 1):
                    print(f"\n{i}. ID: {q.id}")
                    print(f"   User ID: {q.user_id}, Telegram ID: {tg_id}")
                    print(f"   Username: {username}, First name: {first_name}")
                    print(f"   Question: {q.question[:50] if q.question else 'None'}...")
                    print(f"   Answer: {q.answer[:50] if q.answer else 'None'}...")
                    print(f"   Error: {q.error[:50] if q.error else 'None'}...")
                    print(f"   Created: {q.created_at}")
            else:
                print("❌ Query returned 0 rows!")
                print("\nChecking if there are questions without users...")
                questions_without_users = db.query(AiAssistantQuestion).filter(
                    ~AiAssistantQuestion.user_id.in_(
                        db.query(User.id)
                    )
                ).count()
                print(f"Questions without matching users: {questions_without_users}")
                
                # Check all questions
                all_questions = db.query(AiAssistantQuestion).all()
                print(f"\nAll questions (without join): {len(all_questions)}")
                for q in all_questions[:3]:
                    user_exists = db.query(User).filter(User.id == q.user_id).first() is not None
                    print(f"  Question ID {q.id}, User ID {q.user_id}, User exists: {user_exists}")
    finally:
        db.close()




