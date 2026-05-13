"""
Leaf Detector Training Script
Trains a binary classifier (Leaf vs Not Leaf) using MobileNetV2.
Uses the existing plant disease dataset as positive samples and
generates synthetic non-leaf images as negative samples.
"""

import os
import json
import random
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import argparse

# TensorFlow imports with fallback
try:
    import tensorflow as tf
    from tensorflow.keras import layers, models
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("ERROR: TensorFlow is required for training. Install it first:")
    print("   pip install tensorflow==2.15.0")
    exit(1)

print("\n" + "=" * 60)
print("LEAF DETECTOR TRAINING")
print("=" * 60)


def generate_synthetic_non_leaf(original_image, output_path):
    """
    Generate a synthetic non-leaf image from a leaf image by applying
    extreme distortions that break leaf characteristics.
    """
    img = original_image.copy()

    # Random choice of distortion technique
    technique = random.randint(0, 4)

    if technique == 0:
        # Heavy hue shift away from green toward red/blue/purple
        img = img.convert('HSV')
        pixels = img.load()
        for i in range(img.width):
            for j in range(img.height):
                h, s, v = pixels[i, j]
                # Shift hue away from green (60-180) toward red/blue
                if 40 < h < 180:
                    h = (h + 180 + random.randint(-30, 30)) % 256
                pixels[i, j] = (h, s, v)
        img = img.convert('RGB')
        # Add heavy noise
        arr = np.array(img)
        noise = np.random.randint(-80, 80, arr.shape, dtype=np.int16)
        arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)

    elif technique == 1:
        # Extreme posterization + color inversion
        img = ImageEnhance.Color(img).enhance(3.0)
        img = ImageEnhance.Contrast(img).enhance(4.0)
        arr = np.array(img)
        # Invert colors randomly per channel
        arr = 255 - arr
        img = Image.fromarray(arr)
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1, 3)))

    elif technique == 2:
        # Random geometric pattern overlay
        arr = np.array(img)
        h, w = arr.shape[:2]
        # Create random colored shapes
        for _ in range(random.randint(5, 15)):
            x1, y1 = random.randint(0, w-20), random.randint(0, h-20)
            x2, y2 = x1 + random.randint(10, w//3), y1 + random.randint(10, h//3)
            color = [random.randint(0, 255) for _ in range(3)]
            arr[y1:y2, x1:x2] = color
        img = Image.fromarray(arr)
        img = img.filter(ImageFilter.GaussianBlur(radius=2))

    elif technique == 3:
        # Heavy color jitter away from plant colors
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.1)  # Remove color
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(random.uniform(0.3, 1.8))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(random.uniform(2.0, 5.0))
        # Add random colored noise grid
        arr = np.array(img)
        grid_size = random.randint(8, 16)
        for y in range(0, arr.shape[0], grid_size):
            for x in range(0, arr.shape[1], grid_size):
                if random.random() > 0.5:
                    color = np.random.randint(0, 256, 3)
                    arr[y:min(y+grid_size, arr.shape[0]), x:min(x+grid_size, arr.shape[1])] = color
        img = Image.fromarray(arr)

    else:
        # Texture-like noise (simulating fabric/wood/concrete)
        arr = np.array(img)
        h, w = arr.shape[:2]
        base = np.random.randint(50, 200, (h, w, 3), dtype=np.uint8)
        # Add stripe patterns
        for _ in range(random.randint(3, 8)):
            thickness = random.randint(2, 8)
            y = random.randint(0, h - thickness)
            base[y:y+thickness, :] = np.random.randint(0, 256, 3)
        base = base.astype(np.float32)
        # Blend with original slightly
        orig = arr.astype(np.float32)
        blended = 0.1 * orig + 0.9 * base
        img = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))

    # Final resize to standard size
    img = img.resize((224, 224))
    img.save(output_path)
    return output_path


def prepare_dataset(data_dir, output_dir, neg_ratio=1.0):
    """
    Prepare training dataset with positive (leaf) and negative (non-leaf) samples.

    Args:
        data_dir: Path to processed dataset (with train/ val/ test/)
        output_dir: Where to save leaf_detector dataset
        neg_ratio: How many negatives to generate per positive
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'train', 'leaf'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'train', 'not_leaf'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'val', 'leaf'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'val', 'not_leaf'), exist_ok=True)

    train_dir = os.path.join(data_dir, 'train')
    if not os.path.exists(train_dir):
        print(f"ERROR: Training directory not found: {train_dir}")
        return None

    classes = [d for d in os.listdir(train_dir) if os.path.isdir(os.path.join(train_dir, d))]
    all_images = []
    for cls in classes:
        cls_dir = os.path.join(train_dir, cls)
        images = [os.path.join(cls_dir, f) for f in os.listdir(cls_dir)
                  if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        all_images.extend(images)

    print(f"\nFound {len(all_images)} leaf images across {len(classes)} classes")

    # Shuffle and split 80/20
    random.seed(42)
    random.shuffle(all_images)
    split_idx = int(len(all_images) * 0.8)
    train_images = all_images[:split_idx]
    val_images = all_images[split_idx:]

    print(f"Split: {len(train_images)} train, {len(val_images)} validation")

    # Copy/link positive samples (leaf)
    print("\nCopying positive samples (leaf)...")
    for idx, img_path in enumerate(train_images):
        dst = os.path.join(output_dir, 'train', 'leaf', f"leaf_{idx}.jpg")
        img = Image.open(img_path).convert('RGB').resize((224, 224))
        img.save(dst)

    for idx, img_path in enumerate(val_images):
        dst = os.path.join(output_dir, 'val', 'leaf', f"leaf_{idx}.jpg")
        img = Image.open(img_path).convert('RGB').resize((224, 224))
        img.save(dst)

    # Generate negative samples (not_leaf)
    num_train_neg = int(len(train_images) * neg_ratio)
    num_val_neg = int(len(val_images) * neg_ratio)

    print(f"\nGenerating {num_train_neg} synthetic non-leaf training images...")
    for i in range(num_train_neg):
        src_path = random.choice(train_images)
        src_img = Image.open(src_path).convert('RGB')
        dst = os.path.join(output_dir, 'train', 'not_leaf', f"notleaf_{i}.jpg")
        generate_synthetic_non_leaf(src_img, dst)

    print(f"Generating {num_val_neg} synthetic non-leaf validation images...")
    for i in range(num_val_neg):
        src_path = random.choice(val_images)
        src_img = Image.open(src_path).convert('RGB')
        dst = os.path.join(output_dir, 'val', 'not_leaf', f"notleaf_{i}.jpg")
        generate_synthetic_non_leaf(src_img, dst)

    print(f"\nDataset ready at: {output_dir}")
    print(f"  Train - Leaf: {len(train_images)}, Not Leaf: {num_train_neg}")
    print(f"  Val   - Leaf: {len(val_images)}, Not Leaf: {num_val_neg}")
    return output_dir


def create_leaf_detector_model():
    """Create MobileNetV2-based binary leaf detector."""
    base = tf.keras.applications.MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(224, 224, 3)
    )
    base.trainable = False

    inputs = layers.Input(shape=(224, 224, 3))
    x = tf.keras.applications.mobilenet_v2.preprocess_input(inputs)
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(128, activation='relu')(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(1, activation='sigmoid', name='leaf_probability')(x)

    model = models.Model(inputs, outputs, name='LeafDetector')
    return model, base


def train_leaf_detector(data_dir, model_save_dir='../saved_models', epochs=15):
    """Train the leaf detector model."""
    os.makedirs(model_save_dir, exist_ok=True)

    # Data generators
    train_datagen = ImageDataGenerator(
        rotation_range=20,
        width_shift_range=0.2,
        height_shift_range=0.2,
        zoom_range=0.2,
        horizontal_flip=True,
        brightness_range=[0.7, 1.3]
    )
    val_datagen = ImageDataGenerator()

    train_data = train_datagen.flow_from_directory(
        os.path.join(data_dir, 'train'),
        target_size=(224, 224),
        batch_size=32,
        class_mode='binary',
        classes=['not_leaf', 'leaf']
    )
    val_data = val_datagen.flow_from_directory(
        os.path.join(data_dir, 'val'),
        target_size=(224, 224),
        batch_size=32,
        class_mode='binary',
        classes=['not_leaf', 'leaf']
    )

    print(f"\nClass indices: {train_data.class_indices}")
    print(f"  'leaf' = positive class")
    print(f"  'not_leaf' = negative class")

    model, base = create_leaf_detector_model()

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['accuracy', tf.keras.metrics.AUC(name='auc')]
    )

    print("\nModel created and compiled")
    model.summary()

    callbacks = [
        ModelCheckpoint(
            filepath=os.path.join(model_save_dir, 'leaf_detector.keras'),
            monitor='val_accuracy',
            save_best_only=True,
            verbose=1
        ),
        EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, min_lr=1e-7, verbose=1)
    ]

    print(f"\nTraining for up to {epochs} epochs...")
    history = model.fit(
        train_data,
        epochs=epochs,
        validation_data=val_data,
        callbacks=callbacks,
        verbose=1
    )

    # Save final model
    final_path = os.path.join(model_save_dir, 'leaf_detector_final.keras')
    model.save(final_path)
    print(f"\nFinal model saved: {final_path}")

    # Save config
    config = {
        'model_type': 'MobileNetV2 Binary Classifier',
        'classes': {'leaf': 1, 'not_leaf': 0},
        'input_size': '224x224',
        'threshold': 0.7,
        'epochs_trained': len(history.history['loss']),
        'training_date': datetime.now().isoformat() if 'datetime' in dir() else 'unknown'
    }
    with open(os.path.join(model_save_dir, 'leaf_detector_config.json'), 'w') as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("LEAF DETECTOR TRAINING COMPLETE")
    print("=" * 60)
    print(f"\nModel saved to: {model_save_dir}/leaf_detector.keras")
    print("\nUsage in app.py:")
    print('   from model.leaf_detector import LeafDetector')
    print('   detector = LeafDetector(model_path="saved_models/leaf_detector.keras")')
    return model


def main():
    from datetime import datetime
    parser = argparse.ArgumentParser(description='Train Leaf vs Not-Leaf Binary Classifier')
    parser.add_argument('--data_dir', type=str, required=True,
                        help='Path to processed dataset (with train/ subfolder)')
    parser.add_argument('--model_save_dir', type=str, default='../saved_models',
                        help='Path to save trained model')
    parser.add_argument('--epochs', type=int, default=15, help='Training epochs')
    parser.add_argument('--neg_ratio', type=float, default=1.0,
                        help='Ratio of negative to positive samples (default: 1.0)')

    args = parser.parse_args()

    # Prepare dataset
    temp_dataset_dir = os.path.join(args.model_save_dir, 'leaf_detector_dataset')
    prepared = prepare_dataset(args.data_dir, temp_dataset_dir, neg_ratio=args.neg_ratio)
    if not prepared:
        return

    # Train model
    train_leaf_detector(prepared, model_save_dir=args.model_save_dir, epochs=args.epochs)


if __name__ == '__main__':
    from datetime import datetime
    main()
