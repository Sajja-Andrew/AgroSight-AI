"""Add password reset token fields to users table.

Revision ID: 20260513_001_password_reset
Revises: 20260512_123000
Create Date: 2026-05-13

"""
from alembic import op
import sqlalchemy as sa


revision = '20260513_001_password_reset'
down_revision = '20260512_123000'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('password_reset_token', sa.String(length=256), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'password_reset_expires')
    op.drop_column('users', 'password_reset_token')