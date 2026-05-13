"""
Disease Predictor with Structured Output
Formats predictions into the production API response schema.
"""

try:
    import tensorflow as tf
    import numpy as np
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None
    np = None

from PIL import Image
import json
import os
import re

# Load disease database from shared JSON
DISEASE_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'disease_database.json')
DISEASE_INFO = {}
try:
    with open(DISEASE_DB_PATH, 'r', encoding='utf-8') as f:
        DISEASE_INFO = json.load(f)
except Exception as e:
    print(f"Warning: Could not load disease database: {e}")
    DISEASE_INFO = {}


class DiseasePredictor:
    def __init__(self, model_path, class_indices_path, disease_info_path=None):
        """
        Initialize predictor with trained model
        """
        print(f"\nLoading model from: {model_path}")
        if TF_AVAILABLE:
            self.model = tf.keras.models.load_model(model_path)
        else:
            raise RuntimeError("TensorFlow is required for DiseasePredictor")
        self.img_size = (224, 224)

        with open(class_indices_path, 'r') as f:
            self.class_indices = json.load(f)

        self.idx_to_class = {v: k for k, v in self.class_indices.items()}

        print(f"Model loaded successfully!")
        print(f"Number of classes: {len(self.class_indices)}")

    def preprocess_image(self, image):
        if isinstance(image, str):
            image = Image.open(image)
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image = image.resize(self.img_size)
        img_array = np.array(image)
        img_array = img_array.astype(np.float32)
        img_batch = np.expand_dims(img_array, axis=0)
        return img_batch

    def predict(self, image, top_k=3):
        """
        Predict disease from image and return structured result.
        """
        img_batch = self.preprocess_image(image)
        predictions = self.model.predict(img_batch, verbose=0)[0]
        top_indices = np.argsort(predictions)[::-1][:top_k]

        pred_list = []
        for idx in top_indices:
            class_name = self.idx_to_class[idx]
            confidence = float(predictions[idx])
            pred_list.append(self._build_prediction(class_name, confidence))

        primary = pred_list[0]
        return self._format_response(primary, pred_list)

    def _build_prediction(self, class_name, confidence):
        """Build a single prediction dict."""
        crop = self._extract_crop(class_name)

        disease_data = DISEASE_INFO.get(class_name, {
            'name': class_name.replace('___', ' - ').replace('_', ' '),
            'symptoms': 'Information not available',
            'solution': 'Consult an agricultural expert',
            'prevention': 'Practice good agricultural methods',
            'severity': 'Unknown'
        })

        disease_name = disease_data.get('name', class_name.replace('___', ' - ').replace('_', ' '))
        is_healthy = 'healthy' in disease_name.lower()

        severity = self._resolve_severity(disease_data.get('severity', 'Unknown'), confidence, is_healthy)

        return {
            'disease': disease_name,
            'confidence': round(confidence, 4),
            'class_name': class_name,
            'crop': crop,
            'symptoms': self._split_to_list(disease_data.get('symptoms', 'Information not available')),
            'recommendation': self._split_to_list(disease_data.get('solution', 'Consult an agricultural expert')),
            'prevention': disease_data.get('prevention', 'Practice good agricultural methods.'),
            'causes': self._generate_causes(class_name, disease_data),
            'severity': severity,
            'is_healthy': is_healthy
        }

    def _format_response(self, primary, all_predictions):
        """Format final API response."""
        return {
            'success': True,
            'is_leaf': True,
            'crop': primary['crop'],
            'disease': primary['disease'],
            'confidence': primary['confidence'],
            'severity': primary['severity'],
            'symptoms': primary['symptoms'],
            'causes': primary['causes'],
            'recommendation': primary['recommendation'],
            'prevention': primary['prevention'],
            'is_healthy': primary['is_healthy'],
            'message': 'You can ask me any question about this result or your crop.',
            'predictions': all_predictions,
            'primary_prediction': primary
        }

    @staticmethod
    def _extract_crop(class_name):
        """Extract crop name from class_name like 'Tomato___Early_blight'."""
        if '___' in class_name:
            return class_name.split('___')[0].replace('_', ' ')
        elif '_' in class_name:
            return class_name.split('_')[0].replace('_', ' ')
        return 'Unknown Crop'

    @staticmethod
    def _resolve_severity(db_severity, confidence, is_healthy):
        """
        Resolve severity from database or confidence-based mapping.
        Healthy = None. Database value takes priority if known.
        """
        if is_healthy:
            return 'None'

        db_severity = (db_severity or 'Unknown').strip()
        if db_severity and db_severity.lower() not in ('unknown', '', 'n/a'):
            # Map database severity strings to standard levels
            s = db_severity.lower()
            if 'high' in s or 'severe' in s:
                return 'Severe'
            elif 'medium' in s or 'moderate' in s:
                return 'Moderate'
            elif 'low' in s or 'mild' in s:
                return 'Mild'
            elif 'none' in s:
                return 'None'

        # Confidence-based fallback (user requirement)
        conf_pct = confidence * 100
        if conf_pct >= 76:
            return 'Severe'
        elif conf_pct >= 41:
            return 'Moderate'
        else:
            return 'Mild'

    @staticmethod
    def _split_to_list(text):
        """Split a sentence/paragraph into a clean list of items."""
        if not text:
            return []
        # Split by period, semicolon, or newline
        parts = re.split(r'[.;\n]+', text)
        items = []
        for p in parts:
            p = p.strip()
            # Clean up leading bullets/dashes
            p = re.sub(r'^[-*•◦–—]+\s*', '', p)
            if len(p) > 3:
                items.append(p)
        return items if items else [text.strip()]

    @staticmethod
    def _generate_causes(class_name, disease_data):
        """Generate causes text from disease info or fallback."""
        existing = disease_data.get('causes')
        if existing and existing.strip() and existing.strip().lower() not in ('information not available', ''):
            return existing.strip()

        disease_lower = disease_data.get('name', class_name).lower()

        if 'bacterial' in disease_lower or 'bacteria' in disease_lower:
            return 'Bacterial infection caused by pathogenic bacteria entering through wounds or natural openings, favored by warm, wet conditions.'
        if 'fungal' in disease_lower or 'mildew' in disease_lower or 'blight' in disease_lower or 'rust' in disease_lower or 'spot' in disease_lower:
            return 'Fungal infection spread by spores through wind, rain, or contaminated tools. Favored by high humidity and poor air circulation.'
        if 'virus' in disease_lower or 'mosaic' in disease_lower or 'curl' in disease_lower:
            return 'Viral infection transmitted by insect vectors (aphids, whiteflies) or through infected seeds and tools.'
        if 'mite' in disease_lower or 'spider' in disease_lower or 'insect' in disease_lower or 'armyworm' in disease_lower:
            return 'Pest infestation caused by mites or insects feeding on plant tissue, often exacerbated by dry conditions and lack of natural predators.'
        if 'nematode' in disease_lower or 'root knot' in disease_lower:
            return 'Soil-borne nematode infection that attacks plant roots, reducing nutrient uptake and weakening the plant.'
        if 'healthy' in disease_lower:
            return 'No disease detected. The plant appears to be in good health.'

        return 'Pathogen infection or environmental stress under favorable conditions such as high humidity, poor drainage, or plant stress.'

    def predict_batch(self, images):
        results = []
        for image in images:
            result = self.predict(image)
            results.append(result)
        return results


# ── Standalone test ──
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Predict Crop Disease (Structured Output)')
    parser.add_argument('--model', type=str, required=True)
    parser.add_argument('--class_indices', type=str, required=True)
    parser.add_argument('--image', type=str, required=True)
    args = parser.parse_args()

    predictor = DiseasePredictor(args.model, args.class_indices)
    result = predictor.predict(args.image)

    pred = result['primary_prediction']
    print("\n" + "=" * 60)
    print("PREDICTION RESULT")
    print("=" * 60)
    print(f"\nCrop:         {pred['crop']}")
    print(f"Disease:      {pred['disease']}")
    print(f"Confidence:   {pred['confidence']*100:.2f}%")
    print(f"Severity:     {pred['severity']}")
    print(f"\nSymptoms:")
    for s in pred['symptoms']:
        print(f"  - {s}")
    print(f"\nCauses: {pred['causes']}")
    print(f"\nRecommendation:")
    for r in pred['recommendation']:
        print(f"  - {r}")
    print(f"\nPrevention: {pred['prevention']}")
    print(f"\n{result['message']}")
