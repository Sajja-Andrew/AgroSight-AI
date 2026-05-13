#!/usr/bin/env python3
"""
Seed script: Create 6 farmers and 6 agrovets with known credentials.
Run from project root: python scripts/seed_users.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app, db
from database import User, create_user

FARMERS = [
    {"username": "farmer_james", "email": "james@agrosight.ai",    "phone": "+256701000001", "location": "Kampala, Uganda",      "password": "Farmer@123"},
    {"username": "farmer_grace", "email": "grace@agrosight.ai",    "phone": "+256701000002", "location": "Entebbe, Uganda",      "password": "Farmer@123"},
    {"username": "farmer_paul",  "email": "paul@agrosight.ai",     "phone": "+256701000003", "location": "Jinja, Uganda",         "password": "Farmer@123"},
    {"username": "farmer_maria", "email": "maria@agrosight.ai",     "phone": "+256701000004", "location": "Mbarara, Uganda",        "password": "Farmer@123"},
    {"username": "farmer_joseph","email": "joseph@agrosight.ai",   "phone": "+256701000005", "location": "Gulu, Uganda",          "password": "Farmer@123"},
    {"username": "farmer_aisha", "email": "aisha@agrosight.ai",    "phone": "+256701000006", "location": "Mbale, Uganda",         "password": "Farmer@123"},
]

AGROVETS = [
    {"username": "agrovet_daniel", "email": "daniel@agrosight.ai",  "phone": "+256702000001", "location": "Kampala, Uganda",      "password": "Agrovet@123"},
    {"username": "agrovet_sarah",  "email": "sarah@agrosight.ai",  "phone": "+256702000002", "location": "Wakiso, Uganda",       "password": "Agrovet@123"},
    {"username": "agrovet_peter",  "email": "peter@agrosight.ai",  "phone": "+256702000003", "location": "Mukono, Uganda",       "password": "Agrovet@123"},
    {"username": "agrovet_nakato", "email": "nakato@agrosight.ai", "phone": "+256702000004", "location": "Fort Portal, Uganda",  "password": "Agrovet@123"},
    {"username": "agrovet_emma",   "email": "emma@agrosight.ai",   "phone": "+256702000005", "location": "Lira, Uganda",         "password": "Agrovet@123"},
    {"username": "agrovet_ruth",  "email": "ruth@agrosight.ai",   "phone": "+256702000006", "location": "Soroti, Uganda",        "password": "Agrovet@123"},
]


def seed():
    with app.app_context():
        db.create_all()
        created = []

        for f in FARMERS:
            user, err = create_user(
                username=f["username"],
                email=f["email"],
                password=f["password"],
                phone=f["phone"],
                role="farmer",
                location=f["location"],
            )
            if user:
                user.password_reset_required = False
                db.session.commit()
                created.append(("farmer", f["username"], f["email"], f["password"]))
                print(f"  Created farmer: {f['username']}")
            else:
                print(f"  Skipped (exists): {f['username']} — {err}")

        for a in AGROVETS:
            user, err = create_user(
                username=a["username"],
                email=a["email"],
                password=a["password"],
                phone=a["phone"],
                role="agrovet",
                location=a["location"],
            )
            if user:
                user.password_reset_required = False
                db.session.commit()
                created.append(("agrovet", a["username"], a["email"], a["password"]))
                print(f"  Created agrovet: {a['username']}")
            else:
                print(f"  Skipped (exists): {a['username']} — {err}")

        print(f"\nDone. {len(created)} users created.\n")
        return created


if __name__ == "__main__":
    print("=" * 60)
    print("AgroSight AI — Seeding Users")
    print("=" * 60)
    print()
    seed()