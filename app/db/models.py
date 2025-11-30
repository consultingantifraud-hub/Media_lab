"""Database models for Media Lab Bot."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import sqlalchemy as sa

from app.db.base import Base


class PaymentStatus(str, enum.Enum):
    """Payment status enum."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    FAILED = "failed"
    REFUNDED = "refunded"


class OperationStatus(str, enum.Enum):
    """Operation status enum."""
    FREE = "free"
    PENDING = "pending"  # Operation created but not yet charged (waiting for success)
    CHARGED = "charged"  # Operation completed successfully and charged
    REFUNDED = "refunded"
    FAILED = "failed"  # Operation failed, not charged


class User(Base):
    """User model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    free_operations_left = Column(Integer, default=0, nullable=False)
    has_free_access = Column(sa.Boolean, default=False, nullable=False)  # Бесплатный доступ без ограничений
    
    # Telegram profile information
    username = Column(String, nullable=True, index=True)  # Telegram username (without @)
    first_name = Column(String, nullable=True)  # First name from Telegram
    last_name = Column(String, nullable=True)  # Last name from Telegram
    language_code = Column(String, nullable=True)  # Language code (e.g., "ru", "en")
    is_premium = Column(sa.Boolean, default=False, nullable=False)  # Telegram Premium status
    last_activity_at = Column(DateTime(timezone=True), nullable=True)  # Last activity timestamp
    
    # Active discount code for operations
    operation_discount_code_id = Column(Integer, ForeignKey("discount_codes.id"), nullable=True, index=True)
    operation_discount_percent = Column(Integer, nullable=True)  # Discount percentage (10, 20, 30, etc.)

    # Relationships
    balance = relationship("Balance", back_populates="user", uselist=False)
    payments = relationship("Payment", back_populates="user")
    operations = relationship("Operation", back_populates="user")
    statistics = relationship("UserStatistics", back_populates="user", uselist=False)
    ai_assistant_questions = relationship("AiAssistantQuestion", back_populates="user")


class Balance(Base):
    """User balance model."""
    __tablename__ = "balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    balance = Column(Integer, default=0, nullable=False)  # Balance in rubles
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="balance")


class Payment(Base):
    """Payment model."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    yookassa_payment_id = Column(String, unique=True, nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount in rubles
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    raw_data = Column(JSON, nullable=True)  # Raw webhook data for debugging
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="payments")


class Operation(Base):
    """Operation model (billing record for each paid operation)."""
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String, nullable=False)  # generate, edit, merge, face_swap, retouch, upscale
    price = Column(Integer, default=0, nullable=False)  # Final price in rubles (0 for free operations, after discount if any)
    original_price = Column(Integer, nullable=True)  # Original price before discount (if discount was applied)
    discount_percent = Column(Integer, nullable=True)  # Discount percentage applied (10, 20, 30, etc.)
    status = Column(Enum(OperationStatus), default=OperationStatus.CHARGED, nullable=False)
    task_id = Column(String, nullable=True, index=True)  # Link to RQ task
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Operation details for analytics
    model = Column(String, nullable=True, index=True)  # Model used (e.g., "nano-banana-pro", "seedream", "chrono-edit")
    prompt = Column(Text, nullable=True)  # User prompt (optional, for analytics, truncated if too long)
    image_count = Column(Integer, nullable=True)  # Number of images (for merge operations)

    # Relationships
    user = relationship("User", back_populates="operations")


class DiscountCode(Base):
    """Discount code model."""
    __tablename__ = "discount_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)  # Промокод (например, "DISCOUNT10")
    discount_percent = Column(Integer, nullable=False)  # Процент скидки (10, 20, 30, 50)
    is_active = Column(sa.Boolean, default=True, nullable=False)  # Активен ли промокод
    max_uses = Column(Integer, nullable=True)  # Максимальное количество использований (None = без ограничений)
    current_uses = Column(Integer, default=0, nullable=False)  # Текущее количество использований
    valid_from = Column(DateTime(timezone=True), nullable=True)  # Дата начала действия
    valid_until = Column(DateTime(timezone=True), nullable=True)  # Дата окончания действия
    is_free_generation = Column(sa.Boolean, default=False, nullable=False)  # Промокод для бесплатных генераций
    free_generations_count = Column(Integer, nullable=True)  # Количество бесплатных генераций (если is_free_generation=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user_discounts = relationship("UserDiscountCode", back_populates="discount_code")


class UserDiscountCode(Base):
    """User discount code usage tracking."""
    __tablename__ = "user_discount_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    discount_code_id = Column(Integer, ForeignKey("discount_codes.id"), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)  # Связь с платежом (если использован при оплате)
    operation_id = Column(Integer, ForeignKey("operations.id"), nullable=True)  # Связь с операцией (если использован для бесплатной генерации)

    # Relationships
    user = relationship("User")
    discount_code = relationship("DiscountCode", back_populates="user_discounts")
    payment = relationship("Payment")
    operation = relationship("Operation")


class UserStatistics(Base):
    """Aggregated user statistics for analytics."""
    __tablename__ = "user_statistics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    total_operations = Column(Integer, default=0, nullable=False)
    total_spent = Column(Integer, default=0, nullable=False)  # Total spent in rubles
    operations_by_type = Column(JSON, nullable=True)  # JSON: {"generate": 10, "merge": 5, ...}
    models_used = Column(JSON, nullable=True)  # JSON: {"nano-banana-pro": 3, "seedream": 2, ...}
    first_operation_at = Column(DateTime(timezone=True), nullable=True)
    last_operation_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="statistics")


class AiAssistantQuestion(Base):
    """AI Assistant question log model."""
    __tablename__ = "ai_assistant_questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)  # User's question
    answer = Column(Text, nullable=True)  # AI assistant's answer (if successful)
    error = Column(Text, nullable=True)  # Error message (if failed)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    user = relationship("User")


