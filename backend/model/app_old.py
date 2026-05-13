"""
Smart Crop AI - Production API
Flask backend with leaf validation, disease detection, and AI chat.
"""

import sys
import os

# Ensure parent directory is in path so 'model' imports work correctly
# (Flask reloader can change cwd, so we explicitly set the path)
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, create_access_token
import json
import uuid
import re
from datetime import datetime, timedelta
from PIL import Image
import io
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

# â”€â”€ APP CONFIG â”€â”€
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///AgrosightAI.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'AgrosightAI-dev-secret-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# â”€â”€ INIT DB & JWT â”€â”€
from database import db, User, init_app as init_db, create_user, authenticate_user, get_user_by_id
from database import save_detection, get_detections_for_user, get_detection_by_id, delete_detection
from database import save_message, get_conversation_messages, get_conversations_for_user, mark_conversation_read, get_unread_count
from database import save_activity, get_activities_for_user
from database import save_feedback, get_all_users, get_user_stats

init_db(app)
jwt = JWTManager(app)

# â”€â”€ IMPORT MODULES (conditional) â”€â”€
PREDICTOR_AVAILABLE = False
LEAF_DETECTOR_AVAILABLE = False
DiseasePredictor = None
LeafDetector = None

try:
    from model.predict import DiseasePredictor
    PREDICTOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DiseasePredictor not available: {e}")

try:
    from model.leaf_detector import LeafDetector
    LEAF_DETECTOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"LeafDetector not available: {e}")

# â”€â”€ DISEASE INFO LOOKUP (shared by all predictors) â”€â”€
DISEASE_INFO = {}
try:
    _db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'disease_database.json')
    if os.path.exists(_db_path):
        with open(_db_path, 'r', encoding='utf-8') as f:
            DISEASE_INFO = json.load(f)
        logger.info(f"Loaded disease database: {len(DISEASE_INFO)} entries")
except Exception as e:
    logger.warning(f"Could not load disease database: {e}")

# â”€â”€ PYTORCH IMPORTS (conditional) â”€â”€
PYTORCH_AVAILABLE = False
DiseasePredictorPyTorch = None

try:
    from inference_pytorch import DiseasePredictorPyTorch
    PYTORCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyTorch inference not available: {e}")

# â”€â”€ PATHS â”€â”€
MODEL_PATH = 'saved_models/best_model.keras'
CLASS_INDICES_PATH = 'saved_models/class_indices.json'
DISEASE_INFO_PATH = 'saved_models/disease_info.json'
LEAF_DETECTOR_PATH = 'saved_models/leaf_detector.keras'
LEAF_DETECTOR_CONFIG = 'saved_models/leaf_detector_config.json'
PYTORCH_MODEL_DIR = 'saved_models_pytorch'
PYTORCH_MODEL_PATH = os.path.join(PYTORCH_MODEL_DIR, 'best_model.pth')
PYTORCH_CLASS_NAMES = os.path.join(PYTORCH_MODEL_DIR, 'class_names.json')
PYTORCH_PREPROCESS = os.path.join(PYTORCH_MODEL_DIR, 'preprocess_config.json')
FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'feedback.json')

# â”€â”€ LOAD MODELS â”€â”€
predictor = None
leaf_detector = None
model_loaded = False
leaf_model_loaded = False
model_engine = 'Mock'

class PyTorchDiseaseWrapper:
    """Wrap PyTorch predictor to match the existing Keras predictor interface."""
    def __init__(self, pytorch_predictor):
        self.pt = pytorch_predictor

    def predict(self, image):
        """image is a PIL Image. Returns dict matching Keras predictor shape."""
        result = self.pt.predict_pil(image, top_k=3)
        pred_class = result['predicted_class']
        conf = result['confidence']
        is_healthy = 'healthy' in pred_class.lower()
        # Try to map to existing disease_info if available
        disease_info = DISEASE_INFO.get(pred_class, {})
        return {
            'success': True,
            'is_leaf': True,
            'crop': self._extract_crop(pred_class),
            'disease': pred_class,
            'confidence': conf,
            'severity': disease_info.get('severity', 'Moderate'),
            'symptoms': disease_info.get('symptoms', ['No specific symptoms listed.']),
            'causes': disease_info.get('causes', 'Cause information not available.'),
            'recommendation': disease_info.get('recommendation', ['Consult a local extension officer.']),
            'prevention': disease_info.get('prevention', 'Prevention information not available.'),
            'is_healthy': is_healthy,
            'message': 'You can ask me any question about this result or your crop.',
            'predictions': result['top_k'],
        }

    @staticmethod
    def _extract_crop(class_name):
        """Infer crop name from class string like 'Tomato___Early_Blight'."""
        if '___' in class_name:
            return class_name.split('___')[0].replace('_', ' ').title()
        parts = class_name.split()
        if parts:
            return parts[0]
        return 'Unknown'


def load_models():
    global predictor, leaf_detector, model_loaded, leaf_model_loaded, model_engine

    # â”€â”€ Try PyTorch first â”€â”€
    if PYTORCH_AVAILABLE and os.path.exists(PYTORCH_MODEL_PATH) and os.path.exists(PYTORCH_CLASS_NAMES):
        try:
            pt_predictor = DiseasePredictorPyTorch(
                model_path=PYTORCH_MODEL_PATH,
                class_names_path=PYTORCH_CLASS_NAMES,
                preprocess_path=PYTORCH_PREPROCESS if os.path.exists(PYTORCH_PREPROCESS) else None,
                model_name='mobilenetv2'
            )
            predictor = PyTorchDiseaseWrapper(pt_predictor)
            model_loaded = True
            model_engine = 'PyTorch'
            logger.info("PyTorch disease model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load PyTorch model: {e}")

    # â”€â”€ Fall back to Keras â”€â”€
    if predictor is None and PREDICTOR_AVAILABLE and os.path.exists(MODEL_PATH) and os.path.exists(CLASS_INDICES_PATH):
        try:
            predictor = DiseasePredictor(
                model_path=MODEL_PATH,
                class_indices_path=CLASS_INDICES_PATH,
                disease_info_path=DISEASE_INFO_PATH if os.path.exists(DISEASE_INFO_PATH) else None
            )
            model_loaded = True
            model_engine = 'Keras'
            logger.info("Keras disease model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Keras disease model: {e}")

    if predictor is None:
        logger.warning("No disease model loaded. Using mock predictions.")

    # â”€â”€ Leaf detector â”€â”€
    if LEAF_DETECTOR_AVAILABLE:
        try:
            leaf_detector = LeafDetector(
                model_path=LEAF_DETECTOR_PATH,
                config_path=LEAF_DETECTOR_CONFIG,
                threshold=0.7
            )
            leaf_model_loaded = leaf_detector.model is not None
        except Exception as e:
            logger.warning(f"Leaf detector not loaded: {e}")
    else:
        logger.warning("LeafDetector module not available.")

load_models()

# â”€â”€ UTILITIES â”€â”€
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def decode_image(data):
    """Decode base64 string or raw bytes into PIL Image."""
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
    """Save image to uploads folder for record keeping."""
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(filepath, 'JPEG', quality=90)
    return filepath, filename


def current_user_id():
    """Return the authenticated user ID from JWT if present, else None."""
    try:
        from flask_jwt_extended import verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        return int(identity) if identity else None
    except Exception:
        return None


# â”€â”€ MOCK DATA GENERATORS â”€â”€
def get_mock_leaf_result(is_leaf=True):
    if is_leaf:
        return {'is_leaf': True, 'confidence': 0.95, 'method': 'mock', 'message': 'Leaf detected (mock).'}
    return {'is_leaf': False, 'confidence': 0.12, 'method': 'mock', 'message': 'This is not a plant leaf. Please upload a clear leaf image.'}

def get_mock_disease_prediction():
    pred = {
        'success': True,
        'is_leaf': True,
        'crop': 'Tomato',
        'disease': 'Tomato Early Blight',
        'confidence': 0.87,
        'severity': 'Moderate',
        'symptoms': [
            'Dark brown spots with concentric rings (bull\'s eye pattern)',
            'Yellowing of lower leaves',
            'Premature leaf drop in severe cases'
        ],
        'causes': 'Fungal infection caused by Alternaria solani, favored by warm temperatures (24-29C), high humidity, and plant stress from poor nutrition or drought.',
        'recommendation': [
            'Remove and destroy infected lower leaves immediately',
            'Apply fungicide containing chlorothalonil or mancozeb every 7-10 days',
            'Improve air circulation by spacing plants properly and pruning dense foliage',
            'Mulch around the base to prevent soil splash onto leaves'
        ],
        'prevention': 'Crop rotation, proper plant spacing, avoid wetting foliage, mulch around plants.',
        'is_healthy': False,
        'message': 'You can ask me any question about this result or your crop.',
        'predictions': [],
        'mock': True
    }
    pred['primary_prediction'] = pred.copy()
    pred['primary_prediction'].pop('predictions', None)
    pred['primary_prediction'].pop('primary_prediction', None)
    return pred

def get_mock_healthy_prediction():
    pred = {
        'success': True,
        'is_leaf': True,
        'crop': 'Tomato',
        'disease': 'Healthy Tomato',
        'confidence': 0.94,
        'severity': 'None',
        'symptoms': ['No disease detected - plant appears healthy with green leaves and normal growth.'],
        'causes': 'No disease detected. The plant appears to be in good health.',
        'recommendation': [
            'Continue good agricultural practices',
            'Monitor regularly for early signs of disease',
            'Maintain proper watering and fertilization schedules'
        ],
        'prevention': 'Maintain regular monitoring, proper fertilization and watering.',
        'is_healthy': True,
        'message': 'You can ask me any question about this result or your crop.',
        'predictions': [],
        'mock': True
    }
    pred['primary_prediction'] = pred.copy()
    pred['primary_prediction'].pop('predictions', None)
    pred['primary_prediction'].pop('primary_prediction', None)
    return pred

# â”€â”€ AI CHAT KNOWLEDGE BASE â”€â”€
CHAT_RESPONSES = {
    'greeting': [
        "Hello! I am your Smart Crop AI Assistant. I help farmers in Uganda and East Africa with crop diseases, pests, soil, and farming advice. How can I help you today?",
        "Hi there! I am here to give you practical farming advice suited for our East African climate and soils. What would you like to know?"
    ],
    'prevention': [
        "Prevention tips:\n\nâ€¢ Use certified, disease-free seeds\nâ€¢ Practice crop rotation every season\nâ€¢ Keep proper spacing between plants for air flow\nâ€¢ Make sure your field has good drainage\nâ€¢ Check your crops regularly for early signs of disease\nâ€¢ Remove and burn infected plant parts quickly",
        "To stop disease before it starts:\n\nâ€¢ Rotate crops yearly (do not plant the same crop in the same place)\nâ€¢ Use resistant seed varieties when available\nâ€¢ Clean your tools after use\nâ€¢ Avoid watering leaves directly; water at the base\nâ€¢ Walk through your farm at least once a week to spot problems early"
    ],
    'treatment': [
        "Treatment steps you can follow:\n\nâ€¢ First, confirm the disease by looking at the symptoms or uploading a leaf photo\nâ€¢ For fungal diseases: apply recommended fungicide (e.g., mancozeb or chlorothalonil) as directed\nâ€¢ For bacterial diseases: use copper-based sprays\nâ€¢ For viral diseases: remove and destroy infected plants; there is no chemical cure\nâ€¢ Always follow the instructions on the chemical label\nâ€¢ If unsure, consult a local agricultural extension officer",
        "Step-by-step treatment:\n\n1. Identify the exact disease or pest\n2. Remove badly infected leaves or plants and burn them\n3. Apply the right chemical or organic remedy (neem, ash, or recommended pesticide)\n4. Repeat treatment as advised on the label\n5. Watch the crop for improvement over 7â€“14 days\n6. If the problem continues, ask an agro-vet or extension officer for help"
    ],
    'fertilizer': [
        "Fertilizer advice for East African soils:\n\nâ€¢ Test your soil if possible to know what nutrients are missing\nâ€¢ Apply NPK fertilizer based on the crop needs (maize needs more nitrogen)\nâ€¢ Add compost or well-rotted manure to improve soil structure\nâ€¢ Do not over-use nitrogen; it can make plants weak to disease\nâ€¢ Consider micronutrients like zinc for maize and boron for legumes",
        "How to fertilize properly:\n\nâ€¢ Basal application: mix fertilizer into the soil at planting\nâ€¢ Top-dress: add more nitrogen (e.g., urea) when the crop is knee-high\nâ€¢ Use organic matter (compost, manure) alongside chemical fertilizer\nâ€¢ Apply fertilizer when the soil is moist, then light-irrigate if possible"
    ],
    'water': [
        "Water and irrigation tips:\n\nâ€¢ Water early in the morning to reduce leaf wetness and disease\nâ€¢ Use drip irrigation or water at the base of plants if you can\nâ€¢ Do not let water stand in the field; good drainage prevents root rot\nâ€¢ Adjust watering based on rainfallâ€”do not over-water during rainy season\nâ€¢ For dry seasons, mulch around plants to keep soil moist",
        "Proper watering:\n\nâ€¢ Give a deep soak rather than light sprinkles\nâ€¢ Avoid wetting leaves, especially in the evening\nâ€¢ If using a watering can, direct water to the roots\nâ€¢ During drought, prioritize water for young plants and flowering crops"
    ],
    'chemicals': [
        "Safe chemical use:\n\nâ€¢ Always read and follow the label instructions\nâ€¢ Wear protective clothing (gloves, long sleeves, mask if possible)\nâ€¢ Do not spray near rivers, wells, or water sources\nâ€¢ Observe the pre-harvest interval (wait the recommended days before eating/selling)\nâ€¢ Store chemicals locked away, out of reach of children and animals\nâ€¢ If you are unsure which chemical to use, ask an agro-vet",
        "Pesticide and fungicide safety:\n\nâ€¢ Mix only the amount you need for that day\nâ€¢ Spray when the weather is calm (little wind) to avoid drift\nâ€¢ Wash hands and face after spraying\nâ€¢ Keep spray equipment clean and in good condition"
    ],
    'healthy': [
        "Your plant looks healthy! To keep it that way:\n\nâ€¢ Continue regular monitoring\nâ€¢ Water properly and fertilize on schedule\nâ€¢ Watch for any new spots, wilting, or pests\nâ€¢ Maintain good weed control around the crop",
        "Good newsâ€”the plant appears healthy. Keep up:\n\nâ€¢ Balanced nutrition and timely watering\nâ€¢ Field hygiene (remove weeds and crop residues)\nâ€¢ Early scouting so you catch problems before they spread"
    ],
    'uncertain': [
        "I am not fully certain about that specific issue.\n\nI recommend:\nâ€¢ Upload a clear photo of the affected leaf or plant part for a better diagnosis\nâ€¢ Or visit a local agricultural extension officer or registered agro-vet for in-person advice",
        "That is a complex question, and I want to give you accurate advice.\n\nPlease:\nâ€¢ Share more details (crop type, stage, weather, what you have already tried)\nâ€¢ Or upload an image so I can look at the symptoms directly\nâ€¢ If the problem is urgent, consult a local extension officer today."
    ]
}

def build_chat_response(message, last_detection=None):
    """Build contextual AI chat response tailored for East African farmers."""
    msg = (message or '').strip().lower()

    if not msg:
        return "Hello! I am your Smart Crop AI Assistant. I help farmers in Uganda and East Africa with crop diseases, pests, soil, and farming advice. Upload a plant image for diagnosis or ask me anything about your farm."

    # Contextual responses based on last detection
    if last_detection:
        disease = last_detection.get('disease', '')
        is_healthy = last_detection.get('is_healthy', False)
        prevention = last_detection.get('prevention', '')
        recommendation = last_detection.get('recommendation', [])
        causes = last_detection.get('causes', '')
        symptoms = last_detection.get('symptoms', [])

        if any(k in msg for k in ['prevent', 'avoid', 'stop', 'future']):
            steps = prevention if prevention else "Practice crop rotation, use certified seeds, and keep the field clean."
            return f"To prevent {disease} in the future:\n\n{steps}\n\nIf you need specific steps for your crop variety, ask me or consult a local agricultural extension officer."

        if any(k in msg for k in ['treat', 'cure', 'fix', 'solve', 'step by step', 'what should i do', 'how do i treat', 'recommendation']):
            steps = '\n'.join([f'{i+1}. {r}' for i, r in enumerate(recommendation[:5])])
            return f"Here is a step-by-step treatment plan for {disease}:\n\n{steps}\n\nFollow the advice carefully, and if the problem does not improve in 10â€“14 days, visit a local agro-vet or extension officer."

        if any(k in msg for k in ['symptom', 'sign', 'look like', 'why', 'cause']):
            symp_text = '\n'.join([f'â€¢ {s}' for s in symptoms[:5]])
            return f"Symptoms of {disease}:\n\n{symp_text}\n\nCauses:\n{causes}\n\nThese symptoms usually spread during warm, wet weatherâ€”common in our Ugandan rainy seasons. Early action is important."

        if any(k in msg for k in ['last', 'recent', 'previous', 'that disease', 'my detection', 'my result', 'this disease']):
            conf = last_detection.get('confidence', 0)
            sev = last_detection.get('severity', 'Unknown')
            return f"Your last detection was **{disease}** with {conf*100:.1f}% confidence. Severity: {sev}.\n\nIf you want treatment steps or prevention tips, just ask."

        if any(k in msg for k in ['healthy', 'good', 'fine', 'normal']):
            if is_healthy:
                return "Your plant is healthy! Keep up with regular monitoring, proper watering, and balanced nutrition. In our climate, also watch for sudden changes during the rainy season."
            return f"Your detected condition ({disease}) needs attention. Follow the treatment steps I shared, and monitor the crop closely over the next two weeks."

    # General responses with East African farming focus
    if any(k in msg for k in ['hello', 'hi', 'hey', 'greetings']):
        return "Hello! I am your Smart Crop AI Assistant. I help farmers in Uganda and East Africa with practical crop advice. How can I help you today?"

    if any(k in msg for k in ['thank', 'thanks']):
        return "You are very welcome! I am here whenever you need farming advice. Wishing you a good harvest!"

    if any(k in msg for k in ['symptom', 'sign', 'look like']):
        return "Common symptoms in our region include:\n\nâ€¢ Leaf spots or brown patches\nâ€¢ Yellowing or wilting leaves\nâ€¢ White or gray mold on leaves\nâ€¢ Stunted growth or falling fruit\nâ€¢ Holes in leaves from pests\n\nUpload a clear photo of the affected leaf for a more accurate diagnosis."

    if any(k in msg for k in ['treatment', 'cure', 'fix', 'solve', 'medicine']):
        return "Treatments depend on the exact disease or pest. In general:\n\nâ€¢ Fungal diseases: use recommended fungicide (e.g., mancozeb, chlorothalonil)\nâ€¢ Bacterial diseases: apply copper-based sprays\nâ€¢ Viral diseases: remove infected plants; there is no chemical cure\nâ€¢ Pests: neem extract, biological control, or targeted insecticide\n\nFor step-by-step guidance, tell me which crop and disease you are dealing with, or upload an image."

    if any(k in msg for k in ['prevent', 'avoid', 'stop']):
        return "Prevention tips for East African farms:\n\nâ€¢ Use certified, disease-free seeds\nâ€¢ Rotate crops every season\nâ€¢ Keep proper spacing for air circulation\nâ€¢ Ensure good drainageâ€”do not let water stand\nâ€¢ Remove and burn infected plant material quickly\nâ€¢ Scout your farm weekly for early signs"

    if any(k in msg for k in ['fungicide', 'pesticide', 'chemical', 'spray']):
        return "Safe chemical use:\n\nâ€¢ Always read the label and follow instructions\nâ€¢ Wear gloves and protective clothing\nâ€¢ Spray during calm weather, not when windy\nâ€¢ Do not spray near rivers or wells\nâ€¢ Observe the waiting period before harvest\nâ€¢ Store chemicals away from children and animals\nâ€¢ If unsure which chemical to buy, ask a registered agro-vet."

    if any(k in msg for k in ['water', 'irrigate', 'rain']):
        return "Water management in Uganda and East Africa:\n\nâ€¢ Water early in the morning to reduce disease\nâ€¢ Use drip or basin irrigation when possible\nâ€¢ Do not over-water during rainy season\nâ€¢ Mulch around plants to keep moisture during dry spells\nâ€¢ Make sure the field drains well to prevent root rot"

    if any(k in msg for k in ['fertilizer', 'nutrient', 'soil']):
        return "Soil and fertilizer advice:\n\nâ€¢ Test your soil if possible to know what is lacking\nâ€¢ Apply NPK fertilizer based on crop needs\nâ€¢ Add compost or manure to improve soil health\nâ€¢ Top-dress nitrogen (urea) when the crop is actively growing\nâ€¢ Avoid too much nitrogenâ€”it makes plants soft and prone to disease\nâ€¢ In many parts of Uganda, soils are low in zinc and boron; consider micronutrient supplements"

    if any(k in msg for k in ['rust']):
        return "Rust diseases in our region:\n\nâ€¢ Look for reddish-brown pustules on leaves and stems\nâ€¢ Common on maize, beans, and coffee\nâ€¢ Treatment: apply fungicide (e.g., mancozeb), remove infected leaves, and use resistant varieties\nâ€¢ Plant at the right time to avoid peak disease weather"

    if any(k in msg for k in ['powdery mildew', 'white spot', 'mildew']):
        return "Powdery Mildew:\n\nâ€¢ White, powdery coating on leaves, common in warm, humid conditions\nâ€¢ Treatment: sulfur-based fungicide, neem oil, or milk spray (1 part milk to 9 parts water)\nâ€¢ Improve air circulation by pruning and spacing plants\nâ€¢ Avoid overhead watering, especially in the evening"

    if any(k in msg for k in ['blight', 'rot']):
        return "Blight and rot diseases:\n\nâ€¢ Cause wilting, browning, and sudden plant death\nâ€¢ Common during rainy season when humidity is high\nâ€¢ Treatment: remove infected plants, apply copper fungicide, improve drainage\nâ€¢ Prevention: rotate crops, use certified seed, avoid planting in waterlogged areas"

    if any(k in msg for k in ['armyworm', 'pest', 'worm', 'insect', 'fall armyworm']):
        return "Fall Armyworm and other pest control:\n\nâ€¢ Scout your maize field regularly, especially in the first 40 days\nâ€¢ Early planting can reduce damage\nâ€¢ Neem extract and wood ash are affordable organic options\nâ€¢ Biological control: Trichogramma wasps can help\nâ€¢ If infestation is severe, use a recommended insecticide and follow the label exactly\nâ€¢ Report severe outbreaks to your local extension officer"

    if any(k in msg for k in ['maize', 'corn']):
        return "Maize farming tips for Uganda:\n\nâ€¢ Plant at the start of the rainy season for best germination\nâ€¢ Use certified hybrids suited for your agro-ecological zone\nâ€¢ Space plants 75 cm between rows and 25 cm within rows\nâ€¢ Apply DAP or NPK at planting; top-dress with urea at knee height\nâ€¢ Watch for Fall Armyworm, streak virus, and rust\nâ€¢ Harvest when husks turn brown and grain is hard"

    if any(k in msg for k in ['beans', 'groundnut', 'soybean', 'legume']):
        return "Legume crops (beans, groundnuts, soybeans):\n\nâ€¢ Fix nitrogen in the soil, which helps the next crop\nâ€¢ Inoculate seeds with rhizobium if available\nâ€¢ Avoid waterlogging; beans do not like wet feet\nâ€¢ Watch for bean fly, aphids, and anthracnose\nâ€¢ Harvest when pods are dry to prevent mold in storage"

    if any(k in msg for k in ['coffee']):
        return "Coffee care:\n\nâ€¢ Shade-grown coffee often has fewer disease problems\nâ€¢ Watch for coffee wilt disease and leaf rust\nâ€¢ Prune regularly for air flow and easier picking\nâ€¢ Apply organic mulch to retain soil moisture\nâ€¢ Harvest only ripe cherries for better quality and price"

    if any(k in msg for k in ['banana', 'matoke', 'plantain']):
        return "Banana (Matoke) farming:\n\nâ€¢ Use suckers from healthy, disease-free mother plants\nâ€¢ Watch for Banana Xanthomonas Wilt (BXW)â€”cut and bury infected plants\nâ€¢ Remove male buds to reduce weevil and disease spread\nâ€¢ Apply manure or compost around the base regularly\nâ€¢ Keep the plantation weed-free"

    if any(k in msg for k in ['cassava']):
        return "Cassava tips:\n\nâ€¢ Plant stem cuttings (stakes) from healthy, mature plants\nâ€¢ Watch for cassava brown streak disease and mosaic virus\nâ€¢ Do not plant cassava in the same field year after year; rotate with legumes\nâ€¢ Harvest at 9â€“12 months depending on variety\nâ€¢ Handle stakes carefully to avoid bruising and infection"

    if any(k in msg for k in ['rice']):
        return "Rice farming:\n\nâ€¢ Use certified seed and level the field for even water coverage\nâ€¢ Transplant or direct-seed at the right time for your area\nâ€¢ Keep water level 3â€“5 cm during early growth\nâ€¢ Drain the field before applying top-dress fertilizer\nâ€¢ Watch for blast disease and stem borer\nâ€¢ Harvest when 80â€“85% of grains are golden yellow"

    if any(k in msg for k in ['tomato']):
        return "Tomato farming:\n\nâ€¢ Start with certified seedlings\nâ€¢ Stake or trellis plants to keep fruit off the ground\nâ€¢ Avoid wetting leaves; drip irrigation is best\nâ€¢ Watch for bacterial wilt, early blight, and whiteflies\nâ€¢ Practice crop rotationâ€”do not plant tomatoes after peppers or potatoes\nâ€¢ Harvest when fruit is firm and fully colored"

    if any(k in msg for k in ['healthy', 'good', 'fine', 'normal']):
        return "Your plant looks healthy! Keep up with:\n\nâ€¢ Regular field scouting\nâ€¢ Proper watering and balanced nutrition\nâ€¢ Weed control and field hygiene\nâ€¢ Early action if you notice any change"

    # Default uncertain response with safety net
    return "I want to make sure I give you accurate advice.\n\nPlease try one of these:\nâ€¢ Upload a clear leaf or plant photo for diagnosis\nâ€¢ Tell me the exact crop name and what you are seeing\nâ€¢ Or visit your local agricultural extension officer for hands-on help\n\nI am here to support you with reliable farming information."

# â”€â”€ HOME â”€â”€
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'success',
        'message': 'Smart Crop AI - Disease Detection API',
        'version': '2.0.0',
        'model_loaded': model_loaded,
        'leaf_detector_loaded': leaf_model_loaded,
        'endpoints': {
            '/api/analyze': 'POST - Full pipeline: leaf check + disease detection + structured result',
            '/api/chat': 'POST - AI assistant with contextual follow-up',
            '/api/auth/register': 'POST - Create account',
            '/api/auth/login': 'POST - Log in and get token',
            '/api/auth/me': 'GET/PUT - View or update profile',
            '/api/detections': 'GET - Your detection history',
            '/api/messages': 'POST - Send a message',
            '/api/messages/conversations': 'GET - Your conversations',
            '/api/messages/<conv_id>': 'GET - Conversation messages',
            '/api/activity': 'GET - Your activity timeline',
            '/api/users/farmers': 'GET - List farmers',
            '/api/users/agrovets': 'GET - List agro-vets',
            '/api/feedback': 'POST - Submit prediction feedback',
            '/api/health': 'GET - Health check',
            '/api/model-status': 'GET - Model training status'
        }
    })

# â”€â”€ HEALTH â”€â”€
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'model_loaded': model_loaded,
        'leaf_detector_loaded': leaf_model_loaded,
        'timestamp': datetime.now().isoformat()
    })

# â”€â”€ MAIN ANALYZE ENDPOINT â”€â”€
@app.route('/api/analyze', methods=['POST'])
def analyze():
    """
    Full analysis pipeline:
    1. Decode image
    2. Leaf detection
    3. Disease classification
    4. Structured response
    """
    try:
        data = request.get_json() or {}
        image_data = data.get('image')

        if not image_data:
            return jsonify({
                'success': False,
                'is_leaf': False,
                'message': 'No image data provided.'
            }), 400

        # Decode image
        try:
            image = decode_image(image_data)
        except Exception as e:
            logger.error(f"Image decode error: {e}")
            return jsonify({
                'success': False,
                'is_leaf': False,
                'message': 'Invalid image data. Please upload a valid image file.'
            }), 400

        # Save for records
        try:
            filepath, filename = save_upload(image)
            logger.info(f"Image saved: {filename}")
        except Exception:
            filename = None

        # â”€â”€ STEP 1: LEAF DETECTION â”€â”€
        if leaf_detector is not None and LEAF_DETECTOR_AVAILABLE:
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

        # â”€â”€ STEP 2: DISEASE CLASSIFICATION â”€â”€
        result = None
        if model_loaded and predictor is not None and PREDICTOR_AVAILABLE:
            try:
                result = predictor.predict(image)
                result['leaf_check'] = leaf_result
                if filename:
                    result['image_id'] = filename
                logger.info(f"Prediction: {result.get('disease')} ({result.get('confidence')})")
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                # Fall through to mock

        if result is None:
            import random
            result = get_mock_healthy_prediction() if random.random() > 0.5 else get_mock_disease_prediction()
            result['leaf_check'] = leaf_result
            if filename:
                result['image_id'] = filename
            logger.info("Returning mock prediction")

        # Persist to database if user is authenticated
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
        return jsonify({
            'success': False,
            'is_leaf': False,
            'message': f'Server error: {str(e)}'
        }), 500

# â”€â”€ CHAT ENDPOINT â”€â”€
@app.route('/api/chat', methods=['POST'])
def chat():
    """
    AI Chat with contextual follow-up.
    Accepts user question + optional previous detection result for context.
    """
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        last_detection = data.get('last_detection')
        user_history = data.get('user_history', [])

        response_text = build_chat_response(message, last_detection)

        return jsonify({
            'success': True,
            'message': response_text,
            'context': {
                'has_detection': last_detection is not None,
                'detection_disease': last_detection.get('disease') if last_detection else None
            }
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({
            'success': False,
            'message': 'Sorry, I encountered an error. Please try again.'
        }), 500

# â”€â”€ LEGACY ENDPOINTS â”€â”€
@app.route('/api/classes', methods=['GET'])
def get_classes():
    if predictor:
        classes = list(predictor.class_indices.keys())
        return jsonify({'status': 'success', 'num_classes': len(classes), 'classes': classes})
    return jsonify({'status': 'error', 'message': 'Model not loaded'}), 500

@app.route('/api/predict', methods=['POST'])
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

@app.route('/api/predict-base64', methods=['POST'])
def predict_base64():
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400

        image = decode_image(data['image'])

        if model_loaded and predictor:
            results = predictor.predict(image)
        else:
            results = get_mock_disease_prediction()
        return jsonify(results)
    except Exception as e:
        logger.error(f"Base64 prediction error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/batch-predict', methods=['POST'])
def batch_predict():
    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    results = []
    for file in files:
        if file and allowed_file(file.filename):
            try:
                image = Image.open(io.BytesIO(file.read()))
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                if model_loaded and predictor:
                    result = predictor.predict(image)
                else:
                    result = get_mock_disease_prediction()
                result['filename'] = file.filename
                results.append(result)
            except Exception as e:
                results.append({'filename': file.filename, 'success': False, 'error': str(e)})

    return jsonify({'success': True, 'count': len(results), 'results': results})

# â”€â”€ ASSISTANT (LEGACY) â”€â”€
@app.route('/api/assistant', methods=['POST'])
def assistant():
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        last_detection = data.get('last_detection')
        response_text = build_chat_response(message, last_detection)
        return jsonify({'success': True, 'result': {'response': response_text}})
    except Exception as e:
        logger.error(f"Assistant error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# â”€â”€ FEEDBACK â”€â”€
@app.route('/api/feedback', methods=['POST'])
def feedback():
    try:
        data = request.get_json() or {}
        predicted = data.get('predicted_class', 'unknown')
        correct = data.get('correct_class', 'unknown')
        confidence = data.get('confidence', 0)

        entry = {
            'id': str(uuid.uuid4()),
            'predicted_class': predicted,
            'correct_class': correct,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'source': 'user_feedback'
        }

        os.makedirs(os.path.dirname(FEEDBACK_PATH), exist_ok=True)
        existing = []
        if os.path.exists(FEEDBACK_PATH):
            try:
                with open(FEEDBACK_PATH, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        existing.append(entry)
        with open(FEEDBACK_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)

        # Also save to database
        uid = current_user_id()
        try:
            fb = save_feedback(
                user_id=uid,
                predicted_class=predicted,
                correct_class=correct,
                confidence=confidence,
            )
            entry['db_id'] = fb.id
        except Exception as db_err:
            logger.warning(f"Could not save feedback to DB: {db_err}")

        return jsonify({'success': True, 'message': 'Feedback saved', 'feedback_id': entry['id']})
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# â”€â”€ MODEL STATUS â”€â”€
@app.route('/api/model-status', methods=['GET'])
def model_status():
    try:
        training_results_path = os.path.join(os.path.dirname(__file__), '..', 'saved_models', 'training_results.json')
        training_status = None
        if os.path.exists(training_results_path):
            try:
                with open(training_results_path, 'r', encoding='utf-8') as f:
                    training_status = json.load(f)
            except Exception:
                pass

        return jsonify({
            'success': True,
            'model_loaded': model_loaded,
            'leaf_detector_loaded': leaf_model_loaded,
            'model_path': MODEL_PATH if os.path.exists(MODEL_PATH) else None,
            'class_indices_loaded': os.path.exists(CLASS_INDICES_PATH),
            'num_classes': len(predictor.class_indices) if predictor else 0,
            'training_status': training_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# â”€â”€ AUTH ENDPOINTS â”€â”€
@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password', '')
        phone = (data.get('phone') or '').strip() or None
        role = (data.get('role') or 'farmer').strip().lower()
        location = (data.get('location') or '').strip() or None

        if not username or not email or not password:
            return jsonify({'success': False, 'message': 'Username, email, and password are required.'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters.'}), 400
        if role not in ('farmer', 'agrovet', 'admin'):
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
def login():
    try:
        data = request.get_json() or {}
        identifier = (data.get('identifier') or data.get('email') or data.get('phone') or '').strip()
        username = (data.get('username') or '').strip()
        password = data.get('password', '')

        if not identifier or not username or not password:
            return jsonify({'success': False, 'message': 'Identifier, username, and password are required.'}), 400

        user, err = authenticate_user(identifier, username, password)
        if err:
            return jsonify({'success': False, 'message': err}), 401

        token = create_access_token(identity=str(user.id))
        return jsonify({'success': True, 'token': token, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Login error: {e}")
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
            user.phone = data['phone']
        if 'location' in data:
            user.location = data['location']
        if 'profile_picture' in data:
            user.profile_picture = data['profile_picture']
        if 'email' in data:
            existing = User.query.filter(User.email == data['email'], User.id != uid).first()
            if existing:
                return jsonify({'success': False, 'message': 'Email already in use.'}), 409
            user.email = data['email']

        db.session.commit()
        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        logger.error(f"Update me error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# â”€â”€ DETECTIONS CRUD â”€â”€
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


# â”€â”€ MESSAGES CRUD â”€â”€
@app.route('/api/messages', methods=['POST'])
@jwt_required()
def create_message():
    try:
        uid = int(get_jwt_identity())
        data = request.get_json() or {}
        receiver_id = data.get('receiver_id')
        text = data.get('text', '')
        type = data.get('type', 'text')
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
        # Sort by last message time descending
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


# â”€â”€ ACTIVITY CRUD â”€â”€
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


# â”€â”€ USERS (ADMIN / DIRECTORY) â”€â”€
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


# â”€â”€ ERROR HANDLERS â”€â”€
@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'error': 'File is too large. Maximum size is 16MB.'}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# â”€â”€ MAIN â”€â”€
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Smart Crop AI - Disease Detection API")
    print("=" * 60)
    print(f"\nDisease Model: {model_engine} ({'loaded' if model_loaded else 'not loaded'})")
    print(f"Leaf Detector: {'Loaded' if leaf_model_loaded else 'Not loaded (heuristic/mock mode)'}")
    print("\nAPI will be available at: http://localhost:5000")
    print("Main endpoint: POST /api/analyze")
    print("Chat endpoint: POST /api/chat")
    print("\nPress Ctrl+C to stop")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
