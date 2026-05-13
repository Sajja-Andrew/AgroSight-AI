"""
Smart Crop Combined Server
- Disease Detection API
- Real-Time Chat System
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from PIL import Image
import io
import base64
import os
import json
import logging

# Import chat manager
from chat_manager import chat_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'Agrosight AI_secret_key_2024'

# Enable CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize SocketIO for real-time chat
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs('uploads', exist_ok=True)
os.makedirs('saved_models', exist_ok=True)
os.makedirs('data', exist_ok=True)

# Model paths
MODEL_PATH = 'saved_models/best_model.keras'
CLASS_INDICES_PATH = 'saved_models/class_indices.json'

# Disease information
DISEASE_INFO = {
    'Tomato___Late_blight': {
        'name': 'Tomato Late Blight',
        'symptoms': 'Water-soaked lesions on leaves',
        'solution': 'Apply copper fungicide immediately.',
        'prevention': 'Use resistant varieties.',
        'severity': 'High'
    },
    'Tomato___Early_blight': {
        'name': 'Tomato Early Blight',
        'symptoms': 'Dark spots with concentric rings',
        'solution': 'Apply chlorothalonil fungicide.',
        'prevention': 'Crop rotation.',
        'severity': 'Medium'
    },
    'Potato___Late_blight': {
        'name': 'Potato Late Blight',
        'symptoms': 'Water-soaked lesions, white fungal growth',
        'solution': 'Apply fungicide immediately.',
        'prevention': 'Use resistant varieties.',
        'severity': 'High'
    },
    'Tomato___healthy': {
        'name': 'Healthy Tomato',
        'symptoms': 'No disease detected',
        'solution': 'Continue good practices.',
        'prevention': 'Regular monitoring.',
        'severity': 'None'
    },
    'Potato___healthy': {
        'name': 'Healthy Potato',
        'symptoms': 'No disease detected',
        'solution': 'Continue good practices.',
        'prevention': 'Regular monitoring.',
        'severity': 'None'
    }
}

# Global predictor
predictor = None

def load_model():
    """Load trained model"""
    global predictor
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(CLASS_INDICES_PATH):
            import tensorflow as tf
            model = tf.keras.models.load_model(MODEL_PATH)
            
            with open(CLASS_INDICES_PATH, 'r') as f:
                class_indices = json.load(f)
            
            predictor = {
                'model': model,
                'class_indices': class_indices,
                'idx_to_class': {v: k for k, v in class_indices.items()}
            }
            logger.info("Model loaded successfully!")
            return True
        else:
            logger.warning("Model not found - training may be in progress")
            return False
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        return False

model_loaded = load_model()


# ============================================================
# SOCKET.IO EVENTS - REAL-TIME CHAT
# ============================================================

@socketio.on('connect')
def handle_connect():
    """Client connected"""
    logger.info(f"Client connected: {request.sid}")
    emit('connection_response', {'status': 'connected', 'sid': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    logger.info(f"Client disconnected: {request.sid}")
    
    # Find and remove user
    for user_id, user_data in list(chat_manager.online_users.items()):
        if user_data.get('session_id') == request.sid:
            chat_manager.set_user_offline(user_id)
            emit('user_status', {
                'user_id': user_id,
                'online': False,
                'last_seen': datetime.now().isoformat()
            }, broadcast=True)
            break


@socketio.on('join')
def handle_join(data):
    """
    User joins/identifies themselves
    
    Expected data:
    {
        'user_id': '123',
        'user_name': 'John Doe',
        'role': 'farmer' or 'agrovet'
    }
    """
    user_id = data.get('user_id')
    user_name = data.get('user_name', 'Unknown')
    role = data.get('role', 'farmer')
    
    if not user_id:
        return emit('error', {'message': 'User ID required'})
    
    # Store user session
    chat_manager.set_user_online(user_id, request.sid, {
        'user_id': user_id,
        'user_name': user_name,
        'role': role
    })
    
    # Join personal room
    join_room(f'user_{user_id}')
    
    logger.info(f"User {user_name} ({role}) joined: {user_id}")
    
    # Send online users list
    emit('online_users', {
        'users': chat_manager.get_online_users()
    })
    
    # Notify others
    emit('user_status', {
        'user_id': user_id,
        'user_name': user_name,
        'role': role,
        'online': True
    }, broadcast=True, include_self=False)
    
    # Send user's conversations
    conversations = chat_manager.get_user_conversations(user_id)
    emit('conversations', {'conversations': conversations})


@socketio.on('send_message')
def handle_send_message(data):
    """
    Send message from one user to another
    
    Expected data:
    {
        'sender_id': '123',
        'receiver_id': '456',
        'message': 'Hello!',
        'type': 'text'
    }
    """
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message = data.get('message')
    message_type = data.get('type', 'text')
    image_url = data.get('image_url')
    
    if not all([sender_id, receiver_id, message]):
        return emit('error', {'message': 'Missing required fields'})
    
    # Save message
    saved_msg = chat_manager.save_message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        message=message,
        message_type=message_type,
        image_url=image_url
    )
    
    logger.info(f"Message from {sender_id} to {receiver_id}")
    
    # Send to receiver's room
    emit('receive_message', saved_msg, room=f'user_{receiver_id}')
    
    # Send confirmation to sender
    emit('message_sent', saved_msg, room=f'user_{sender_id}')


@socketio.on('get_conversation')
def handle_get_conversation(data):
    """Get conversation between two users"""
    user_id = data.get('user_id')
    other_user_id = data.get('other_user_id')
    
    if not all([user_id, other_user_id]):
        return emit('error', {'message': 'Missing user IDs'})
    
    messages = chat_manager.get_conversation(user_id, other_user_id)
    chat_manager.mark_as_read(user_id, other_user_id)
    
    emit('conversation_messages', {
        'other_user_id': other_user_id,
        'messages': messages
    })


@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicator"""
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    is_typing = data.get('is_typing', False)
    
    chat_manager.set_typing(sender_id, receiver_id, is_typing)
    
    emit('typing_indicator', {
        'user_id': sender_id,
        'is_typing': is_typing
    }, room=f'user_{receiver_id}')


@socketio.on('get_online_users')
def handle_get_online_users():
    """Get list of online users"""
    emit('online_users', {
        'users': chat_manager.get_online_users()
    })


# ============================================================
# HTTP ROUTES - API
# ============================================================

@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        'status': 'success',
        'message': 'Smart Crop API with Real-Time Chat',
        'version': '2.0.0',
        'model_loaded': model_loaded,
        'online_users': len(chat_manager.get_online_users()),
        'features': {
            'disease_detection': True,
            'real_time_chat': True,
            'online_status': True
        },
        'endpoints': {
            '/': 'GET - API info',
            '/api/health': 'GET - Health check',
            '/api/predict': 'POST - Disease prediction',
            '/api/chat/conversations/<user_id>': 'GET - User conversations',
            '/api/users/online': 'GET - Online users'
        }
    })


@app.route('/api/health')
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model_loaded,
        'online_users': len(chat_manager.get_online_users())
    })


@app.route('/api/predict', methods=['POST'])
def predict():
    """Predict disease from uploaded image"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    try:
        image = Image.open(io.BytesIO(file.read()))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        import uuid
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(filepath)
        
        if model_loaded and predictor:
            result = predict_image(image)
            result['image_id'] = filename
            result['model_loaded'] = True
        else:
            result = {
                'success': True,
                'image_id': filename,
                'model_loaded': False,
                'message': 'Model is still training.',
                'predictions': []
            }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/predict-base64', methods=['POST'])
def predict_base64():
    """Predict from base64 image"""
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': 'No image data'}), 400
        
        image_data = data['image']
        if 'base64,' in image_data:
            image_data = image_data.split('base64,')[1]
        
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        if model_loaded and predictor:
            result = predict_image(image)
            result['model_loaded'] = True
        else:
            result = {
                'success': True,
                'model_loaded': False,
                'message': 'Model is still training.',
                'predictions': []
            }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def predict_image(image):
    """Make prediction"""
    import numpy as np
    
    image = image.resize((224, 224))
    img_array = np.array(image)
    img_array = img_array.astype(np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    
    predictions = predictor['model'].predict(img_array, verbose=0)[0]
    top_indices = np.argsort(predictions)[::-1][:3]
    
    results = {'success': True, 'predictions': []}
    
    for idx in top_indices:
        class_name = predictor['idx_to_class'][idx]
        confidence = float(predictions[idx])
        
        disease_data = DISEASE_INFO.get(class_name, {
            'name': class_name.replace('___', ' - ').replace('_', ' '),
            'symptoms': 'Information not available',
            'solution': 'Consult an agricultural expert',
            'prevention': 'Practice good agricultural methods',
            'severity': 'Unknown'
        })
        
        results['predictions'].append({
            'class_name': class_name,
            'disease': disease_data['name'],
            'confidence': round(confidence * 100, 2),
            'symptoms': disease_data['symptoms'],
            'solution': disease_data['solution'],
            'prevention': disease_data['prevention'],
            'severity': disease_data['severity']
        })
    
    results['primary_prediction'] = results['predictions'][0]
    return results


@app.route('/api/chat/conversations/<user_id>')
def get_conversations(user_id):
    """Get all conversations for a user"""
    conversations = chat_manager.get_user_conversations(user_id)
    return jsonify({'success': True, 'conversations': conversations})


@app.route('/api/users/online')
def get_online_users():
    """Get list of online users"""
    return jsonify({
        'success': True,
        'online_users': chat_manager.get_online_users()
    })


@app.route('/api/model-status')
def model_status():
    """Check model status"""
    status = {
        'model_exists': os.path.exists(MODEL_PATH),
        'model_loaded': model_loaded
    }
    
    if status['model_exists']:
        status['model_size_mb'] = round(os.path.getsize(MODEL_PATH) / (1024 * 1024), 2)
    
    return jsonify(status)


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("SMART CROP API + REAL-TIME CHAT")
    print("="*60)
    
    print(f"\nModel Status: {'LOADED' if model_loaded else 'TRAINING'}")
    print("Chat System: ACTIVE")
    print(f"Online Users: {len(chat_manager.get_online_users())}")
    
    print("\nServer: http://localhost:5000")
    print("WebSocket: ws://localhost:5000")
    
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)