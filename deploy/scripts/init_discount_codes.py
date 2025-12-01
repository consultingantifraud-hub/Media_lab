#!/usr/bin/env python3
"""Script to initialize default discount codes."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal, init_db
from app.services.discount import init_default_discount_codes

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    
    print("Creating default discount codes...")
    db = SessionLocal()
    try:
        init_default_discount_codes(db)
        print("✅ Default discount codes created successfully!")
        print("\nCreated codes:")
        print("  - WELCOME10 (10% discount)")
        print("  - SAVE20 (20% discount)")
        print("  - BONUS30 (30% discount)")
        print("  - MEGA50 (50% discount)")
        print("  - FREE_ACCESS (unlimited free operations)")
    finally:
        db.close()

