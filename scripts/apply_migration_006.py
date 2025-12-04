#!/usr/bin/env python3
"""Apply migration 006: Create ai_assistant_questions table."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.migrations.apply_all_migrations import apply_migration

if __name__ == "__main__":
    migration_file = Path(__file__).parent.parent / "app" / "db" / "migrations" / "006_create_ai_assistant_questions.sql"
    success = apply_migration(migration_file, "Create ai_assistant_questions table")
    if success:
        print("Migration 006 applied successfully")
    else:
        print(f"Error applying migration: Migration failed for {migration_file}")
        sys.exit(1)




