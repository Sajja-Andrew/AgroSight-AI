"""
Improved Training Script for Smart Crop Disease Detection
This version achieves better accuracy faster
"""

import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras import layers, models
import os
import json
from datetime import datetime
import argparse

print("\n" + "="*60)
print("SMART CROP - IMPROVED TRAINING")
print("="*60)


def create_improved_model(num_classes, img_size=(224, 224)):
    """
    Create improved model with MobileNetV2 base
    """
    
    # Load MobileNetV2 without top layers
    base_model = tf.keras.applications.MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(*img_size, 3)
    )
    
    # Freeze base model initially
    base_model.trainable = False
    
    # Build model
    inputs = layers.Input(shape=(*img_size, 3))
    
    # Light data augmentation
    x = layers.RandomFlip("horizontal")(inputs)
    x = layers.RandomRotation(0.1)(x)
    x = layers.RandomZoom(0.1)(x)
    
    # Preprocess for MobileNetV2
    x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
    
    # Pass through base model
    x = base_model(x, training=False)
    
    # Classification head
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.3)(x)
    
    x = layers.Dense(512, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.4)(x)
    
    x = layers.Dense(256, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.3)(x)
    
    # Output layer
    outputs = layers.Dense(num_classes, activation='softmax')(x)
    
    model = models.Model(inputs, outputs, name='AgrosightAIModel')
    
    return model, base_model


def train_model(data_dir, model_save_dir, epochs=20):
    """
    Train the model with improved settings
    """
    
    # Settings
    img_size = (224, 224)
    batch_size = 32
    
    print(f"\n Dataset: {data_dir}")
    print(f" Models will be saved to: {model_save_dir}")
    print(f" Epochs: {epochs}")
    print(f" Batch size: {batch_size}")
    
    # Create output directory
    os.makedirs(model_save_dir, exist_ok=True)
    
    # ============================================================
    # LOAD DATA
    # ============================================================
    
    print("\n" + "="*60)
    print(" LOADING DATA")
    print("="*60)
    
    # Training data with augmentation
    # NOTE: Do NOT rescale here â€” the model has preprocess_input built-in
    train_datagen = ImageDataGenerator(
        rotation_range=15,
        width_shift_range=0.1,
        height_shift_range=0.1,
        horizontal_flip=True,
        fill_mode='nearest'
    )

    # Validation and test - no rescaling (preprocess_input is in the model)
    val_datagen = ImageDataGenerator()
    test_datagen = ImageDataGenerator()
    
    # Load from directories
    print("\nLoading training data...")
    train_data = train_datagen.flow_from_directory(
        os.path.join(data_dir, 'train'),
        target_size=img_size,
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=True
    )
    
    print("Loading validation data...")
    val_data = val_datagen.flow_from_directory(
        os.path.join(data_dir, 'val'),
        target_size=img_size,
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=False
    )
    
    print("Loading test data...")
    test_data = test_datagen.flow_from_directory(
        os.path.join(data_dir, 'test'),
        target_size=img_size,
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=False
    )
    
    num_classes = len(train_data.class_indices)
    class_names = list(train_data.class_indices.keys())
    
    print(f"\n Data loaded successfully!")
    print(f"   Number of classes: {num_classes}")
    print(f"   Training samples: {train_data.samples}")
    print(f"   Validation samples: {val_data.samples}")
    print(f"   Test samples: {test_data.samples}")
    
    # Save class indices
    class_indices_path = os.path.join(model_save_dir, 'class_indices.json')
    with open(class_indices_path, 'w') as f:
        json.dump(train_data.class_indices, f, indent=2)
    print(f"    Class indices saved")
    
    # Save class names
    class_names_path = os.path.join(model_save_dir, 'class_names.txt')
    with open(class_names_path, 'w') as f:
        f.write('\n'.join(class_names))
    
    # ============================================================
    # CREATE MODEL
    # ============================================================
    
    print("\n" + "="*60)
    print("ï¸ CREATING MODEL")
    print("="*60)
    
    model, base_model = create_improved_model(num_classes, img_size)
    
    # Compile model
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )
    
    print("\n Model created and compiled")
    print("\n" + "="*60)
    print("MODEL SUMMARY")
    print("="*60)
    model.summary()
    
    # ============================================================
    # PHASE 1: TRAIN CLASSIFICATION HEAD
    # ============================================================
    
    print("\n" + "="*60)
    print(" PHASE 1: TRAINING CLASSIFICATION HEAD")
    print("="*60)
    print("Training the top layers while base model is frozen...")
    
    # Callbacks
    callbacks_phase1 = [
        ModelCheckpoint(
            filepath=os.path.join(model_save_dir, 'best_model.keras'),
            monitor='val_accuracy',
            save_best_only=True,
            verbose=1
        ),
        EarlyStopping(
            monitor='val_accuracy',
            patience=5,
            restore_best_weights=True,
            verbose=1
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=3,
            min_lr=1e-7,
            verbose=1
        )
    ]
    
    # Calculate steps
    steps_per_epoch = train_data.samples // batch_size
    validation_steps = val_data.samples // batch_size
    
    print(f"\nSteps per epoch: {steps_per_epoch}")
    print(f"Validation steps: {validation_steps}")
    print(f"Training for {min(epochs, 10)} epochs...\n")
    
    # Train phase 1
    history_phase1 = model.fit(
        train_data,
        epochs=min(epochs, 10),
        steps_per_epoch=steps_per_epoch,
        validation_data=val_data,
        validation_steps=validation_steps,
        callbacks=callbacks_phase1,
        verbose=1
    )
    
    # ============================================================
    # PHASE 2: FINE-TUNING
    # ============================================================
    
    if epochs > 10:
        print("\n" + "="*60)
        print(" PHASE 2: FINE-TUNING")
        print("="*60)
        print("Unfreezing last 20 layers of MobileNetV2...")
        
        # Unfreeze base model
        base_model.trainable = True
        
        # Freeze all layers except last 20
        for layer in base_model.layers[:-20]:
            layer.trainable = False
        
        # Count trainable layers
        trainable_count = sum(1 for layer in base_model.layers if layer.trainable)
        print(f"Trainable layers in base model: {trainable_count}")
        
        # Recompile with lower learning rate
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        print("Compiled with learning rate: 1e-5")
        print(f"Training for {epochs - 10} more epochs...\n")
        
        # Callbacks for phase 2
        callbacks_phase2 = [
            ModelCheckpoint(
                filepath=os.path.join(model_save_dir, 'best_model_finetuned.keras'),
                monitor='val_accuracy',
                save_best_only=True,
                verbose=1
            ),
            EarlyStopping(
                monitor='val_accuracy',
                patience=5,
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
        
        # Train phase 2
        history_phase2 = model.fit(
            train_data,
            epochs=epochs,
            initial_epoch=10,
            steps_per_epoch=steps_per_epoch,
            validation_data=val_data,
            validation_steps=validation_steps,
            callbacks=callbacks_phase2,
            verbose=1
        )
    
    # ============================================================
    # EVALUATE ON TEST SET
    # ============================================================
    
    print("\n" + "="*60)
    print(" FINAL EVALUATION ON TEST SET")
    print("="*60)
    
    # Load best model
    best_model_path = os.path.join(model_save_dir, 'best_model.keras')
    if os.path.exists(best_model_path):
        print(f"\nLoading best model from: {best_model_path}")
        model = tf.keras.models.load_model(best_model_path)
    
    # Evaluate
    test_loss, test_accuracy = model.evaluate(test_data, verbose=1)
    
    print(f"\n{'='*60}")
    print(" FINAL RESULTS")
    print(f"{'='*60}")
    print(f"Test Loss: {test_loss:.4f}")
    print(f"Test Accuracy: {test_accuracy*100:.2f}%")
    
    # ============================================================
    # SAVE FINAL MODEL
    # ============================================================
    
    print("\n" + "="*60)
    print(" SAVING MODELS")
    print("="*60)
    
    # Save with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save as Keras
    final_model_path = os.path.join(model_save_dir, f'crop_disease_final_{timestamp}.keras')
    model.save(final_model_path)
    print(f" Final model saved: {final_model_path}")
    
    # Save backup Keras model
    backup_model_path = os.path.join(model_save_dir, f'crop_disease_backup_{timestamp}.keras')
    model.save(backup_model_path)
    print(f" Backup model saved: {backup_model_path}")
    
    # Save training results
    results = {
        'test_accuracy': float(test_accuracy),
        'test_loss': float(test_loss),
        'num_classes': num_classes,
        'class_names': class_names,
        'epochs_trained': epochs,
        'training_date': datetime.now().isoformat(),
        'model_type': 'MobileNetV2 Transfer Learning',
        'input_size': f'{img_size[0]}x{img_size[1]}'
    }
    
    results_path = os.path.join(model_save_dir, 'training_results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f" Training results saved: {results_path}")
    
    print("\n" + "="*60)
    print(" TRAINING COMPLETED SUCCESSFULLY!")
    print("="*60)
    print(f"\n Model location: {model_save_dir}")
    print(f" Test Accuracy: {test_accuracy*100:.2f}%")
    print(f"\nYou can now start the API server:")
    print(f"   python app.py")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Train Smart Crop Disease Detection Model (Improved)'
    )
    parser.add_argument('--data_dir', type=str, required=True,
                       help='Path to processed dataset directory')
    parser.add_argument('--model_save_dir', type=str, required=True,
                       help='Path to save trained models')
    parser.add_argument('--epochs', type=int, default=20,
                       help='Number of training epochs (default: 20)')
    
    args = parser.parse_args()
    
    # Validate paths
    if not os.path.exists(args.data_dir):
        print(f" ERROR: Data directory not found: {args.data_dir}")
        return
    
    train_data_path = os.path.join(args.data_dir, 'train')
    if not os.path.exists(train_data_path):
        print(f" ERROR: Training data not found: {train_data_path}")
        return
    
    # Start training
    train_model(
        data_dir=args.data_dir,
        model_save_dir=args.model_save_dir,
        epochs=args.epochs
    )


if __name__ == "__main__":
    main()