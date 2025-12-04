#!/usr/bin/env python3
"""Test AI assistant question logging."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal, engine
from app.db.models import AiAssistantQuestion, User, Base
from sqlalchemy import inspect

if __name__ == "__main__":
    # Check if table exists
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables in database: {tables}")
    
    if "ai_assistant_questions" in tables:
        print("✅ Table 'ai_assistant_questions' exists")
        
        # Check table structure
        columns = inspector.get_columns("ai_assistant_questions")
        print(f"\nTable columns:")
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
        
        # Try to create a test record
        db = SessionLocal()
        try:
            # Get first user
            user = db.query(User).first()
            if user:
                print(f"\nTesting with user_id={user.id}, telegram_id={user.telegram_id}")
                
                # Try to create a test question
                test_question = AiAssistantQuestion(
                    user_id=user.id,
                    question="Test question",
                    answer="Test answer"
                )
                db.add(test_question)
                db.commit()
                print(f"✅ Test question created with ID: {test_question.id}")
                
                # Delete test question
                db.delete(test_question)
                db.commit()
                print("✅ Test question deleted")
            else:
                print("❌ No users found in database")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
        finally:
            db.close()
    else:
        print("❌ Table 'ai_assistant_questions' does NOT exist!")
        print("Migration needs to be applied!")




