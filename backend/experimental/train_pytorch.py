"""
Smart Crop AI - PyTorch Training Pipeline
Production-ready image classification for crop disease detection.

Requirements (install first):
    pip install torch torchvision opencv-python scikit-learn matplotlib numpy pillow

Usage:
    python train_pytorch.py --data_dir ./dataset --epochs 20 --batch_size 32
    python train_pytorch.py --data_dir ./dataset --model resnet50 --epochs 15

The dataset folder must have this structure:
    dataset/
    â”œâ”€â”€ train/
    â”‚   â”œâ”€â”€ class_1/
    â”‚   â”œâ”€â”€ class_2/
    â”‚   â””â”€â”€ ...
    â”œâ”€â”€ val/
    â””â”€â”€ test/

Outputs:
    saved_models_pytorch/
    â”œâ”€â”€ best_model.pth          # Best validation accuracy weights
    â”œâ”€â”€ final_model.pth         # Final epoch weights
    â”œâ”€â”€ class_names.json        # Ordered list of class names
    â”œâ”€â”€ training_history.json   # Loss and accuracy per epoch
    â”œâ”€â”€ confusion_matrix.png    # Test-set confusion matrix visualization
    â””â”€â”€ model_mobilenetv2.pt  # TorchScript model (optional)
"""

import os
import sys
import json
import argparse
import time
from collections import defaultdict

import numpy as np
import cv2
from PIL import Image

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, transforms, models
from torchvision.models import MobileNet_V2_Weights, ResNet50_Weights

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report,
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'[Device] Using: {DEVICE}')

IMAGE_SIZE = 224
NUM_WORKERS = min(4, os.cpu_count() or 2)


# ============================================================
# 1. DATA LOADING
# ============================================================

def get_transforms(image_size=224):
    """
    Define training, validation, and test preprocessing pipelines.
    """
    # ImageNet normalization (pretrained models expect this)
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )

    train_transform = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(degrees=20),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        transforms.ToTensor(),
        normalize,
    ])

    val_transform = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        normalize,
    ])

    return train_transform, val_transform


class AgrosightAIDataset(Dataset):
    """
    Custom dataset that walks a nested folder tree and yields (image_tensor, class_idx).
    Class names are derived from the relative directory path, separators replaced by '___'.
    """

    def __init__(self, samples, class_to_idx, transform=None):
        """
        Args:
            samples: list of (image_path, class_name_str)
            class_to_idx: dict mapping class_name_str -> integer label
            transform: torchvision transform
        """
        self.samples = samples
        self.class_to_idx = class_to_idx
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, cls_name = self.samples[idx]
        image = Image.open(path).convert('RGB')
        if self.transform:
            image = self.transform(image)
        target = self.class_to_idx[cls_name]
        return image, target


def _load_flat_data(data_dir, batch_size, image_size):
    """Original ImageFolder loader for pre-split train/val/test folders."""
    train_dir = os.path.join(data_dir, 'train')
    val_dir = os.path.join(data_dir, 'val')
    test_dir = os.path.join(data_dir, 'test')

    for d in (train_dir, val_dir, test_dir):
        if not os.path.isdir(d):
            raise FileNotFoundError(
                f"Dataset folder not found: {d}\n"
                "Expected structure:\n"
                "  dataset/train/class_a/\n"
                "  dataset/val/class_a/\n"
                "  dataset/test/class_a/"
            )

    train_transform, val_transform = get_transforms(image_size)

    train_dataset = datasets.ImageFolder(train_dir, transform=train_transform)
    val_dataset = datasets.ImageFolder(val_dir, transform=val_transform)
    test_dataset = datasets.ImageFolder(test_dir, transform=val_transform)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )

    class_names = train_dataset.classes
    print(f'[Data] Classes ({len(class_names)}): {class_names}')
    print(f'[Data] Train: {len(train_dataset)} | Val: {len(val_dataset)} | Test: {len(test_dataset)}')

    return train_loader, val_loader, test_loader, class_names


def _load_nested_data(data_dir, batch_size, image_size, test_size=0.2, val_size=0.1):
    """
    Walk a nested folder tree (e.g. color/Maize/DiseaseClass/) and auto-split
    into train/val/test per class.
    """
    root = os.path.abspath(data_dir)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Dataset folder not found: {root}")

    exts = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')
    class_images = {}

    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(exts):
                full_path = os.path.join(dirpath, f)
                rel_dir = os.path.relpath(dirpath, root)
                class_label = 'unknown' if rel_dir == '.' else rel_dir.replace(os.sep, '___')
                class_images.setdefault(class_label, []).append(full_path)

    if not class_images:
        raise FileNotFoundError(f"No images found in {data_dir}")

    # Per-class split
    train_samples, val_samples, test_samples = [], [], []
    for cls in sorted(class_images.keys()):
        paths = class_images[cls]
        n = len(paths)
        if n < 3:
            print(f"  Warning: class '{cls}' has only {n} images. Assigning all to train.")
            train_samples.extend([(p, cls) for p in paths])
            continue

        train_p, test_p = train_test_split(paths, test_size=test_size, random_state=42)
        val_size_actual = val_size / (1 - test_size) if (1 - test_size) > 0 else 0
        train_p, val_p = train_test_split(train_p, test_size=val_size_actual, random_state=42)

        train_samples.extend([(p, cls) for p in train_p])
        val_samples.extend([(p, cls) for p in val_p])
        test_samples.extend([(p, cls) for p in test_p])

    class_names = sorted(class_images.keys())
    class_to_idx = {c: i for i, c in enumerate(class_names)}

    train_transform, val_transform = get_transforms(image_size)

    train_dataset = AgrosightAIDataset(train_samples, class_to_idx, transform=train_transform)
    val_dataset = AgrosightAIDataset(val_samples, class_to_idx, transform=val_transform)
    test_dataset = AgrosightAIDataset(test_samples, class_to_idx, transform=val_transform)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True if DEVICE.type == 'cuda' else False
    )

    print(f'[Data] Classes ({len(class_names)}): {class_names}')
    print(f'[Data] Train: {len(train_dataset)} | Val: {len(val_dataset)} | Test: {len(test_dataset)}')

    return train_loader, val_loader, test_loader, class_names


def load_data(data_dir, batch_size=32, image_size=224):
    """
    Load train/val/test datasets.
    If a 'train' subfolder exists, use flat ImageFolder layout.
    Otherwise, walk the nested tree and auto-split.
    """
    train_dir = os.path.join(data_dir, 'train')
    if os.path.isdir(train_dir):
        return _load_flat_data(data_dir, batch_size, image_size)
    return _load_nested_data(data_dir, batch_size, image_size)


# ============================================================
# 2. MODEL BUILDING
# ============================================================

def build_model(num_classes, model_name='mobilenetv2', freeze_backbone=False):
    """
    Build a transfer-learning classifier using pretrained weights.

    Args:
        num_classes: number of disease classes in your dataset
        model_name: 'mobilenetv2' | 'resnet50'
        freeze_backbone: if True, freeze early layers for faster training
    """
    if model_name == 'mobilenetv2':
        weights = MobileNet_V2_Weights.IMAGENET1K_V1
        model = models.mobilenet_v2(weights=weights)
        # Replace classifier
        model.classifier[1] = nn.Linear(model.last_channel, num_classes)
        if freeze_backbone:
            for param in model.features.parameters():
                param.requires_grad = False
    elif model_name == 'resnet50':
        weights = ResNet50_Weights.IMAGENET1K_V2
        model = models.resnet50(weights=weights)
        # Replace fully-connected layer
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        if freeze_backbone:
            for param in model.parameters():
                param.requires_grad = False
            # Unfreeze the new FC layer
            for param in model.fc.parameters():
                param.requires_grad = True
    else:
        raise ValueError(f"Unsupported model: {model_name}. Choose 'mobilenetv2' or 'resnet50'.")

    model = model.to(DEVICE)
    print(f'[Model] Loaded {model_name} with {num_classes} output classes.')
    print(f'[Model] Backbone frozen: {freeze_backbone}')
    return model


# ============================================================
# 3. TRAINING LOOP
# ============================================================

def train_one_epoch(model, loader, criterion, optimizer, device):
    """Run one training epoch. Returns average loss and accuracy."""
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * images.size(0)
        _, predicted = torch.max(outputs, 1)
        correct += (predicted == labels).sum().item()
        total += labels.size(0)

    avg_loss = running_loss / total
    accuracy = correct / total
    return avg_loss, accuracy


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    """Evaluate on validation or test set. Returns loss and accuracy."""
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0
    all_preds = []
    all_labels = []

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        outputs = model(images)
        loss = criterion(outputs, labels)

        running_loss += loss.item() * images.size(0)
        _, predicted = torch.max(outputs, 1)
        correct += (predicted == labels).sum().item()
        total += labels.size(0)

        all_preds.extend(predicted.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

    avg_loss = running_loss / total
    accuracy = correct / total
    return avg_loss, accuracy, all_labels, all_preds


def train_model(model, train_loader, val_loader, epochs=20, lr=1e-4, save_dir='saved_models_pytorch'):
    """
    Full training loop with validation and checkpoint saving.
    """
    os.makedirs(save_dir, exist_ok=True)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    # Learning rate scheduler: reduce LR when val loss plateaus
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=3)

    history = {'train_loss': [], 'train_acc': [], 'val_loss': [], 'val_acc': []}
    best_val_acc = 0.0
    best_model_path = os.path.join(save_dir, 'best_model.pth')

    print(f"\n[Training] Starting for {epochs} epochs...\n")
    for epoch in range(1, epochs + 1):
        start = time.time()

        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, DEVICE)
        val_loss, val_acc, _, _ = evaluate(model, val_loader, criterion, DEVICE)

        scheduler.step(val_loss)

        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)

        elapsed = time.time() - start
        print(f"Epoch {epoch:02d}/{epochs} | {elapsed:.1f}s | "
              f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
              f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f}")

        # Save best model
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), best_model_path)
            print(f"  -> Saved best model (val_acc={val_acc:.4f})")

    # Save final model
    final_path = os.path.join(save_dir, 'final_model.pth')
    torch.save(model.state_dict(), final_path)
    print(f"\n[Training] Complete. Best val accuracy: {best_val_acc:.4f}")
    print(f"[Training] Best weights: {best_model_path}")
    print(f"[Training] Final weights: {final_path}")

    return history, best_model_path


# ============================================================
# 4. EVALUATION
# ============================================================

def evaluate_model(model, test_loader, class_names, save_dir='saved_models_pytorch'):
    """
    Evaluate trained model on test set and save confusion matrix + report.
    """
    criterion = nn.CrossEntropyLoss()
    test_loss, test_acc, y_true, y_pred = evaluate(model, test_loader, criterion, DEVICE)

    print(f"\n[Test] Loss: {test_loss:.4f} | Accuracy: {test_acc:.4f}")
    print(f"\nClassification Report:\n{'='*60}")
    print(classification_report(y_true, y_pred, target_names=class_names, digits=4))

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(max(8, len(class_names)), max(6, len(class_names) * 0.5)))
    plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title('Confusion Matrix')
    plt.colorbar()
    tick_marks = np.arange(len(class_names))
    plt.xticks(tick_marks, class_names, rotation=45, ha='right')
    plt.yticks(tick_marks, class_names)
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')
    plt.tight_layout()
    cm_path = os.path.join(save_dir, 'confusion_matrix.png')
    plt.savefig(cm_path, dpi=150)
    plt.close()
    print(f"[Eval] Confusion matrix saved: {cm_path}")

    return test_acc, cm


# ============================================================
# 5. MODEL SAVING
# ============================================================

def save_metadata(class_names, history, save_dir='saved_models_pytorch'):
    """Save class names and training history to JSON."""
    os.makedirs(save_dir, exist_ok=True)

    class_path = os.path.join(save_dir, 'class_names.json')
    with open(class_path, 'w', encoding='utf-8') as f:
        json.dump(class_names, f, indent=2)
    print(f"[Save] Class names: {class_path}")

    history_path = os.path.join(save_dir, 'training_history.json')
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)
    print(f"[Save] Training history: {history_path}")

    # Save preprocessing config for inference
    _, val_transform = get_transforms(IMAGE_SIZE)
    preprocess = {
        'image_size': IMAGE_SIZE,
        'mean': [0.485, 0.456, 0.406],
        'std': [0.229, 0.224, 0.225],
        'model_input_size': IMAGE_SIZE,
    }
    prep_path = os.path.join(save_dir, 'preprocess_config.json')
    with open(prep_path, 'w', encoding='utf-8') as f:
        json.dump(preprocess, f, indent=2)
    print(f"[Save] Preprocess config: {prep_path}")


# ============================================================
# 6. OPTIONAL EXPORT (TorchScript / ONNX)
# ============================================================

def export_torchscript(model, save_dir='saved_models_pytorch', model_name='mobilenetv2'):
    """Export model to TorchScript for mobile deployment."""
    try:
        model.eval()
        example = torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE).to(DEVICE)

        # Trace the model
        traced = torch.jit.trace(model, example)
        ts_path = os.path.join(save_dir, f'model_{model_name}.pt')
        traced.save(ts_path)
        print(f"[Export] TorchScript model saved: {ts_path}")
        return ts_path
    except Exception as e:
        print(f"[Export] TorchScript export failed: {e}")
        return None


def export_onnx(model, save_dir='saved_models_pytorch', model_name='mobilenetv2'):
    """Export model to ONNX format."""
    try:
        model.eval()
        dummy_input = torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE).to(DEVICE)
        onnx_path = os.path.join(save_dir, f'model_{model_name}.onnx')
        torch.onnx.export(
            model, dummy_input, onnx_path,
            export_params=True,
            opset_version=11,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output'],
            dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
        )
        print(f"[Export] ONNX model saved: {onnx_path}")
        return onnx_path
    except Exception as e:
        print(f"[Export] ONNX export failed: {e}")
        return None


# ============================================================
# 7. PLOTTING
# ============================================================

def plot_history(history, save_dir='saved_models_pytorch'):
    """Plot and save training curves."""
    epochs = range(1, len(history['train_loss']) + 1)

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Loss', color='tab:red')
    ax1.plot(epochs, history['train_loss'], 'r-o', label='Train Loss')
    ax1.plot(epochs, history['val_loss'], 'r--s', label='Val Loss')
    ax1.tick_params(axis='y', labelcolor='tab:red')
    ax1.legend(loc='upper left')

    ax2 = ax1.twinx()
    ax2.set_ylabel('Accuracy', color='tab:blue')
    ax2.plot(epochs, history['train_acc'], 'b-o', label='Train Acc')
    ax2.plot(epochs, history['val_acc'], 'b--s', label='Val Acc')
    ax2.tick_params(axis='y', labelcolor='tab:blue')
    ax2.legend(loc='lower right')

    plt.title('Training History')
    plt.tight_layout()
    plot_path = os.path.join(save_dir, 'training_curves.png')
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"[Plot] Training curves saved: {plot_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Train Crop Disease Classification Model (PyTorch)')
    parser.add_argument('--data_dir', type=str, default='dataset', help='Path to dataset folder')
    parser.add_argument('--model', type=str, default='mobilenetv2', choices=['mobilenetv2', 'resnet50'])
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--freeze_backbone', action='store_true', help='Freeze backbone for faster training')
    parser.add_argument('--save_dir', type=str, default='saved_models_pytorch')
    parser.add_argument('--export', action='store_true', help='Export TorchScript and ONNX')
    args = parser.parse_args()

    print("=" * 60)
    print("Smart Crop AI - PyTorch Training")
    print("=" * 60)
    print(f"Dataset:   {args.data_dir}")
    print(f"Model:     {args.model}")
    print(f"Epochs:    {args.epochs}")
    print(f"Batch:     {args.batch_size}")
    print(f"LR:        {args.lr}")
    print(f"Device:    {DEVICE}")
    print("=" * 60 + "\n")

    # 1. Load data
    train_loader, val_loader, test_loader, class_names = load_data(
        args.data_dir, batch_size=args.batch_size, image_size=IMAGE_SIZE
    )

    # 2. Build model
    model = build_model(
        num_classes=len(class_names),
        model_name=args.model,
        freeze_backbone=args.freeze_backbone
    )

    # 3. Train
    history, best_path = train_model(
        model, train_loader, val_loader,
        epochs=args.epochs, lr=args.lr, save_dir=args.save_dir
    )

    # Load best weights for evaluation
    model.load_state_dict(torch.load(best_path, map_location=DEVICE))

    # 4. Evaluate
    test_acc, cm = evaluate_model(model, test_loader, class_names, save_dir=args.save_dir)

    # 5. Save metadata
    save_metadata(class_names, history, save_dir=args.save_dir)

    # 6. Plot curves
    plot_history(history, save_dir=args.save_dir)

    # 7. Optional exports
    if args.export:
        export_torchscript(model, save_dir=args.save_dir, model_name=args.model)
        export_onnx(model, save_dir=args.save_dir, model_name=args.model)

    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"Best model: {best_path}")
    print(f"Test accuracy: {test_acc:.4f}")
    print("=" * 60)


if __name__ == '__main__':
    main()
