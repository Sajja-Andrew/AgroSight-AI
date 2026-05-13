"""
Continuous Retraining Script
Fine-tunes the model on original dataset + user feedback images.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
import argparse

import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from legacy.feedback_manager import FeedbackManager


def retrain_model(
    base_model_path='../saved_models/best_model_finetuned.keras',
    original_data_dir='../dataset/processed',
    feedback_dir='feedback',
    model_save_dir='../saved_models',
    epochs=5,
    batch_size=16,
    learning_rate=1e-5,
    use_feedback_only=False
):
    """
    Retrain the model incorporating user feedback.

    Args:
        base_model_path: Path to the current model
        original_data_dir: Path to the original processed dataset
        feedback_dir: Path to feedback images
        model_save_dir: Where to save the new model
        epochs: Number of training epochs
        batch_size: Batch size
        learning_rate: Learning rate for fine-tuning
        use_feedback_only: If True, only train on feedback images
    """

    print("=" * 60)
    print("🔄 CONTINUOUS RETRAINING")
    print("=" * 60)

    # Validate paths
    base_model_path = Path(base_model_path)
    if not base_model_path.is_absolute():
        base_model_path = Path(__file__).parent / base_model_path

    original_data_dir = Path(original_data_dir)
    if not original_data_dir.is_absolute():
        original_data_dir = Path(__file__).parent / original_data_dir

    model_save_dir = Path(model_save_dir)
    if not model_save_dir.is_absolute():
        model_save_dir = Path(__file__).parent / model_save_dir

    feedback_manager = FeedbackManager(feedback_dir=feedback_dir)
    feedback_stats = feedback_manager.get_feedback_stats()

    print(f"\n📊 Base model: {base_model_path}")
    print(f"📊 Original data: {original_data_dir}")
    print(f"📊 Feedback images: {feedback_stats['total_feedback']}")
    print(f"📊 Epochs: {epochs}")
    print(f"📊 Learning rate: {learning_rate}")

    if feedback_stats['total_feedback'] == 0:
        print("\n⚠️  No feedback images found. Skipping retraining.")
        return None

    # Prepare combined dataset
    temp_dataset_dir = Path(__file__).parent / 'temp_training_data'
    if temp_dataset_dir.exists():
        shutil.rmtree(temp_dataset_dir)

    print("\n📁 Preparing combined dataset...")

    # Copy original training data
    original_train = original_data_dir / 'train'
    if original_train.exists() and not use_feedback_only:
        print("  Copying original training data...")
        shutil.copytree(original_train, temp_dataset_dir / 'train', dirs_exist_ok=True)

    # Add feedback images
    feedback_images = feedback_manager.get_feedback_images()
    if feedback_images:
        print(f"  Adding {len(feedback_images)} feedback images...")
        for img_path, class_name in feedback_images:
            class_folder = temp_dataset_dir / 'train' / class_name
            class_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img_path, class_folder / Path(img_path).name)

    # Copy validation data
    original_val = original_data_dir / 'val'
    if original_val.exists():
        shutil.copytree(original_val, temp_dataset_dir / 'val', dirs_exist_ok=True)

    # Check if we have data
    train_dir = temp_dataset_dir / 'train'
    if not train_dir.exists() or not any(train_dir.iterdir()):
        print("❌ No training data available.")
        return None

    class_folders = [d for d in train_dir.iterdir() if d.is_dir()]
    num_classes = len(class_folders)
    print(f"\n✅ Dataset ready: {num_classes} classes")

    # Data generators (no rescale — model has preprocess_input)
    train_datagen = ImageDataGenerator(
        rotation_range=15,
        width_shift_range=0.1,
        height_shift_range=0.1,
        horizontal_flip=True,
        fill_mode='nearest'
    )

    val_datagen = ImageDataGenerator()

    train_data = train_datagen.flow_from_directory(
        train_dir,
        target_size=(224, 224),
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=True
    )

    val_data = val_datagen.flow_from_directory(
        temp_dataset_dir / 'val',
        target_size=(224, 224),
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=False
    )

    print(f"   Training samples: {train_data.samples}")
    print(f"   Validation samples: {val_data.samples}")

    # Load base model
    print("\n🧠 Loading base model...")
    model = tf.keras.models.load_model(str(base_model_path))

    # Unfreeze all layers for fine-tuning
    model.trainable = True

    # Recompile with lower learning rate
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    print(f"   Total layers: {len(model.layers)}")
    print(f"   Trainable: {sum(1 for l in model.layers if l.trainable)}")

    # Callbacks
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    checkpoint_path = model_save_dir / f'feedback_retrain_{timestamp}.keras'

    callbacks = [
        ModelCheckpoint(
            filepath=str(checkpoint_path),
            monitor='val_accuracy',
            save_best_only=True,
            verbose=1
        ),
        EarlyStopping(
            monitor='val_loss',
            patience=3,
            restore_best_weights=True,
            verbose=1
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=2,
            min_lr=1e-8,
            verbose=1
        )
    ]

    # Train
    print("\n🚀 Starting fine-tuning...")
    history = model.fit(
        train_data,
        epochs=epochs,
        validation_data=val_data,
        callbacks=callbacks,
        verbose=1
    )

    # Save final model
    final_path = model_save_dir / f'feedback_final_{timestamp}.keras'
    model.save(str(final_path))

    # Save training results
    results = {
        'training_type': 'continuous_feedback_retrain',
        'base_model': str(base_model_path),
        'epochs_trained': epochs,
        'learning_rate': learning_rate,
        'feedback_images': feedback_stats['total_feedback'],
        'final_accuracy': float(history.history['accuracy'][-1]),
        'final_val_accuracy': float(history.history['val_accuracy'][-1]),
        'final_loss': float(history.history['loss'][-1]),
        'final_val_loss': float(history.history['val_loss'][-1]),
        'timestamp': timestamp,
        'saved_models': {
            'best': str(checkpoint_path),
            'final': str(final_path)
        }
    }

    results_file = model_save_dir / f'feedback_training_results_{timestamp}.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("✅ RETRAINING COMPLETE")
    print("=" * 60)
    print(f"\n📊 Final Accuracy: {results['final_accuracy']:.4f}")
    print(f"📊 Val Accuracy: {results['final_val_accuracy']:.4f}")
    print(f"📊 Final Loss: {results['final_loss']:.4f}")
    print(f"\n💾 Models saved:")
    print(f"   Best: {checkpoint_path}")
    print(f"   Final: {final_path}")
    print(f"\n📋 Results: {results_file}")

    # Update active model symlink
    active_link = model_save_dir / 'best_model_finetuned.keras'
    if active_link.exists() or active_link.is_symlink():
        active_link.unlink()
    shutil.copy2(str(final_path), str(active_link))
    print(f"\n🔗 Active model updated: {active_link}")

    # Cleanup temp data
    print("\n🧹 Cleaning up temporary dataset...")
    shutil.rmtree(temp_dataset_dir)

    return results


def main():
    parser = argparse.ArgumentParser(description='Retrain model with user feedback')
    parser.add_argument('--base_model', type=str, default='../saved_models/best_model_finetuned.keras')
    parser.add_argument('--data_dir', type=str, default='../dataset/processed')
    parser.add_argument('--feedback_dir', type=str, default='feedback')
    parser.add_argument('--model_save_dir', type=str, default='../saved_models')
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch_size', type=int, default=16)
    parser.add_argument('--lr', type=float, default=1e-5)
    parser.add_argument('--feedback_only', action='store_true')

    args = parser.parse_args()

    retrain_model(
        base_model_path=args.base_model,
        original_data_dir=args.data_dir,
        feedback_dir=args.feedback_dir,
        model_save_dir=args.model_save_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        use_feedback_only=args.feedback_only
    )


if __name__ == '__main__':
    main()