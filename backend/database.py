"""
Smart Crop AI - Database Layer
SQLite with SQLAlchemy ORM
"""

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import event, func
import json
import math

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='farmer')
    location = db.Column(db.String(200), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    profile_picture = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_reset_required = db.Column(db.Boolean, default=False)
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    password_reset_token = db.Column(db.String(256), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)

    # Location-based fields
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen_at = db.Column(db.DateTime, nullable=True)

    detections = db.relationship('Detection', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    activities = db.relationship('Activity', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    feedbacks = db.relationship('Feedback', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_email=True):
        d = {
            'id': self.id,
            'username': self.username,
            'phone': self.phone,
            'role': self.role,
            'location': self.location,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'isOnline': self.is_online,
            'lastSeenAt': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'profilePicture': self.profile_picture,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
            'passwordResetRequired': self.password_reset_required,
            'lastPasswordChange': self.last_password_change.isoformat() if self.last_password_change else None,
        }
        if include_email:
            d['email'] = self.email
        return d


class Detection(db.Model):
    __tablename__ = 'detections'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    disease = db.Column(db.String(200), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    severity = db.Column(db.String(50), nullable=True)
    is_healthy = db.Column(db.Boolean, default=False)
    crop = db.Column(db.String(100), nullable=True)
    symptoms = db.Column(db.Text, nullable=True)  # JSON list
    causes = db.Column(db.Text, nullable=True)
    recommendation = db.Column(db.Text, nullable=True)  # JSON list
    prevention = db.Column(db.Text, nullable=True)
    image_id = db.Column(db.String(100), nullable=True)
    caption = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'disease': self.disease,
            'confidence': self.confidence,
            'severity': self.severity,
            'is_healthy': self.is_healthy,
            'crop': self.crop,
            'symptoms': json.loads(self.symptoms) if self.symptoms else [],
            'causes': self.causes,
            'recommendation': json.loads(self.recommendation) if self.recommendation else [],
            'prevention': self.prevention,
            'image_id': self.image_id,
            'caption': self.caption,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(100), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(20), default='text')
    media_url = db.Column(db.Text, nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'text': self.text,
            'type': self.type,
            'media_url': self.media_url,
            'read': self.read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Activity(db.Model):
    __tablename__ = 'activities'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'text': self.text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Feedback(db.Model):
    __tablename__ = 'feedback_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    predicted_class = db.Column(db.String(200), nullable=True)
    correct_class = db.Column(db.String(200), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    image_path = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'predicted_class': self.predicted_class,
            'correct_class': self.correct_class,
            'confidence': self.confidence,
            'image_path': self.image_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('User', backref='audit_actions')

    def to_dict(self):
        return {
            'id': self.id,
            'adminId': self.admin_id,
            'adminName': self.admin.username if self.admin else 'Unknown',
            'action': self.action,
            'targetType': self.target_type,
            'targetId': self.target_id,
            'details': self.details,
            'ipAddress': self.ip_address,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


# ── SQLite updated_at fix ──
# SQLite does not support ON UPDATE, so we use an event listener.
@event.listens_for(User, 'before_update')
def user_before_update(mapper, connection, target):
    target.updated_at = datetime.utcnow()


# ── HELPER FUNCTIONS ──

def init_app(app):
    """Initialize SQLAlchemy with the Flask app."""
    db.init_app(app)
    # Table creation is handled by Flask-Migrate migrations (alembic).
    # Run `flask db upgrade` before starting the app in production.
    # For local SQLite dev, migrations are still preferred over db.create_all().


def create_user(username, email, password, phone=None, role='farmer', location=None,
                profile_picture=None, latitude=None, longitude=None):
    """Create a new user with hashed password."""
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return None, 'User with this email or username already exists'
    user = User(
        username=username,
        email=email,
        phone=phone,
        role=role,
        location=location,
        profile_picture=profile_picture,
        latitude=latitude,
        longitude=longitude,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, None


def create_admin(username, email, password):
    """Create an admin user if one does not already exist with this email/username."""
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return None, 'Admin with this email or username already exists'
    user = User(
        username=username,
        email=email,
        role='admin',
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, None


def authenticate_user(identifier, password):
    """Authenticate by email, phone, or username + password.
    identifier can be email, phone number, or username.
    """
    user = User.query.filter(
        (User.email == identifier) | (User.phone == identifier) | (User.username == identifier)
    ).first()
    if not user:
        return None, 'Invalid credentials'
    if not user.check_password(password):
        return None, 'Invalid credentials'
    return user, None


def get_user_by_id(user_id):
    return User.query.get(user_id)


def get_user_by_username(username):
    return User.query.filter_by(username=username).first()


def get_user_by_email(email):
    return User.query.filter_by(email=email).first()


def save_detection(user_id, disease=None, confidence=None, severity=None, is_healthy=False,
                   crop=None, symptoms=None, causes=None, recommendation=None, prevention=None,
                   image_id=None, caption=None):
    """Persist a detection result."""
    det = Detection(
        user_id=user_id,
        disease=disease,
        confidence=confidence,
        severity=severity,
        is_healthy=is_healthy,
        crop=crop,
        symptoms=json.dumps(symptoms) if symptoms else None,
        causes=causes,
        recommendation=json.dumps(recommendation) if recommendation else None,
        prevention=prevention,
        image_id=image_id,
        caption=caption,
    )
    db.session.add(det)
    db.session.commit()
    return det


def get_detections_for_user(user_id, limit=50):
    return Detection.query.filter_by(user_id=user_id).order_by(Detection.created_at.desc()).limit(limit).all()


def get_detection_by_id(detection_id, user_id=None):
    q = Detection.query.filter_by(id=detection_id)
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    return q.first()


def delete_detection(detection_id, user_id):
    det = Detection.query.filter_by(id=detection_id, user_id=user_id).first()
    if det:
        db.session.delete(det)
        db.session.commit()
        return True
    return False


def save_message(conversation_id, sender_id, receiver_id, text=None, type='text', media_url=None):
    msg = Message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        text=text,
        type=type,
        media_url=media_url,
        read=False,
    )
    db.session.add(msg)
    db.session.commit()
    return msg


def get_conversation_messages(conversation_id, limit=100):
    return Message.query.filter_by(conversation_id=conversation_id).order_by(Message.created_at.asc()).limit(limit).all()


def get_conversations_for_user(user_id):
    """Return distinct conversation IDs and the other participant for a user."""
    sent = Message.query.filter_by(sender_id=user_id).with_entities(Message.conversation_id, Message.receiver_id).distinct().all()
    received = Message.query.filter_by(receiver_id=user_id).with_entities(Message.conversation_id, Message.sender_id).distinct().all()
    convs = {}
    for conv_id, other_id in sent:
        convs[conv_id] = other_id
    for conv_id, other_id in received:
        convs[conv_id] = other_id
    return convs


def mark_conversation_read(conversation_id, user_id):
    Message.query.filter_by(conversation_id=conversation_id, receiver_id=user_id, read=False).update({'read': True})
    db.session.commit()


def get_unread_count(user_id):
    return Message.query.filter_by(receiver_id=user_id, read=False).count()


def save_activity(user_id, type, text):
    act = Activity(user_id=user_id, type=type, text=text)
    db.session.add(act)
    db.session.commit()
    return act


def get_activities_for_user(user_id, limit=50):
    return Activity.query.filter_by(user_id=user_id).order_by(Activity.created_at.desc()).limit(limit).all()


def save_feedback(predicted_class, correct_class, confidence=None, image_path=None, user_id=None):
    fb = Feedback(
        user_id=user_id,
        predicted_class=predicted_class,
        correct_class=correct_class,
        confidence=confidence,
        image_path=image_path,
    )
    db.session.add(fb)
    db.session.commit()
    return fb


def get_all_users(role=None):
    q = User.query
    if role:
        q = q.filter_by(role=role)
    return q.order_by(User.created_at.desc()).all()


def haversine_distance(lat1, lng1, lat2, lng2):
    """Calculate the great-circle distance between two points on earth in kilometers."""
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_nearby_agrovets(latitude, longitude, radius_km=50.0, limit=50):
    """Return agrovets within radius_km using Haversine formula.
    Works on both PostgreSQL and SQLite.
    """
    if latitude is None or longitude is None:
        return []

    # For PostgreSQL, use raw Haversine in SQL for performance
    # For SQLite, compute in Python
    db_uri = str(db.engine.url)
    is_postgres = 'postgresql' in db_uri or 'postgres' in db_uri

    if is_postgres:
        # Earth radius in meters for PostgreSQL earthdistance-like math
        R = 6371000.0
        # Haversine raw SQL
        distance_expr = (
            R * func.acos(
                func.least(1.0, func.greatest(-1.0,
                    func.cos(func.radians(latitude)) *
                    func.cos(func.radians(User.latitude)) *
                    func.cos(func.radians(User.longitude - longitude)) +
                    func.sin(func.radians(latitude)) *
                    func.sin(func.radians(User.latitude))
                ))
            ) / 1000.0
        )
        results = (
            User.query
            .filter_by(role='agrovet')
            .filter(User.latitude.isnot(None))
            .filter(User.longitude.isnot(None))
            .add_columns(distance_expr.label('distance'))
            .filter(distance_expr <= radius_km)
            .order_by(distance_expr.asc())
            .limit(limit)
            .all()
        )
        return [(u, d) for u, d in results]
    else:
        # SQLite fallback: filter roughly then compute exact distance in Python
        # Rough bounding box filter (1 degree lat ~ 111km)
        deg_offset = radius_km / 111.0
        q = (
            User.query
            .filter_by(role='agrovet')
            .filter(User.latitude.isnot(None))
            .filter(User.longitude.isnot(None))
            .filter(User.latitude.between(latitude - deg_offset, latitude + deg_offset))
            .filter(User.longitude.between(longitude - deg_offset, longitude + deg_offset))
            .all()
        )
        results = []
        for user in q:
            d = haversine_distance(latitude, longitude, user.latitude, user.longitude)
            if d is not None and d <= radius_km:
                results.append((user, d))
        results.sort(key=lambda x: x[1])
        return results[:limit]


def update_user_location(user_id, latitude, longitude):
    user = User.query.get(user_id)
    if not user:
        return None
    user.latitude = latitude
    user.longitude = longitude
    db.session.commit()
    return user


def update_user_online_status(user_id, is_online):
    user = User.query.get(user_id)
    if not user:
        return None
    user.is_online = is_online
    user.last_seen_at = datetime.utcnow()
    db.session.commit()
    return user


def get_user_stats():
    """Quick aggregate stats for the admin dashboard."""
    total_users = User.query.count()
    total_farmers = User.query.filter_by(role='farmer').count()
    total_agrovets = User.query.filter_by(role='agrovet').count()
    total_admins = User.query.filter_by(role='admin').count()
    total_detections = Detection.query.count()
    total_messages = Message.query.count()
    return {
        'total_users': total_users,
        'total_farmers': total_farmers,
        'total_agrovets': total_agrovets,
        'total_admins': total_admins,
        'total_detections': total_detections,
        'total_messages': total_messages,
    }


def log_audit_action(admin_id, action, target_type, target_id=None, details=None, ip_address=None):
    """Log an admin action for audit purposes."""
    log = AuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
    )
    db.session.add(log)
    db.session.commit()
    return log


def get_audit_logs(limit=100, offset=0, admin_id=None, action=None):
    """Fetch audit logs with optional filtering."""
    q = AuditLog.query
    if admin_id:
        q = q.filter_by(admin_id=admin_id)
    if action:
        q = q.filter_by(action=action)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset).all()


def reset_user_password(user_id, new_password):
    """Reset a user's password and require them to change it on next login."""
    user = User.query.get(user_id)
    if not user:
        return None, 'User not found'
    user.set_password(new_password)
    user.password_reset_required = True
    user.last_password_change = datetime.utcnow()
    db.session.commit()
    return user, None


def change_user_password(user, new_password):
    """Change a user's own password. Clears password_reset_required flag."""
    user.set_password(new_password)
    user.password_reset_required = False
    user.last_password_change = datetime.utcnow()
    db.session.commit()
    return user
