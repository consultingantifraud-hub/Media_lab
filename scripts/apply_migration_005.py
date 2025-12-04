#!/usr/bin/env python3
"""Apply migration 005: Add operation discount fields to users table."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.migrations.apply_all_migrations import apply_migration

if __name__ == "__main__":
    migration_file = Path(__file__).parent.parent / "app" / "db" / "migrations" / "005_add_operation_discount_to_users.sql"
    success = apply_migration(migration_file, "Add operation discount fields to users table")
    if success:
        print("Migration 005 applied successfully")
    else:
        print("Migration 005 failed")
        sys.exit(1)
