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
    # SQLite specific configuration
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    # PostgreSQL/MySQL configuration
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )

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



