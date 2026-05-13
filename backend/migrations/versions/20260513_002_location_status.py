"""Add location and online status fields to users table.

Revision ID: 20260513_002_location_status
Revises: 20260513_001_password_reset
Create Date: 2026-05-13

"""
from alembic import op
import sqlalchemy as sa


revision = '20260513_002_location_status'
down_revision = '20260513_001_password_reset'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('is_online', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    # Create indexes for fast geospatial queries
    op.create_index('ix_users_latitude', 'users', ['latitude'], postgresql_using='btree')
    op.create_index('ix_users_longitude', 'users', ['longitude'], postgresql_using='btree')
    op.create_index('ix_users_is_online', 'users', ['is_online'], postgresql_using='btree')


def downgrade():
    op.drop_index('ix_users_is_online', table_name='users')
    op.drop_index('ix_users_longitude', table_name='users')
    op.drop_index('ix_users_latitude', table_name='users')
    op.drop_column('users', 'last_seen_at')
    op.drop_column('users', 'is_online')
    op.drop_column('users', 'longitude')
    op.drop_column('users', 'latitude')
