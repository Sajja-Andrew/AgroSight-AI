"""Alembic environment configuration for Flask-Migrate."""

import logging
from logging.config import fileConfig

from alembic import context

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# Import db and models from our database module (no heavy ML imports)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import db
from database import User, Detection, Message, Activity, Feedback, AuditLog

target_metadata = db.metadata


def get_url():
    """Read database URL from environment or fall back to local SQLite."""
    return os.environ.get("DATABASE_URL", "sqlite:///AgroSightAI.db")


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    url = get_url()
    engine = create_engine(url)

    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
