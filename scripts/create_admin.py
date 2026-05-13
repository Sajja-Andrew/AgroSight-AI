#!/usr/bin/env python3
"""
AgroSight AI - Admin User Creation Script
Creates a default admin user or resets an existing admin's password.
Usage: python scripts/create_admin.py [--username admin --email admin@agrosight.ai --password adminpass123]
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app, db
from database import User, create_admin
from werkzeug.security import generate_password_hash


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Create or reset AgroSight AI admin user')
    parser.add_argument('--username', default='admin', help='Admin username (default: admin)')
    parser.add_argument('--email', default='admin@agrosight.ai', help='Admin email (default: admin@agrosight.ai)')
    parser.add_argument('--password', default='adminpass123', help='Admin password (default: adminpass123)')
    args = parser.parse_args()

    with app.app_context():
        # Create tables if needed
        db.create_all()

        # Check if admin exists
        existing = User.query.filter_by(role='admin').first()
        if existing:
            # Reset password
            existing.set_password(args.password)
            existing.password_reset_required = False
            db.session.commit()
            print(f"Admin password reset for user: {existing.username} ({existing.email})")
            print(f"New password: {args.password}")
            return

        # Create new admin
        admin, err = create_admin(args.username, args.email, args.password)
        if admin:
            admin.password_reset_required = False
            db.session.commit()
            print(f"Admin user created successfully!")
            print(f"  Username: {args.username}")
            print(f"  Email:    {args.email}")
            print(f"  Password: {args.password}")
        else:
            print(f"Error creating admin: {err}")


if __name__ == '__main__':
    main()