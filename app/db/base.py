"""Database base configuration."""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
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

# CRITICAL: Engine-level safeguard to prevent is_premium=None in UPDATE users
@event.listens_for(engine, "before_cursor_execute", retval=True)
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    Абсолютный предохранитель от is_premium=None для UPDATE users.
    Работает на уровне engine: любое UPDATE users с is_premium=None — принудительно меняем на False.
    """
    try:
        # statement может быть str или bytes
        stmt = statement.decode() if isinstance(statement, (bytes, bytearray)) else statement
        
        # Интересует только UPDATE users с is_premium
        if "UPDATE users SET" in stmt and "users" in stmt and "is_premium" in stmt:
            # В логах видно, что параметры — dict с ключами 'is_premium' и 'users_id'
            if isinstance(parameters, dict) and "is_premium" in parameters:
                if parameters.get("is_premium") is None:
                    logger.warning(
                        "ENGINE PATCH: users.id=%s had is_premium=None before UPDATE, forcing False; stmt=%s",
                        parameters.get("users_id"),
                        stmt[:200] if len(stmt) > 200 else stmt,
                    )
                    parameters["is_premium"] = False
            # Также обрабатываем случаи, когда parameters - это список (для executemany)
            elif isinstance(parameters, (list, tuple)):
                for param_dict in parameters:
                    if isinstance(param_dict, dict) and "is_premium" in param_dict:
                        if param_dict.get("is_premium") is None:
                            logger.warning(
                                "ENGINE PATCH: users.id=%s had is_premium=None before UPDATE (executemany), forcing False",
                                param_dict.get("users_id"),
                            )
                            param_dict["is_premium"] = False
    except Exception as e:
        logger.error("ENGINE PATCH ERROR in before_cursor_execute: %r", e)
    return statement, parameters

logger.info("Engine before_cursor_execute hook for User.is_premium normalization registered")

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Global safeguard: ensure User.is_premium is never None before flush
@event.listens_for(SessionLocal, "before_flush", propagate=True)
def _normalize_user_is_premium(session, flush_context, instances):
    """Normalize User.is_premium (None -> False) before any flush to database."""
    try:
        from app.db.models import User  # local import to avoid circular
    except Exception as e:
        logger.debug(f"Could not import User in before_flush: {e}")
        return
    
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, User):
            if obj.is_premium is None:
                user_id = getattr(obj, "id", None) or getattr(obj, "telegram_id", "unknown") if hasattr(obj, "telegram_id") else "unknown"
                logger.warning(
                    "User %s: is_premium=None detected in before_flush, forcing False",
                    user_id
                )
                obj.is_premium = False

logger.info("Session before_flush hook for User.is_premium normalization registered")


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




