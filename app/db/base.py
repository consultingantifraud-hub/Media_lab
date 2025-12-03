"""Database base configuration."""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger
import os

# Database URL from environment
# Если DATABASE_URL не установлен, используем путь в /app
# Для воркеров с network_mode: host может потребоваться явный путь к файлу в volume
default_db_path = "/app/media_lab.db"
default_db_url = f"sqlite:///{default_db_path}"
DATABASE_URL = os.getenv("DATABASE_URL", default_db_url)

# Логируем используемый путь для диагностики
logger.info(f"Database URL: {DATABASE_URL}")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    # SQLite specific configuration with optimizations
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0,  # Timeout for database locks (30 seconds)
        },
        echo=False,
        pool_pre_ping=True,  # Verify connections before using
    )
    
    # Enable WAL (Write-Ahead Logging) mode for better concurrency
    # This allows multiple readers and a single writer simultaneously
    def _enable_wal(dbapi_conn, connection_record):
        """Enable WAL mode for SQLite."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL, still safe
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        logger.debug("SQLite WAL mode enabled")
    
    from sqlalchemy import event
    event.listen(engine, "connect", _enable_wal)
    
    logger.info("SQLite engine configured with WAL mode and timeout optimizations")
else:
    # PostgreSQL/MySQL configuration
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,  # Connection pool size (увеличено для поддержки 100+ пользователей)
        max_overflow=30,  # Additional connections when pool is exhausted (увеличено для поддержки 100+ пользователей)
        echo=False,
    )
    logger.info(f"PostgreSQL/MySQL engine configured with connection pooling")

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database (create tables)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")




