"""Add location and online status fields to users table.

Revision ID: 20260513_002_user_location
Revises: 20260513_001_password_reset
Create Date: 2026-05-13

"""
from alembic import op
import sqlalchemy as sa


revision = '20260513_002_user_location'
down_revision = '20260513_001_password_reset'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('is_online', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'last_seen_at')
    op.drop_column('users', 'is_online')
    op.drop_column('users', 'longitude')
    op.drop_column('users', 'latitude')