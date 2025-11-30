"""Check if operations table exists."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from sqlalchemy import inspect

db = SessionLocal()
try:
    inspector = inspect(db.bind)
    tables = inspector.get_table_names()
    print("Tables in database:", tables)
    
    if "operations" in tables:
        print("✓ operations table exists")
        columns = [col["name"] for col in inspector.get_columns("operations")]
        print("Columns:", columns)
    else:
        print("✗ operations table NOT found")
        print("Creating tables...")
        from app.db.base import Base, engine
        from app.db import models  # Import models to register them
        Base.metadata.create_all(bind=engine)
        print("Tables created. Checking again...")
        tables = inspector.get_table_names()
        if "operations" in tables:
            print("✓ operations table created successfully")
        else:
            print("✗ Still not found")
finally:
    db.close()

