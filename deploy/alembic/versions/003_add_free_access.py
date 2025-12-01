"""Add free access field to users

Revision ID: 003_free_access
Revises: 002_discount_codes
Create Date: 2025-01-20 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_free_access'
down_revision = '002_discount_codes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add has_free_access column to users table
    op.add_column('users', sa.Column('has_free_access', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'has_free_access')



