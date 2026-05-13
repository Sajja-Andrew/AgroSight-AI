"""
Smart Crop AI - LocalStorage to Database Migration Script
Usage: python migrate_localstorage.py path/to/localstorage_export.json
"""

import sys
import os
import json

# Ensure backend imports work
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from database import db, create_user, save_detection, save_message, save_activity
from model.app import app


def migrate_users(users_data):
    """Import users from localStorage export."""
    created = 0
    skipped = 0
    for u in users_data:
        try:
            user, err = create_user(
                username=u.get('username'),
                email=u.get('email'),
                password=u.get('password', 'changeme123'),
                phone=u.get('phone'),
                role=u.get('role', 'farmer'),
                location=u.get('location'),
                profile_picture=u.get('profilePicture'),
            )
            if user:
                created += 1
                print(f"  Created user: {user.username} (id={user.id})")
            else:
                skipped += 1
                print(f"  Skipped user: {u.get('username')} â€” {err}")
        except Exception as e:
            skipped += 1
            print(f"  Error creating user {u.get('username')}: {e}")
    return created, skipped


def migrate_detections(detections_data, user_id_map):
    """Import detection history."""
    created = 0
    skipped = 0
    for d in detections_data:
        try:
            # Map old localStorage user id to new DB id
            # In the old system, detections were per-browser, not per-user on server.
            # We accept a user_id from the detection record if present, else skip.
            uid = d.get('user_id')
            if not uid and user_id_map:
                # Try to infer from the single-user system
                uid = list(user_id_map.values())[0] if user_id_map else None
            if not uid:
                skipped += 1
                continue

            save_detection(
                user_id=uid,
                disease=d.get('disease'),
                confidence=d.get('confidence'),
                severity=d.get('severity'),
                image_id=d.get('img'),  # may be base64; storage handled separately
                caption=d.get('caption'),
            )
            created += 1
        except Exception as e:
            skipped += 1
            print(f"  Error saving detection: {e}")
    return created, skipped


def migrate_messages(messages_data, user_id_map):
    """Import conversation messages."""
    created = 0
    skipped = 0
    for conv_id, msgs in messages_data.items():
        parts = conv_id.split('_')
        if len(parts) != 2:
            continue
        for m in msgs:
            try:
                sender_id = int(m.get('sender_id', parts[0]))
                receiver_id = int(m.get('receiver_id', parts[1]))
                save_message(
                    conversation_id=conv_id,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    text=m.get('text', ''),
                    type=m.get('type', 'text'),
                    media_url=m.get('image') or m.get('audio'),
                )
                created += 1
            except Exception as e:
                skipped += 1
                print(f"  Error saving message: {e}")
    return created, skipped


def migrate_activities(activities_data, user_id_map):
    """Import activity logs."""
    created = 0
    skipped = 0
    for a in activities_data:
        try:
            uid = a.get('user_id')
            if not uid and user_id_map:
                uid = list(user_id_map.values())[0] if user_id_map else None
            if not uid:
                skipped += 1
                continue
            save_activity(
                user_id=uid,
                type=a.get('type', 'login'),
                text=a.get('text', 'Activity'),
            )
            created += 1
        except Exception as e:
            skipped += 1
            print(f"  Error saving activity: {e}")
    return created, skipped


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_localstorage.py path/to/export.json")
        print("")
        print("Export format (JSON object with keys like AgrosightAI_users, sc_detections, etc.):")
        print("  {")
        print("    \"AgrosightAI_users\": [ ... ],")
        print("    \"sc_detections\": [ ... ],")
        print("    \"sc_conversations\": { ... },")
        print("    \"sc_activity\": [ ... ]")
        print("  }")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    with app.app_context():
        db.create_all()

        print("\n" + "=" * 50)
        print("Smart Crop AI - LocalStorage Migration")
        print("=" * 50)

        # Users
        users = data.get('AgrosightAI_users', [])
        print(f"\n[Users] Found {len(users)} users to import...")
        u_created, u_skipped = migrate_users(users)
        print(f"  Done: {u_created} created, {u_skipped} skipped.")

        # Build old_id -> new_id map from database
        from database import User
        user_id_map = {}
        for u in users:
            old_id = u.get('id')
            db_user = User.query.filter_by(email=u.get('email')).first()
            if db_user and old_id is not None:
                user_id_map[str(old_id)] = db_user.id

        # Detections
        detections = data.get('sc_detections', [])
        print(f"\n[Detections] Found {len(detections)} detections to import...")
        d_created, d_skipped = migrate_detections(detections, user_id_map)
        print(f"  Done: {d_created} created, {d_skipped} skipped.")

        # Messages
        conversations = data.get('sc_conversations', {})
        msg_count = sum(len(v) for v in conversations.values())
        print(f"\n[Messages] Found {msg_count} messages in {len(conversations)} conversations to import...")
        m_created, m_skipped = migrate_messages(conversations, user_id_map)
        print(f"  Done: {m_created} created, {m_skipped} skipped.")

        # Activity
        activities = data.get('sc_activity', [])
        print(f"\n[Activity] Found {len(activities)} activities to import...")
        a_created, a_skipped = migrate_activities(activities, user_id_map)
        print(f"  Done: {a_created} created, {a_skipped} skipped.")

        print("\n" + "=" * 50)
        print("Migration complete!")
        print("=" * 50 + "\n")


if __name__ == '__main__':
    main()
