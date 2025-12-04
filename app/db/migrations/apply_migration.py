"""Apply database migration script."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import models to ensure they are registered with Base
from app.db import models  # noqa: F401

from sqlalchemy import text, inspect
from app.db.base import engine, SessionLocal
from loguru import logger


def apply_migration():
    """Apply migration to add discount fields to operations table."""
    migration_file = Path(__file__).parent / "001_add_discount_fields_to_operations.sql"
    
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    # Read migration SQL
    with open(migration_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    # Filter SQL statements (remove comments and empty lines)
    statements = []
    for line in sql_content.split("\n"):
        line = line.strip()
        if line and not line.startswith("--") and not line.startswith("#"):
            # Skip PostgreSQL-specific statements if using SQLite
            if "IF NOT EXISTS" in line and "sqlite" in str(engine.url).lower():
                continue
            if "COMMENT ON" in line:
                continue
            statements.append(line)
    
    # Join statements
    sql = "\n".join(statements)
    
    db = SessionLocal()
    try:
        # Check if table exists
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if "operations" not in tables:
            logger.error("Table 'operations' does not exist. Please initialize database first.")
            logger.info("Run: from app.db.base import init_db; init_db()")
            return False
        
        # Check if columns already exist
        columns = [col["name"] for col in inspector.get_columns("operations")]
        logger.info(f"Current columns in operations table: {columns}")
        
        if "original_price" in columns and "discount_percent" in columns:
            logger.info("Migration already applied: discount fields exist in operations table")
            return True
        
        # Apply migration
        logger.info("Applying migration: adding discount fields to operations table")
        
        # For SQLite, we need to execute ALTER TABLE statements separately
        if "sqlite" in str(engine.url).lower():
            if "original_price" not in columns:
                logger.info("Adding column: original_price")
                db.execute(text("ALTER TABLE operations ADD COLUMN original_price INTEGER NULL"))
                logger.info("✓ Added column: original_price")
            
            if "discount_percent" not in columns:
                logger.info("Adding column: discount_percent")
                db.execute(text("ALTER TABLE operations ADD COLUMN discount_percent INTEGER NULL"))
                logger.info("✓ Added column: discount_percent")
        else:
            # For PostgreSQL/MySQL, execute SQL directly
            logger.info("Executing migration SQL for PostgreSQL/MySQL")
            db.execute(text(sql))
            logger.info("Applied migration SQL")
        
        db.commit()
        logger.success("Migration applied successfully")
        
        # Verify columns were added
        inspector = inspect(engine)
        columns_after = [col["name"] for col in inspector.get_columns("operations")]
        if "original_price" in columns_after and "discount_percent" in columns_after:
            logger.success("✓ Verification: Both columns exist in operations table")
            return True
        else:
            logger.warning("Migration completed but verification failed")
            return False
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)

