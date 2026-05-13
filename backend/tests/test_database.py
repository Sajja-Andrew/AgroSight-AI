"""Tests for backend/database.py SQLAlchemy models and helpers."""

import pytest
import json

from database import (
    db, User, Detection, Message, Activity, Feedback,
    create_user, authenticate_user, get_user_by_id,
    save_detection, get_detections_for_user, get_detection_by_id,
    delete_detection, save_message, get_conversations_for_user,
    get_conversation_messages, mark_conversation_read, get_unread_count,
    save_activity, get_activities_for_user, save_feedback,
    get_all_users, get_user_stats, create_admin,
)


@pytest.mark.db
class TestUserModel:
    """User creation, password hashing, and auth."""

    def test_create_user(self, app):
        with app.app_context():
            user, err = create_user('alice', 'alice@example.com', 'secret123',
                                     phone='+256700000001', role='farmer', location='Jinja')
            assert user is not None
            assert err is None
            assert user.username == 'alice'
            assert user.check_password('secret123') is True
            assert user.check_password('wrong') is False
            assert user.to_dict()['role'] == 'farmer'

    def test_create_user_duplicate_email(self, app):
        with app.app_context():
            u1, _ = create_user('alice', 'alice@example.com', 'secret123')
            assert u1 is not None
            u2, err = create_user('alice2', 'alice@example.com', 'secret123')
            assert u2 is None
            assert 'already exists' in err

    def test_authenticate_user_by_email(self, app):
        with app.app_context():
            create_user('bob', 'bob@example.com', 'mypass')
            user, err = authenticate_user('bob@example.com', 'mypass')
            assert user is not None
            assert err is None
            assert user.username == 'bob'

    def test_authenticate_user_by_username(self, app):
        with app.app_context():
            create_user('carol', 'carol@example.com', 'mypass')
            user, err = authenticate_user('carol', 'mypass')
            assert user is not None
            assert err is None

    def test_authenticate_user_wrong_password(self, app):
        with app.app_context():
            create_user('dave', 'dave@example.com', 'mypass')
            user, err = authenticate_user('dave@example.com', 'wrong')
            assert user is None
            assert 'Invalid credentials' in err

    def test_user_to_dict_excludes_email_when_requested(self, app):
        with app.app_context():
            user, _ = create_user('eve', 'eve@example.com', 'mypass')
            d = user.to_dict(include_email=False)
            assert 'email' not in d


@pytest.mark.db
class TestDetectionModel:
    """Detection CRUD and serialization."""

    def test_save_detection(self, app):
        with app.app_context():
            user, _ = create_user('farmer1', 'f1@example.com', 'pass')
            det = save_detection(
                user_id=user.id,
                disease='Bean Rust',
                confidence=0.92,
                symptoms=['spots', 'yellowing'],
                recommendation=['Apply fungicide'],
            )
            assert det.id is not None
            assert det.user_id == user.id
            assert 'spots' in json.loads(det.symptoms)

    def test_get_detections_ordered(self, app):
        with app.app_context():
            user, _ = create_user('farmer2', 'f2@example.com', 'pass')
            save_detection(user_id=user.id, disease='A')
            save_detection(user_id=user.id, disease='B')
            dets = get_detections_for_user(user.id)
            assert len(dets) == 2
            assert dets[0].disease == 'B'  # descending

    def test_delete_detection(self, app):
        with app.app_context():
            user, _ = create_user('farmer3', 'f3@example.com', 'pass')
            det = save_detection(user_id=user.id, disease='Rust')
            ok = delete_detection(det.id, user.id)
            assert ok is True
            assert get_detection_by_id(det.id) is None

    def test_delete_detection_wrong_user(self, app):
        with app.app_context():
            u1, _ = create_user('a', 'a@example.com', 'pass')
            u2, _ = create_user('b', 'b@example.com', 'pass')
            det = save_detection(user_id=u1.id, disease='Rust')
            ok = delete_detection(det.id, u2.id)
            assert ok is False


@pytest.mark.db
class TestMessageModel:
    """Messaging helpers."""

    def test_save_message(self, app):
        with app.app_context():
            u1, _ = create_user('sender', 's@example.com', 'pass')
            u2, _ = create_user('receiver', 'r@example.com', 'pass')
            msg = save_message('conv-1', u1.id, u2.id, text='Hello')
            assert msg.id is not None
            assert msg.text == 'Hello'
            assert msg.read is False

    def test_get_conversations(self, app):
        with app.app_context():
            u1, _ = create_user('a', 'a@example.com', 'pass')
            u2, _ = create_user('b', 'b@example.com', 'pass')
            save_message('c1', u1.id, u2.id, text='hi')
            convs = get_conversations_for_user(u1.id)
            assert 'c1' in convs
            assert convs['c1'] == u2.id

    def test_mark_conversation_read(self, app):
        with app.app_context():
            u1, _ = create_user('a', 'a@example.com', 'pass')
            u2, _ = create_user('b', 'b@example.com', 'pass')
            save_message('c1', u1.id, u2.id, text='unread')
            assert get_unread_count(u2.id) == 1
            mark_conversation_read('c1', u2.id)
            assert get_unread_count(u2.id) == 0


@pytest.mark.db
class TestActivityAndFeedback:
    """Activity logging and feedback storage."""

    def test_save_activity(self, app):
        with app.app_context():
            u, _ = create_user('act', 'act@example.com', 'pass')
            a = save_activity(u.id, 'detection', 'Detected Rust')
            assert a.id is not None
            acts = get_activities_for_user(u.id)
            assert len(acts) == 1

    def test_save_feedback(self, app):
        with app.app_context():
            u, _ = create_user('fb', 'fb@example.com', 'pass')
            fb = save_feedback(predicted_class='A', correct_class='B',
                                confidence=0.8, image_path='img.jpg', user_id=u.id)
            assert fb.id is not None
            assert fb.correct_class == 'B'

    def test_get_user_stats(self, app):
        with app.app_context():
            u1, _ = create_user('f1', 'f1@example.com', 'pass')
            u2, _ = create_user('f2', 'f2@example.com', 'pass')
            create_admin('admin', 'adm@example.com', 'pass')
            save_detection(user_id=u1.id, disease='Rust')
            save_message('c', u1.id, u2.id, text='hi')
            stats = get_user_stats()
            assert stats['total_users'] == 3
            assert stats['total_farmers'] == 2
            assert stats['total_admins'] == 1
            assert stats['total_detections'] == 1
            assert stats['total_messages'] == 1

    def test_get_all_users_filter_by_role(self, app):
        with app.app_context():
            create_user('f', 'f@example.com', 'pass', role='farmer')
            create_user('a', 'a@example.com', 'pass', role='agrovet')
            farmers = get_all_users(role='farmer')
            assert len(farmers) == 1
            assert farmers[0].role == 'farmer'


@pytest.mark.db
class TestAdminCreation:
    """Admin user creation."""

    def test_create_admin(self, app):
        with app.app_context():
            admin, err = create_admin('root', 'root@example.com', 'toor')
            assert admin is not None
            assert admin.role == 'admin'
            assert admin.check_password('toor')

    def test_create_admin_duplicate(self, app):
        with app.app_context():
            create_admin('root', 'root@example.com', 'toor')
            admin2, err = create_admin('root2', 'root@example.com', 'toor')
            assert admin2 is None
            assert 'already exists' in err
