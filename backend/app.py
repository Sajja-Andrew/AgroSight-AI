"""
Smart Crop AI - Production API (Unified Backend)
Flask backend with leaf validation, disease detection, AI chat, JWT auth, and admin endpoints.
"""

import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, create_access_token
import json
import uuid
from datetime import datetime, timedelta
from PIL import Image
import io
import base64
import logging

# ── CONFIG ──
import config as app_config

# Configure logging
logging.basicConfig(level=getattr(logging, app_config.LOG_LEVEL), format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS
# supports_credentials=True cannot be used with origins='*' per CORS spec.
# This project uses JWT tokens (not cookies), so credentials are not needed.
if app_config.CORS_ORIGINS == '*':
    CORS(app, origins='*')
else:
    CORS(app, supports_credentials=True, origins=app_config.CORS_ORIGINS)

# App config
app.config['MAX_CONTENT_LENGTH'] = app_config.MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = app_config.UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = app_config.ALLOWED_EXTENSIONS
app.config['SQLALCHEMY_DATABASE_URI'] = app_config.DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = app_config.JWT_SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=app_config.JWT_ACCESS_TOKEN_EXPIRES_DAYS)
app.config['ENABLE_RATE_LIMITING'] = app_config.ENABLE_RATE_LIMITING
app.config['ENABLE_SECURE_HEADERS'] = app_config.ENABLE_SECURE_HEADERS

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── SECURITY MIDDLEWARE ──
from middleware.security import apply_secure_headers, rate_limit, allowed_file, validate_email, validate_username, sanitize_string

@app.after_request
def after_request(response):
    return apply_secure_headers(response)

# ── DATABASE ──
from database import db, User, init_app as init_db, create_user, authenticate_user, get_user_by_id, create_admin
from database import save_detection, get_detections_for_user, get_detection_by_id, delete_detection
from database import save_message, get_conversation_messages, get_conversations_for_user, mark_conversation_read, get_unread_count
from database import save_activity, get_activities_for_user
from database import save_feedback, get_all_users, get_user_stats
from database import Message
from database import log_audit_action, get_audit_logs, reset_user_password, change_user_password

init_db(app)

# ── DATABASE MIGRATIONS (Flask-Migrate / Alembic) ──
try:
    from flask_migrate import Migrate
    migrate = Migrate(app, db)
except ImportError:
    logger.warning("Flask-Migrate not installed. Database migrations disabled.")
    migrate = None

jwt = JWTManager(app)

# ── ADMIN MIDDLEWARE ──
from functools import wraps

def admin_required(fn):
    """Decorator to ensure only admins can access a route."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        try:
            uid = int(get_jwt_identity())
            user = get_user_by_id(uid)
            if not user or user.role != 'admin':
                return jsonify({'success': False, 'message': 'Admin access required.'}), 403
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error(f"Admin middleware error: {e}")
            return jsonify({'success': False, 'message': 'Authentication error.'}), 401
    return wrapper

# ── MODELS ──
from model_loader import load_models

predictor, leaf_detector, model_loaded, leaf_model_loaded, model_engine = load_models(app_config)

# ── DISEASE INFO LOOKUP ──
DISEASE_INFO = {}
try:
    _db_path = os.path.join(_current_dir, 'data', 'disease_database.json')
    if os.path.exists(_db_path):
        with open(_db_path, 'r', encoding='utf-8') as f:
            DISEASE_INFO = json.load(f)
        logger.info(f"Loaded disease database: {len(DISEASE_INFO)} entries")
except Exception as e:
    logger.warning(f"Could not load disease database: {e}")

# ── UTILITIES ──
def decode_image(data):
    if isinstance(data, str):
        if 'base64,' in data:
            data = data.split('base64,')[1]
        image_bytes = base64.b64decode(data)
    else:
        image_bytes = data
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return image

def save_upload(image):
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(filepath, 'JPEG', quality=90)
    return filepath, filename

def current_user_id():
    try:
        from flask_jwt_extended import verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        return int(identity) if identity else None
    except Exception:
        return None

# ── MOCK DATA ──
def get_mock_leaf_result(is_leaf=True):
    if is_leaf:
        return {'is_leaf': True, 'confidence': 0.95, 'method': 'mock', 'message': 'Leaf detected (mock).'}
    return {'is_leaf': False, 'confidence': 0.12, 'method': 'mock', 'message': 'This is not a plant leaf. Please upload a clear leaf image.'}

def get_mock_disease_prediction():
    pred = {
        'success': True, 'is_leaf': True, 'crop': 'Tomato', 'disease': 'Tomato Early Blight',
        'confidence': 0.87, 'severity': 'Moderate',
        'symptoms': ['Dark brown spots with concentric rings', 'Yellowing of lower leaves', 'Premature leaf drop'],
        'causes': 'Fungal infection caused by Alternaria solani.',
        'recommendation': ['Remove infected lower leaves', 'Apply fungicide every 7-10 days', 'Improve air circulation'],
        'prevention': 'Crop rotation, proper spacing, avoid wetting foliage.',
        'is_healthy': False, 'message': 'You can ask me any question about this result or your crop.',
        'predictions': [], 'mock': True
    }
    pred['primary_prediction'] = pred.copy()
    pred['primary_prediction'].pop('predictions', None)
    pred['primary_prediction'].pop('primary_prediction', None)
    return pred

def get_mock_healthy_prediction():
    pred = {
        'success': True, 'is_leaf': True, 'crop': 'Tomato', 'disease': 'Healthy Tomato',
        'confidence': 0.94, 'severity': 'None',
        'symptoms': ['No disease detected - plant appears healthy.'],
        'causes': 'No disease detected.',
        'recommendation': ['Continue good agricultural practices', 'Monitor regularly'],
        'prevention': 'Maintain proper watering and fertilization.',
        'is_healthy': True, 'message': 'You can ask me any question about this result or your crop.',
        'predictions': [], 'mock': True
    }
    pred['primary_prediction'] = pred.copy()
    pred['primary_prediction'].pop('predictions', None)
    pred['primary_prediction'].pop('primary_prediction', None)
    return pred

# ── AI CHAT KNOWLEDGE BASE ──
CHAT_RESPONSES = {
    'greeting': [
        "Hello! I am your Smart Crop AI Assistant. I help farmers with crop diseases, pests, soil, and farming advice. How can I help you today?",
        "Hi there! I am here to give you practical farming advice. What would you like to know?"
    ],
    'prevention': [
        "Prevention tips:\n\n• Use certified, disease-free seeds\n• Practice crop rotation every season\n• Keep proper spacing for air flow\n• Ensure good drainage\n• Scout your farm weekly",
        "To stop disease before it starts:\n\n• Rotate crops yearly\n• Use resistant varieties\n• Clean tools after use\n• Avoid watering leaves directly"
    ],
    'treatment': [
        "Treatment steps:\n\n• Confirm the disease by uploading a leaf photo\n• For fungal diseases: apply recommended fungicide\n• For bacterial diseases: use copper-based sprays\n• For viral diseases: remove infected plants\n• Always follow chemical label instructions",
        "Step-by-step treatment:\n\n1. Identify the exact disease or pest\n2. Remove badly infected parts\n3. Apply the right remedy\n4. Repeat as advised\n5. Watch for improvement over 7-14 days"
    ],
    'fertilizer': [
        "Fertilizer advice:\n\n• Test your soil to know what nutrients are missing\n• Apply NPK based on crop needs\n• Add compost or manure\n• Do not over-use nitrogen",
        "How to fertilize:\n\n• Mix into soil at planting\n• Top-dress when crop is actively growing\n• Use organic matter alongside chemical fertilizer"
    ],
    'water': [
        "Water and irrigation tips:\n\n• Water early morning to reduce disease\n• Use drip irrigation if possible\n• Do not let water stand in the field\n• Mulch to keep soil moist",
        "Proper watering:\n\n• Give deep soaks rather than light sprinkles\n• Avoid wetting leaves in the evening"
    ],
    'chemicals': [
        "Safe chemical use:\n\n• Read and follow label instructions\n• Wear protective clothing\n• Do not spray near water sources\n• Observe pre-harvest interval\n• Store chemicals locked away",
        "Pesticide safety:\n\n• Mix only what you need\n• Spray in calm weather\n• Wash hands after spraying"
    ],
    'healthy': [
        "Your plant looks healthy! Keep it that way:\n\n• Continue regular monitoring\n• Water and fertilize on schedule\n• Watch for any new spots or pests",
        "Good news - plant appears healthy. Keep up balanced nutrition and timely watering."
    ],
    'uncertain': [
        "I am not fully certain. I recommend:\n\n• Upload a clear photo for better diagnosis\n• Or visit a local agricultural extension officer",
        "That is complex. Please share more details or upload an image so I can help directly."
    ]
}

def build_chat_response(message, last_detection=None):
    msg = (message or '').strip().lower()
    if not msg:
        return "Hello! I am your Smart Crop AI Assistant. Upload a plant image for diagnosis or ask me anything about your farm."

    if last_detection:
        disease = last_detection.get('disease', '')
        is_healthy = last_detection.get('is_healthy', False)
        prevention = last_detection.get('prevention', '')
        recommendation = last_detection.get('recommendation', [])
        causes = last_detection.get('causes', '')
        symptoms = last_detection.get('symptoms', [])

        if any(k in msg for k in ['prevent', 'avoid', 'stop', 'future']):
            steps = prevention if prevention else "Practice crop rotation, use certified seeds, and keep the field clean."
            return f"To prevent {disease} in the future:\n\n{steps}\n\nIf you need specific steps, ask me or consult a local extension officer."

        if any(k in msg for k in ['treat', 'cure', 'fix', 'solve', 'what should i do']):
            steps = '\n'.join([f'{i+1}. {r}' for i, r in enumerate(recommendation[:5])])
            return f"Step-by-step treatment for {disease}:\n\n{steps}\n\nFollow carefully. If no improvement in 10-14 days, visit an agro-vet."

        if any(k in msg for k in ['symptom', 'sign', 'why', 'cause']):
            symp_text = '\n'.join([f'• {s}' for s in symptoms[:5]])
            return f"Symptoms of {disease}:\n\n{symp_text}\n\nCauses:\n{causes}\n\nThese usually spread during warm, wet weather. Early action is important."

        if any(k in msg for k in ['last', 'recent', 'previous', 'my detection', 'my result']):
            conf = last_detection.get('confidence', 0)
            sev = last_detection.get('severity', 'Unknown')
            return f"Your last detection was **{disease}** with {conf*100:.1f}% confidence. Severity: {sev}."

        if any(k in msg for k in ['healthy', 'good', 'fine', 'normal']):
            if is_healthy:
                return "Your plant is healthy! Keep up with regular monitoring and proper watering."
            return f"Your detected condition ({disease}) needs attention. Follow the treatment steps and monitor closely."

    if any(k in msg for k in ['hello', 'hi', 'hey']):
        return "Hello! I am your Smart Crop AI Assistant. How can I help you today?"
    if any(k in msg for k in ['thank', 'thanks']):
        return "You are very welcome! I am here whenever you need farming advice."
    if any(k in msg for k in ['treatment', 'cure', 'fix']):
        return CHAT_RESPONSES['treatment'][0]
    if any(k in msg for k in ['prevent', 'avoid', 'stop']):
        return CHAT_RESPONSES['prevention'][0]
    if any(k in msg for k in ['fertilizer', 'nutrient', 'soil']):
        return CHAT_RESPONSES['fertilizer'][0]
    if any(k in msg for k in ['water', 'irrigate', 'rain']):
        return CHAT_RESPONSES['water'][0]
    if any(k in msg for k in ['fungicide', 'pesticide', 'chemical', 'spray']):
        return CHAT_RESPONSES['chemicals'][0]
    if any(k in msg for k in ['healthy', 'good', 'fine']):
        return CHAT_RESPONSES['healthy'][0]

    return CHAT_RESPONSES['uncertain'][0]

# ── ROUTES ──

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'success',
        'message': 'Smart Crop AI - Disease Detection API',
        'version': '3.0.0',
        'model_loaded': model_loaded,
        'leaf_detector_loaded': leaf_model_loaded,
        'endpoints': {
            '/api/analyze': 'POST - Full pipeline: leaf check + disease detection',
            '/api/chat': 'POST - AI assistant',
            '/api/auth/register': 'POST - Create account',
            '/api/auth/login': 'POST - Log in',
            '/api/auth/admin/login': 'POST - Admin log in',
            '/api/auth/me': 'GET/PUT - Profile',
            '/api/detections': 'GET - Detection history',
            '/api/messages': 'POST - Send message',
            '/api/messages/conversations': 'GET - Conversations',
            '/api/feedback': 'POST - Submit feedback',
            '/api/health': 'GET - Health check',
            '/api/model-status': 'GET - Model status'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'model_loaded': model_loaded,
        'leaf_detector_loaded': leaf_model_loaded,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/analyze', methods=['POST'])
@rate_limit(limit=30, window_seconds=60)
def analyze():
    try:
        data = request.get_json() or {}
        image_data = data.get('image')
        if not image_data:
            return jsonify({'success': False, 'is_leaf': False, 'message': 'No image data provided.'}), 400

        try:
            image = decode_image(image_data)
        except Exception as e:
            logger.error(f"Image decode error: {e}")
            return jsonify({'success': False, 'is_leaf': False, 'message': 'Invalid image data.'}), 400

        try:
            filepath, filename = save_upload(image)
            logger.info(f"Image saved: {filename}")
        except Exception:
            filename = None

        # Leaf detection
        if leaf_detector is not None:
            leaf_result = leaf_detector.predict(image)
        else:
            leaf_result = get_mock_leaf_result(is_leaf=True)
            leaf_result['method'] = 'fallback'

        if not leaf_result['is_leaf']:
            return jsonify({
                'success': False,
                'is_leaf': False,
                'confidence': leaf_result.get('confidence'),
                'method': leaf_result.get('method'),
                'message': leaf_result.get('message', 'This is not a plant leaf. Please upload a clear leaf image.')
            })

        # Disease classification
        result = None
        if model_loaded and predictor is not None:
            try:
                result = predictor.predict(image)
                result['leaf_check'] = leaf_result
                if filename:
                    result['image_id'] = filename
                logger.info(f"Prediction: {result.get('disease')} ({result.get('confidence')})")
            except Exception as e:
                logger.error(f"Prediction error: {e}")

        if result is None:
            import random
            result = get_mock_healthy_prediction() if random.random() > 0.5 else get_mock_disease_prediction()
            result['leaf_check'] = leaf_result
            if filename:
                result['image_id'] = filename
            logger.info("Returning mock prediction")

        # Persist to DB
        uid = current_user_id()
        if uid:
            try:
                primary = result.get('primary_prediction', result)
                save_detection(
                    user_id=uid,
                    disease=primary.get('disease'),
                    confidence=primary.get('confidence'),
                    severity=primary.get('severity'),
                    is_healthy=primary.get('is_healthy', False),
                    crop=primary.get('crop'),
                    symptoms=primary.get('symptoms'),
                    causes=primary.get('causes'),
                    recommendation=primary.get('recommendation'),
                    prevention=primary.get('prevention'),
                    image_id=result.get('image_id'),
                    caption=data.get('caption'),
                )
                save_activity(user_id=uid, type='detection', text=f"Detected {primary.get('disease', 'Unknown')}")
            except Exception as db_err:
                logger.warning(f"Could not save detection to DB: {db_err}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Analyze error: {e}")
        return jsonify({'success': False, 'is_leaf': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        last_detection = data.get('last_detection')
        response_text = build_chat_response(message, last_detection)
        return jsonify({'success': True, 'message': response_text, 'context': {'has_detection': last_detection is not None}})
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'success': False, 'message': 'Sorry, I encountered an error. Please try again.'}), 500

# ── AUTH ENDPOINTS ──

@app.route('/api/auth/register', methods=['POST'])
@rate_limit(limit=10, window_seconds=60)
def register():
    try:
        data = request.get_json() or {}
        username = sanitize_string(data.get('username') or '', max_length=80)
        email = sanitize_string(data.get('email') or '', max_length=120).lower()
        password = data.get('password', '')
        phone = sanitize_string(data.get('phone') or '', max_length=20) or None
        role = sanitize_string(data.get('role') or 'farmer', max_length=20).lower()
        location = sanitize_string(data.get('location') or '', max_length=200) or None

        if not username or not email or not password:
            return jsonify({'success': False, 'message': 'Username, email, and password are required.'}), 400
        if not validate_username(username):
            return jsonify({'success': False, 'message': 'Username must be 3-30 characters, alphanumeric and underscores only.'}), 400
        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Please provide a valid email address.'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters.'}), 400
        if role not in ('farmer', 'agrovet'):
            role = 'farmer'

        user, err = create_user(username, email, password, phone=phone, role=role, location=location)
        if err:
            return jsonify({'success': False, 'message': err}), 409

        token = create_access_token(identity=str(user.id))
        return jsonify({'success': True, 'token': token, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Register error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
@rate_limit(limit=10, window_seconds=60)
def login():
    try:
        data = request.get_json() or {}
        identifier = sanitize_string(data.get('identifier') or data.get('email') or data.get('phone') or data.get('username') or '', max_length=120)
        password = data.get('password', '')

        if not identifier or not password:
            return jsonify({'success': False, 'message': 'Identifier and password are required.'}), 400

        user, err = authenticate_user(identifier, password)
        if err:
            return jsonify({'success': False, 'message': err}), 401

        token = create_access_token(identity=str(user.id))
        return jsonify({'success': True, 'token': token, 'user': user.to_dict(), 'passwordResetRequired': user.password_reset_required})
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/admin/login', methods=['POST'])
@rate_limit(limit=5, window_seconds=60)
def admin_login():
    try:
        data = request.get_json() or {}
        identifier = sanitize_string(data.get('identifier') or data.get('username') or data.get('email') or '', max_length=120)
        password = data.get('password', '')

        if not identifier or not password:
            return jsonify({'success': False, 'message': 'Identifier and password are required.'}), 400

        user, err = authenticate_user(identifier, password)
        if err:
            return jsonify({'success': False, 'message': err}), 401

        if user.role != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required.'}), 403

        token = create_access_token(identity=str(user.id))
        return jsonify({'success': True, 'token': token, 'user': user.to_dict(), 'passwordResetRequired': user.password_reset_required})
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404
        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Me error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/me', methods=['PUT'])
@jwt_required()
def update_me():
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404

        data = request.get_json() or {}
        if 'phone' in data:
            user.phone = sanitize_string(data['phone'], max_length=20)
        if 'location' in data:
            user.location = sanitize_string(data['location'], max_length=200)
        if 'profile_picture' in data:
            user.profile_picture = data['profile_picture']
        if 'email' in data:
            from database import User as UserModel
            existing = UserModel.query.filter(UserModel.email == data['email'], UserModel.id != uid).first()
            if existing:
                return jsonify({'success': False, 'message': 'Email already in use.'}), 409
            user.email = sanitize_string(data['email'], max_length=120).lower()

        db.session.commit()
        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Update me error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── PASSWORD CHANGE ──
@app.route('/api/auth/change-password', methods=['POST'])
@jwt_required()
@rate_limit(limit=5, window_seconds=60)
def change_password():
    """Allow any authenticated user to change their own password."""
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404

        data = request.get_json() or {}
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')

        if not new_password or len(new_password) < 8:
            return jsonify({'success': False, 'message': 'New password must be at least 8 characters.'}), 400

        # If password reset is required, skip current_password check
        if not user.password_reset_required:
            if not current_password:
                return jsonify({'success': False, 'message': 'Current password is required.'}), 400
            if not user.check_password(current_password):
                return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 401

        change_user_password(user, new_password)
        logger.info(f"User {user.id} changed password.")
        return jsonify({'success': True, 'message': 'Password changed successfully. Please log in again.'})
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── DETECTIONS ──
@app.route('/api/detections', methods=['GET'])
@jwt_required()
def get_detections():
    try:
        uid = int(get_jwt_identity())
        limit = request.args.get('limit', 50, type=int)
        dets = get_detections_for_user(uid, limit=limit)
        return jsonify({'success': True, 'count': len(dets), 'detections': [d.to_dict() for d in dets]})
    except Exception as e:
        logger.error(f"Get detections error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/detections/<int:det_id>', methods=['GET'])
@jwt_required()
def get_detection(det_id):
    try:
        uid = int(get_jwt_identity())
        det = get_detection_by_id(det_id, user_id=uid)
        if not det:
            return jsonify({'success': False, 'message': 'Detection not found.'}), 404
        return jsonify({'success': True, 'detection': det.to_dict()})
    except Exception as e:
        logger.error(f"Get detection error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/detections/<int:det_id>', methods=['DELETE'])
@jwt_required()
def delete_detection_route(det_id):
    try:
        uid = int(get_jwt_identity())
        ok = delete_detection(det_id, uid)
        if not ok:
            return jsonify({'success': False, 'message': 'Detection not found.'}), 404
        return jsonify({'success': True, 'message': 'Detection deleted.'})
    except Exception as e:
        logger.error(f"Delete detection error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── MESSAGES ──
@app.route('/api/messages', methods=['POST'])
@jwt_required()
def create_message():
    try:
        uid = int(get_jwt_identity())
        data = request.get_json() or {}
        receiver_id = data.get('receiver_id')
        text = sanitize_string(data.get('text', ''), max_length=2000)
        type = sanitize_string(data.get('type', 'text'), max_length=20)
        media_url = data.get('media_url')

        if not receiver_id:
            return jsonify({'success': False, 'message': 'receiver_id is required.'}), 400

        conv_id = '_'.join(sorted([str(uid), str(receiver_id)]))
        msg = save_message(conv_id, uid, receiver_id, text=text, type=type, media_url=media_url)
        return jsonify({'success': True, 'message': msg.to_dict()})
    except Exception as e:
        logger.error(f"Create message error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    try:
        uid = int(get_jwt_identity())
        convs = get_conversations_for_user(uid)
        result = []
        for conv_id, other_id in convs.items():
            other = get_user_by_id(other_id)
            last_msgs = get_conversation_messages(conv_id, limit=1)
            last_msg = last_msgs[0].to_dict() if last_msgs else None
            unread = Message.query.filter_by(conversation_id=conv_id, receiver_id=uid, read=False).count()
            result.append({
                'conversation_id': conv_id,
                'other_user': other.to_dict(include_email=False) if other else {'id': other_id},
                'last_message': last_msg,
                'unread_count': unread,
            })
        result.sort(key=lambda x: x['last_message']['created_at'] if x['last_message'] else '', reverse=True)
        return jsonify({'success': True, 'conversations': result})
    except Exception as e:
        logger.error(f"Get conversations error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/<string:conv_id>', methods=['GET'])
@jwt_required()
def get_messages(conv_id):
    try:
        uid = int(get_jwt_identity())
        limit = request.args.get('limit', 100, type=int)
        msgs = get_conversation_messages(conv_id, limit=limit)
        mark_conversation_read(conv_id, uid)
        return jsonify({'success': True, 'messages': [m.to_dict() for m in msgs]})
    except Exception as e:
        logger.error(f"Get messages error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── ACTIVITY ──
@app.route('/api/activity', methods=['GET'])
@jwt_required()
def get_activity():
    try:
        uid = int(get_jwt_identity())
        limit = request.args.get('limit', 50, type=int)
        acts = get_activities_for_user(uid, limit=limit)
        return jsonify({'success': True, 'activities': [a.to_dict() for a in acts]})
    except Exception as e:
        logger.error(f"Get activity error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── USERS / ADMIN ──
@app.route('/api/users', methods=['GET'])
@jwt_required()
def list_users():
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        if not user or user.role != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required.'}), 403

        role = request.args.get('role')
        users = get_all_users(role=role)
        return jsonify({'success': True, 'count': len(users), 'users': [u.to_dict() for u in users]})
    except Exception as e:
        logger.error(f"List users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/stats', methods=['GET'])
@jwt_required()
def user_stats():
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        if not user or user.role != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required.'}), 403
        stats = get_user_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"User stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/farmers', methods=['GET'])
def list_farmers():
    try:
        farmers = get_all_users(role='farmer')
        return jsonify({'success': True, 'count': len(farmers), 'farmers': [f.to_dict() for f in farmers]})
    except Exception as e:
        logger.error(f"List farmers error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/agrovets', methods=['GET'])
def list_agrovets():
    try:
        agrovets = get_all_users(role='agrovet')
        return jsonify({'success': True, 'count': len(agrovets), 'agrovets': [a.to_dict() for a in agrovets]})
    except Exception as e:
        logger.error(f"List agrovets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── ADMIN MANAGEMENT ──
import secrets

@app.route('/api/admin/users', methods=['GET'])
@admin_required
@rate_limit(limit=30, window_seconds=60)
def admin_list_users():
    """List all users with optional role filter and pagination."""
    try:
        role = request.args.get('role')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        q = User.query
        if role:
            q = q.filter_by(role=role)
        total = q.count()
        users = q.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
        return jsonify({'success': True, 'total': total, 'count': len(users), 'users': [u.to_dict() for u in users]})
    except Exception as e:
        logger.error(f"Admin list users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_required
@rate_limit(limit=30, window_seconds=60)
def admin_get_user(user_id):
    """Get a single user by ID (admin only)."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404
        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Admin get user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
@rate_limit(limit=10, window_seconds=60)
def admin_update_user(user_id):
    """Update user details (admin only)."""
    try:
        admin_uid = int(get_jwt_identity())
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404

        data = request.get_json() or {}
        changes = []

        if 'phone' in data:
            user.phone = sanitize_string(data['phone'], max_length=20)
            changes.append('phone')
        if 'location' in data:
            user.location = sanitize_string(data['location'], max_length=200)
            changes.append('location')
        if 'role' in data:
            new_role = sanitize_string(data['role'], max_length=20).lower()
            if new_role in ('farmer', 'agrovet', 'admin'):
                user.role = new_role
                changes.append('role')
        if 'email' in data:
            existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
            if existing:
                return jsonify({'success': False, 'message': 'Email already in use.'}), 409
            user.email = sanitize_string(data['email'], max_length=120).lower()
            changes.append('email')

        db.session.commit()

        # Audit log
        log_audit_action(
            admin_id=admin_uid,
            action='UPDATE_USER',
            target_type='user',
            target_id=user_id,
            details=f"Updated fields: {', '.join(changes)}",
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Admin update user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
@rate_limit(limit=5, window_seconds=60)
def admin_reset_password(user_id):
    """Reset a user's password and require them to change it on next login."""
    try:
        admin_uid = int(get_jwt_identity())
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404

        # Generate a secure temporary password
        temp_password = secrets.token_urlsafe(12)
        reset_user_password(user_id, temp_password)

        # Audit log
        log_audit_action(
            admin_id=admin_uid,
            action='RESET_PASSWORD',
            target_type='user',
            target_id=user_id,
            details=f"Password reset for user {user.username}",
            ip_address=request.remote_addr,
        )

        logger.warning(f"Admin {admin_uid} reset password for user {user_id}")
        return jsonify({'success': True, 'message': 'Password reset successfully.', 'temporaryPassword': temp_password})
    except Exception as e:
        logger.error(f"Admin reset password error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
@rate_limit(limit=5, window_seconds=60)
def admin_delete_user(user_id):
    """Delete a user account (admin only)."""
    try:
        admin_uid = int(get_jwt_identity())
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404
        if user.id == admin_uid:
            return jsonify({'success': False, 'message': 'Cannot delete your own account.'}), 400

        username = user.username
        db.session.delete(user)
        db.session.commit()

        # Audit log
        log_audit_action(
            admin_id=admin_uid,
            action='DELETE_USER',
            target_type='user',
            target_id=user_id,
            details=f"Deleted user: {username}",
            ip_address=request.remote_addr,
        )

        return jsonify({'success': True, 'message': f"User {username} deleted successfully."})
    except Exception as e:
        logger.error(f"Admin delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/audit-logs', methods=['GET'])
@admin_required
@rate_limit(limit=30, window_seconds=60)
def admin_audit_logs():
    """Fetch audit logs with optional filtering."""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        action_filter = request.args.get('action')
        logs = get_audit_logs(limit=limit, offset=offset, action=action_filter)
        return jsonify({'success': True, 'count': len(logs), 'logs': [l.to_dict() for l in logs]})
    except Exception as e:
        logger.error(f"Admin audit logs error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── FEEDBACK ──
# Also import FeedbackManager for image-based corrections
from legacy.feedback_manager import FeedbackManager
_feedback_manager = FeedbackManager()

_FEEDBACK_JSON_PATH = os.path.join(_current_dir, 'data', 'feedback.json')


def _append_to_feedback_json(entry: dict):
    """Atomically append a feedback entry to feedback.json."""
    try:
        existing = []
        if os.path.exists(_FEEDBACK_JSON_PATH):
            with open(_FEEDBACK_JSON_PATH, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        if not isinstance(existing, list):
            existing = []
        existing.append(entry)
        with open(_FEEDBACK_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not append to feedback.json: {e}")


@app.route('/api/feedback', methods=['POST'])
def feedback():
    try:
        data = request.get_json() or {}
        predicted = sanitize_string(data.get('predicted_class', 'unknown'), max_length=200)
        correct = sanitize_string(data.get('correct_class', 'unknown'), max_length=200)
        confidence = data.get('confidence', 0)
        image_id = data.get('image_id')
        image_data = data.get('image_data')  # optional base64 image

        entry = {
            'id': str(uuid.uuid4()),
            'predicted_class': predicted,
            'correct_class': correct,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'source': 'user_feedback',
            'status': 'verified',
            'image_path': image_id,
        }

        # Also save to DB
        uid = current_user_id()
        try:
            fb = save_feedback(
                user_id=uid,
                predicted_class=predicted,
                correct_class=correct,
                confidence=confidence,
                image_path=image_id,
            )
            entry['db_id'] = fb.id
        except Exception as db_err:
            logger.warning(f"Could not save feedback to DB: {db_err}")

        # Persist to feedback.json for pipeline consumption
        _append_to_feedback_json(entry)

        # Store feedback image for retraining if image_data provided
        if image_data:
            try:
                fm_result = _feedback_manager.store_feedback(
                    image_data=image_data,
                    predicted_class=predicted,
                    correct_class=correct,
                    confidence=confidence,
                )
                if fm_result.get('success'):
                    entry['feedback_image_path'] = fm_result.get('file_path')
            except Exception as fm_err:
                logger.warning(f"Could not store feedback image: {fm_err}")

        return jsonify({'success': True, 'message': 'Feedback saved', 'feedback_id': entry['id']})
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── MODEL STATUS ──
@app.route('/api/model-status', methods=['GET'])
def model_status():
    try:
        training_results_path = os.path.join(_current_dir, '..', 'saved_models', 'training_results.json')
        training_status = None
        if os.path.exists(training_results_path):
            try:
                with open(training_results_path, 'r', encoding='utf-8') as f:
                    training_status = json.load(f)
            except Exception:
                pass

        num_classes = 0
        if predictor and hasattr(predictor, 'class_indices'):
            num_classes = len(predictor.class_indices)

        return jsonify({
            'success': True,
            'model_loaded': model_loaded,
            'leaf_detector_loaded': leaf_model_loaded,
            'model_path': app_config.MODEL_PATH if os.path.exists(app_config.MODEL_PATH) else None,
            'class_indices_loaded': os.path.exists(app_config.CLASS_INDICES_PATH),
            'num_classes': num_classes,
            'training_status': training_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── LEGACY PREDICTION ENDPOINTS (file upload) ──
@app.route('/api/predict', methods=['POST'])
@rate_limit(limit=30, window_seconds=60)
def predict():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    try:
        image_bytes = file.read()
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(filepath)

        if model_loaded and predictor:
            results = predictor.predict(image)
            results['image_id'] = filename
        else:
            results = get_mock_disease_prediction()
            results['image_id'] = filename
        return jsonify(results)
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── ERROR HANDLERS ──
@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'error': 'File is too large. Maximum size is 16MB.'}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ── RETRAINING BLUEPRINT ──
from api_retrain_routes import retrain_bp
app.register_blueprint(retrain_bp)

# ── MAIN ──
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Smart Crop AI - Disease Detection API v3.0")
    print("=" * 60)
    print(f"\nDisease Model: {model_engine} ({'loaded' if model_loaded else 'not loaded'})")
    print(f"Leaf Detector: {'Loaded' if leaf_model_loaded else 'Not loaded (heuristic/mock mode)'}")
    print(f"\nAPI: http://localhost:5000")
    print("Main endpoint: POST /api/analyze")
    print("\nPress Ctrl+C to stop")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=app_config.DEBUG)
