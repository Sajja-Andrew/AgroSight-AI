import os
import json
import base64
import uuid
from datetime import datetime
from pathlib import Path
import shutil

class FeedbackManager:
    """
    Manages user feedback/corrections for continuous learning.
    Stores corrected images in a folder structure ready for retraining.
    """

    def __init__(self, feedback_dir='feedback', log_file='feedback/feedback_log.json'):
        self.feedback_dir = Path(feedback_dir)
        self.log_file = Path(log_file)

        # Ensure feedback directory exists
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

        # Initialize or load log
        if not self.log_file.exists():
            self._save_log([])

    def _save_log(self, entries):
        """Save feedback log to JSON"""
        with open(self.log_file, 'w') as f:
            json.dump(entries, f, indent=2)

    def _load_log(self):
        """Load feedback log from JSON"""
        if not self.log_file.exists():
            return []
        with open(self.log_file, 'r') as f:
            return json.load(f)

    def store_feedback(self, image_data, predicted_class, correct_class, confidence=None, image_format='jpg'):
        """
        Store a user correction.

        Args:
            image_data: Raw bytes or base64 string of the image
            predicted_class: The class the model predicted
            correct_class: The correct class provided by the user
            confidence: Confidence score of the original prediction
            image_format: Image file extension (jpg, png, etc.)

        Returns:
            dict with feedback_id, file_path, and status
        """
        try:
            # Decode image if base64
            if isinstance(image_data, str):
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data

            # Sanitize class name for folder
            safe_class = self._sanitize_folder_name(correct_class)

            # Create class folder
            class_folder = self.feedback_dir / safe_class
            class_folder.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            uid = uuid.uuid4().hex[:8]
            filename = f"{timestamp}_{uid}.{image_format}"
            file_path = class_folder / filename

            # Save image
            with open(file_path, 'wb') as f:
                f.write(image_bytes)

            # Log entry
            entry = {
                'id': f"{timestamp}_{uid}",
                'timestamp': datetime.now().isoformat(),
                'predicted_class': predicted_class,
                'correct_class': correct_class,
                'confidence': confidence,
                'file_path': str(file_path),
                'status': 'stored'
            }

            log = self._load_log()
            log.append(entry)
            self._save_log(log)

            return {
                'success': True,
                'feedback_id': entry['id'],
                'file_path': str(file_path),
                'message': 'Feedback stored successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to store feedback'
            }

    def _sanitize_folder_name(self, class_name):
        """Convert class name to safe folder name"""
        # Replace characters that are problematic in folder names
        safe = class_name.replace('/', '-').replace('\\', '-')
        return safe

    def get_feedback_stats(self):
        """Get statistics about stored feedback"""
        log = self._load_log()

        stats = {
            'total_feedback': len(log),
            'classes': {},
            'recent': log[-10:]  # Last 10 entries
        }

        for entry in log:
            correct_class = entry['correct_class']
            stats['classes'][correct_class] = stats['classes'].get(correct_class, 0) + 1

        # Count actual files per class folder
        for class_folder in self.feedback_dir.iterdir():
            if class_folder.is_dir():
                class_name = class_folder.name
                file_count = len(list(class_folder.glob('*')))
                if class_name not in stats['classes']:
                    stats['classes'][class_name] = 0
                stats['classes'][class_name] = max(stats['classes'][class_name], file_count)

        return stats

    def get_feedback_images(self, class_name=None):
        """
        Get all feedback images or images for a specific class.
        Returns list of (file_path, correct_class) tuples.
        """
        images = []

        if class_name:
            class_folder = self.feedback_dir / self._sanitize_folder_name(class_name)
            if class_folder.exists():
                for img_file in class_folder.iterdir():
                    if img_file.is_file():
                        images.append((str(img_file), class_name))
        else:
            for class_folder in self.feedback_dir.iterdir():
                if class_folder.is_dir():
                    for img_file in class_folder.iterdir():
                        if img_file.is_file():
                            images.append((str(img_file), class_folder.name))

        return images

    def prepare_feedback_dataset(self, output_dir='feedback_dataset'):
        """
        Copy all feedback images into a clean folder structure suitable for training.
        Returns the path to the prepared dataset.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        images = self.get_feedback_images()

        for img_path, class_name in images:
            class_folder = output_path / class_name
            class_folder.mkdir(parents=True, exist_ok=True)
            dest = class_folder / Path(img_path).name
            shutil.copy2(img_path, dest)

        return str(output_path)


if __name__ == '__main__':
    # Test
    fm = FeedbackManager()
    print("Feedback manager initialized")
    print(f"Stats: {fm.get_feedback_stats()}")