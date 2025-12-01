"""Initial billing tables

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('free_operations_left', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    # Create balances table
    op.create_table(
        'balances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('balance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_balances_id'), 'balances', ['id'], unique=False)
    op.create_index(op.f('ix_balances_user_id'), 'balances', ['user_id'], unique=True)

    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('yookassa_payment_id', sa.String(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'SUCCEEDED', 'CANCELED', 'FAILED', 'REFUNDED', name='paymentstatus'), nullable=False, server_default='PENDING'),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('yookassa_payment_id')
    )
    op.create_index(op.f('ix_payments_id'), 'payments', ['id'], unique=False)
    op.create_index(op.f('ix_payments_user_id'), 'payments', ['user_id'], unique=False)
    op.create_index(op.f('ix_payments_yookassa_payment_id'), 'payments', ['yookassa_payment_id'], unique=True)

    # Create operations table
    op.create_table(
        'operations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('FREE', 'CHARGED', 'REFUNDED', 'FAILED', name='operationstatus'), nullable=False, server_default='CHARGED'),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_operations_id'), 'operations', ['id'], unique=False)
    op.create_index(op.f('ix_operations_user_id'), 'operations', ['user_id'], unique=False)
    op.create_index(op.f('ix_operations_task_id'), 'operations', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_operations_task_id'), table_name='operations')
    op.drop_index(op.f('ix_operations_user_id'), table_name='operations')
    op.drop_index(op.f('ix_operations_id'), table_name='operations')
    op.drop_table('operations')
    
    op.drop_index(op.f('ix_payments_yookassa_payment_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_user_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_id'), table_name='payments')
    op.drop_table('payments')
    
    op.drop_index(op.f('ix_balances_user_id'), table_name='balances')
    op.drop_index(op.f('ix_balances_id'), table_name='balances')
    op.drop_table('balances')
    
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    
    # Drop enums
    sa.Enum(name='paymentstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='operationstatus').drop(op.get_bind(), checkfirst=True)




