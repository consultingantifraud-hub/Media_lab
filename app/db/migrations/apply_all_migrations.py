"""Apply all database migrations."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import models to ensure they are registered with Base
from app.db import models  # noqa: F401

from sqlalchemy import text, inspect
from app.db.base import engine, SessionLocal
from loguru import logger


def apply_migration(migration_file: Path, description: str) -> bool:
    """Apply a single migration file."""
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    # Read migration SQL
    with open(migration_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        
        # For CREATE TABLE statements, handle them specially
        if "CREATE TABLE" in sql_content.upper():
            # Find CREATE TABLE start (case-insensitive)
            import re
            match = re.search(r'CREATE\s+TABLE', sql_content, re.IGNORECASE)
            if match:
                start_pos = match.start()
                # Find the end of CREATE TABLE (first ; after CREATE TABLE)
                remaining = sql_content[start_pos:]
                end_pos = remaining.find(";")
                if end_pos >= 0:
                    create_table_sql = remaining[:end_pos + 1]
                    # Remove comments from CREATE TABLE line by line
                    lines = []
                    for line in create_table_sql.split("\n"):
                        # Remove full-line comments
                        if line.strip().startswith("--"):
                            continue
                        # Remove inline comments
                        if "--" in line:
                            comment_pos = line.find("--")
                            if comment_pos >= 0:
                                before_comment = line[:comment_pos]
                                quote_count = before_comment.count("'") + before_comment.count('"')
                                if quote_count % 2 == 0:
                                    line = line[:comment_pos].strip()
                        line = line.strip()
                        if line and not line.startswith("#"):
                            lines.append(line)
                    create_table_sql = " ".join(lines)
                    # Clean up any double spaces
                    create_table_sql = re.sub(r'\s+', ' ', create_table_sql)
                    
                    # Check if table already exists
                    table_name_match = None
                    import re
                    match = re.search(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)', create_table_sql, re.IGNORECASE)
                    if match:
                        table_name = match.group(1)
                        tables = inspector.get_table_names()
                        if table_name.lower() in [t.lower() for t in tables]:
                            logger.info(f"Table {table_name} already exists, skipping CREATE TABLE")
                            db.commit()
                            logger.success(f"✓ Migration applied: {description}")
                            return True
                    
                    # Execute CREATE TABLE
                    try:
                        db.execute(text(create_table_sql))
                        logger.info(f"Executed CREATE TABLE")
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" in error_str:
                            logger.info(f"Table already exists, skipping")
                        else:
                            raise
                    
                    # Handle indexes separately
                    remaining_sql = remaining[end_pos + 1:]
                    for line in remaining_sql.split("\n"):
                        line = line.strip()
                        if line.upper().startswith("CREATE INDEX"):
                            if "--" in line:
                                comment_pos = line.find("--")
                                if comment_pos >= 0:
                                    line = line[:comment_pos].strip()
                            if line:
                                try:
                                    db.execute(text(line))
                                    logger.info(f"Executed index: {line[:60]}...")
                                except Exception as e:
                                    error_str = str(e).lower()
                                    if "already exists" in error_str or "duplicate" in error_str:
                                        logger.info(f"Index already exists, skipping")
                                    else:
                                        raise
        
        else:
            # For ALTER TABLE and other statements, process normally
            lines = []
            for line in sql_content.split("\n"):
                # Remove inline comments
                if "--" in line:
                    comment_pos = line.find("--")
                    if comment_pos >= 0:
                        before_comment = line[:comment_pos]
                        quote_count = before_comment.count("'") + before_comment.count('"')
                        if quote_count % 2 == 0:
                            line = line[:comment_pos].strip()
                
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # Skip PostgreSQL-specific statements if using SQLite
                if "IF NOT EXISTS" in line and "sqlite" in str(engine.url).lower():
                    continue
                if "COMMENT ON" in line:
                    continue
                
                lines.append(line)
            
            # Join all lines and split by semicolon to get statements
            full_sql = " ".join(lines)
            statements = [s.strip() for s in full_sql.split(";") if s.strip()]
            
            # Execute statements one by one
            for statement in statements:
                if statement:
                    try:
                        db.execute(text(statement))
                        logger.info(f"Executed: {statement[:60]}...")
                    except Exception as e:
                        # Check if error is about column/table already existing
                        error_str = str(e).lower()
                        if "duplicate column" in error_str or "already exists" in error_str:
                            logger.info(f"Column/table already exists, skipping: {statement[:60]}...")
                        else:
                            raise
        
        db.commit()
        logger.success(f"✓ Migration applied: {description}")
        return True
        
    except Exception as e:
        db.rollback()
        error_str = str(e).lower()
        if "duplicate column" in error_str or "already exists" in error_str:
            logger.info(f"Migration already applied (skipping): {description}")
            return True
        logger.error(f"Migration failed: {description}, error: {e}", exc_info=True)
        return False
    finally:
        db.close()


def main():
    """Apply all migrations in order."""
    migrations_dir = Path(__file__).parent
    
    migrations = [
        ("002_add_user_profile_fields.sql", "Add user profile fields"),
        ("003_add_operation_details.sql", "Add operation details"),
        ("004_create_user_statistics.sql", "Create user statistics table"),
    ]
    
    logger.info("Starting database migrations...")
    
    all_success = True
    for migration_file, description in migrations:
        migration_path = migrations_dir / migration_file
        if migration_path.exists():
            success = apply_migration(migration_path, description)
            if not success:
                all_success = False
        else:
            logger.warning(f"Migration file not found: {migration_file}")
    
    if all_success:
        logger.success("All migrations applied successfully!")
    else:
        logger.error("Some migrations failed!")
    
    return all_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

