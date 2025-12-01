"""Add discount codes tables

Revision ID: 002_discount_codes
Revises: 001_initial
Create Date: 2025-01-20 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_discount_codes'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create discount_codes table
    op.create_table(
        'discount_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_free_generation', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('free_generations_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_discount_codes_id'), 'discount_codes', ['id'], unique=False)
    op.create_index(op.f('ix_discount_codes_code'), 'discount_codes', ['code'], unique=True)

    # Create user_discount_codes table
    op.create_table(
        'user_discount_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('discount_code_id', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('operation_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['discount_code_id'], ['discount_codes.id'], ),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
        sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_discount_codes_id'), 'user_discount_codes', ['id'], unique=False)
    op.create_index(op.f('ix_user_discount_codes_user_id'), 'user_discount_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_discount_codes_discount_code_id'), 'user_discount_codes', ['discount_code_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_discount_codes_discount_code_id'), table_name='user_discount_codes')
    op.drop_index(op.f('ix_user_discount_codes_user_id'), table_name='user_discount_codes')
    op.drop_index(op.f('ix_user_discount_codes_id'), table_name='user_discount_codes')
    op.drop_table('user_discount_codes')
    
    op.drop_index(op.f('ix_discount_codes_code'), table_name='discount_codes')
    op.drop_index(op.f('ix_discount_codes_id'), table_name='discount_codes')
    op.drop_table('discount_codes')



