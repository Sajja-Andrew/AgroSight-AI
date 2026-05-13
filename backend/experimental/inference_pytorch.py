"""
Smart Crop AI - PyTorch Inference Pipeline
Load a trained model and run predictions on new images.

Usage:
    # Single image prediction
    python inference_pytorch.py --model_path saved_models_pytorch/best_model.pth \
        --image path/to/leaf.jpg --model_name mobilenetv2

    # Batch prediction on a folder
    python inference_pytorch.py --model_path saved_models_pytorch/best_model.pth \
        --image_dir path/to/test_images/ --model_name mobilenetv2

Dependencies:
    pip install torch torchvision pillow numpy
"""

import os
import sys
import json
import argparse
from typing import Union, List, Tuple

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
from torchvision import transforms, models
from torchvision.models import MobileNet_V2_Weights, ResNet50_Weights


# ============================================================
# DEVICE SETUP
# ============================================================

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ============================================================
# 1. MODEL LOADING
# ============================================================

def load_model(model_path: str, num_classes: int, model_name: str = 'mobilenetv2'):
    """
    Load a trained PyTorch model from a .pth weights file.

    Args:
        model_path: path to .pth checkpoint
        num_classes: number of output classes
        model_name: 'mobilenetv2' or 'resnet50'

    Returns:
        model (torch.nn.Module) on DEVICE in eval mode
    """
    if model_name == 'mobilenetv2':
        model = models.mobilenet_v2(weights=None)
        model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    elif model_name == 'resnet50':
        model = models.resnet50(weights=None)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    # Load weights
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    state_dict = torch.load(model_path, map_location=DEVICE)
    model.load_state_dict(state_dict)
    model = model.to(DEVICE)
    model.eval()
    print(f"[Load] Loaded {model_name} from {model_path} ({num_classes} classes)")
    return model


def load_class_names(class_names_path: str) -> List[str]:
    """Load ordered class names from JSON."""
    if not os.path.exists(class_names_path):
        raise FileNotFoundError(f"Class names file not found: {class_names_path}")
    with open(class_names_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_preprocess_config(preprocess_path: str) -> dict:
    """Load preprocessing configuration."""
    if not os.path.exists(preprocess_path):
        # Return ImageNet defaults
        return {
            'image_size': 224,
            'mean': [0.485, 0.456, 0.406],
            'std': [0.229, 0.224, 0.225],
        }
    with open(preprocess_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 2. IMAGE PREPROCESSING
# ============================================================

def get_inference_transform(config: dict = None):
    """
    Build the inference transform from a config dict or ImageNet defaults.
    """
    if config is None:
        config = {}
    size = config.get('image_size', 224)
    mean = config.get('mean', [0.485, 0.456, 0.406])
    std = config.get('std', [0.229, 0.224, 0.225])

    transform = transforms.Compose([
        transforms.Resize((size, size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    return transform


def preprocess_image(image: Union[str, Image.Image, np.ndarray], transform) -> torch.Tensor:
    """
    Load and preprocess an image into a batch tensor.

    Args:
        image: file path, PIL Image, or numpy array (H,W,3)
        transform: torchvision transforms pipeline

    Returns:
        tensor of shape (1, 3, H, W)
    """
    if isinstance(image, str):
        if not os.path.exists(image):
            raise FileNotFoundError(f"Image not found: {image}")
        image = Image.open(image).convert('RGB')
    elif isinstance(image, np.ndarray):
        image = Image.fromarray(image).convert('RGB')
    elif not isinstance(image, Image.Image):
        raise TypeError(f"Expected str, PIL.Image, or np.ndarray. Got {type(image)}")

    tensor = transform(image)
    # Add batch dimension
    tensor = tensor.unsqueeze(0)
    return tensor


# ============================================================
# 3. PREDICTION
# ============================================================

def predict_image(model, image_input, class_names, transform, device=DEVICE, top_k=3):
    """
    Run inference on a single image.

    Args:
        model: trained PyTorch model in eval mode
        image_input: str path, PIL Image, or numpy array
        class_names: ordered list of class names
        transform: preprocessing transform
        device: torch device
        top_k: number of top predictions to return

    Returns:
        dict: {
            'predicted_class': str,
            'confidence': float,
            'top_k': [
                {'class': str, 'confidence': float},
                ...
            ]
        }
    """
    tensor = preprocess_image(image_input, transform).to(device)

    with torch.no_grad():
        outputs = model(tensor)
        probabilities = torch.softmax(outputs, dim=1)

    probs = probabilities.cpu().numpy().flatten()
    top_indices = np.argsort(probs)[::-1][:top_k]

    result = {
        'predicted_class': class_names[top_indices[0]],
        'confidence': float(probs[top_indices[0]]),
        'top_k': [
            {
                'class': class_names[idx],
                'confidence': float(probs[idx]),
            }
            for idx in top_indices
        ]
    }
    return result


def predict_batch(model, image_dir: str, class_names, transform, device=DEVICE):
    """
    Run inference on all images in a directory.

    Returns:
        list of dicts with filename + prediction result
    """
    if not os.path.isdir(image_dir):
        raise FileNotFoundError(f"Directory not found: {image_dir}")

    results = []
    for fname in sorted(os.listdir(image_dir)):
        fpath = os.path.join(image_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            pred = predict_image(model, fpath, class_names, transform, device)
            pred['filename'] = fname
            results.append(pred)
        except Exception as e:
            print(f"[Skip] {fname}: {e}")
    return results


# ============================================================
# 4. CONVENIENCE CLASS (for Flask integration)
# ============================================================

class DiseasePredictorPyTorch:
    """
    Production-ready wrapper for disease prediction.
    Loads model, class names, and preprocessing once.
    """

    def __init__(self, model_path: str, class_names_path: str,
                 preprocess_path: str = None, model_name: str = 'mobilenetv2'):
        self.class_names = load_class_names(class_names_path)
        self.config = load_preprocess_config(preprocess_path) if preprocess_path else {}
        self.transform = get_inference_transform(self.config)
        self.model = load_model(model_path, len(self.class_names), model_name)
        self.model_name = model_name

    def predict(self, image_input, top_k=3):
        """Run prediction on a single image."""
        return predict_image(
            self.model, image_input, self.class_names,
            self.transform, device=DEVICE, top_k=top_k
        )

    def predict_pil(self, pil_image, top_k=3):
        """Run prediction on a PIL Image (used by Flask)."""
        tensor = self.transform(pil_image.convert('RGB'))
        tensor = tensor.unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            outputs = self.model(tensor)
            probabilities = torch.softmax(outputs, dim=1)

        probs = probabilities.cpu().numpy().flatten()
        top_indices = np.argsort(probs)[::-1][:top_k]

        return {
            'predicted_class': self.class_names[top_indices[0]],
            'confidence': float(probs[top_indices[0]]),
            'top_k': [
                {'class': self.class_names[idx], 'confidence': float(probs[idx])}
                for idx in top_indices
            ]
        }


# ============================================================
# MAIN (CLI)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Crop Disease Inference (PyTorch)')
    parser.add_argument('--model_path', type=str, required=True, help='Path to .pth model weights')
    parser.add_argument('--class_names', type=str, default=None, help='Path to class_names.json')
    parser.add_argument('--preprocess', type=str, default=None, help='Path to preprocess_config.json')
    parser.add_argument('--model_name', type=str, default='mobilenetv2', choices=['mobilenetv2', 'resnet50'])
    parser.add_argument('--image', type=str, default=None, help='Single image path')
    parser.add_argument('--image_dir', type=str, default=None, help='Directory of images')
    parser.add_argument('--top_k', type=int, default=3)
    args = parser.parse_args()

    # Auto-locate class_names.json next to model if not provided
    class_names_path = args.class_names
    if not class_names_path:
        model_dir = os.path.dirname(args.model_path)
        candidate = os.path.join(model_dir, 'class_names.json')
        if os.path.exists(candidate):
            class_names_path = candidate
        else:
            print("Error: --class_names required (or place class_names.json next to model).")
            sys.exit(1)

    # Auto-locate preprocess_config.json next to model if not provided
    preprocess_path = args.preprocess
    if not preprocess_path:
        model_dir = os.path.dirname(args.model_path)
        candidate = os.path.join(model_dir, 'preprocess_config.json')
        if os.path.exists(candidate):
            preprocess_path = candidate

    predictor = DiseasePredictorPyTorch(
        model_path=args.model_path,
        class_names_path=class_names_path,
        preprocess_path=preprocess_path,
        model_name=args.model_name,
    )

    if args.image:
        print(f"\nPredicting: {args.image}")
        result = predictor.predict(args.image, top_k=args.top_k)
        print(f"  Predicted: {result['predicted_class']} ({result['confidence']*100:.2f}%)")
        print("  Top predictions:")
        for p in result['top_k']:
            print(f"    - {p['class']}: {p['confidence']*100:.2f}%")

    elif args.image_dir:
        print(f"\nBatch predicting: {args.image_dir}")
        results = predict_batch(predictor.model, args.image_dir, predictor.class_names, predictor.transform)
        for r in results:
            print(f"  {r['filename']}: {r['predicted_class']} ({r['confidence']*100:.2f}%)")
    else:
        print("Please provide --image or --image_dir")
        sys.exit(1)


if __name__ == '__main__':
    main()
