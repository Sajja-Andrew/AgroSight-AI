import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint, TensorBoard
import matplotlib.pyplot as plt
import numpy as np
import os
import json
from datetime import datetime
import argparse

# Import model
from model import CropDiseaseModel

class ModelTrainer:
    def __init__(self, data_dir, model_save_dir='../saved_models'):
        self.data_dir = data_dir
        self.model_save_dir = model_save_dir
        self.img_size = (224, 224)
        self.batch_size = 32
        self.epochs = 50
        self.history = None
        self.model = None
        
        # Create directories
        os.makedirs(model_save_dir, exist_ok=True)
        os.makedirs(os.path.join(model_save_dir, 'logs'), exist_ok=True)
        
    def load_data(self):
        """
        Load and prepare training, validation, and test datasets
        """
        
        # Data augmentation for training
        # NOTE: Do NOT rescale here — model includes preprocess_input
        train_datagen = ImageDataGenerator(
            rotation_range=20,
            width_shift_range=0.2,
            height_shift_range=0.2,
            shear_range=0.2,
            zoom_range=0.2,
            horizontal_flip=True,
            fill_mode='nearest'
        )

        # No rescaling for validation and test (preprocess_input is in the model)
        val_datagen = ImageDataGenerator()
        test_datagen = ImageDataGenerator()
        
        # Load training data
        print("\nLoading training data...")
        self.train_data = train_datagen.flow_from_directory(
            os.path.join(self.data_dir, 'train'),
            target_size=self.img_size,
            batch_size=self.batch_size,
            class_mode='categorical',
            shuffle=True
        )
        
        # Load validation data
        print("\nLoading validation data...")
        self.val_data = val_datagen.flow_from_directory(
            os.path.join(self.data_dir, 'val'),
            target_size=self.img_size,
            batch_size=self.batch_size,
            class_mode='categorical',
            shuffle=False
        )
        
        # Load test data
        print("\nLoading test data...")
        self.test_data = test_datagen.flow_from_directory(
            os.path.join(self.data_dir, 'test'),
            target_size=self.img_size,
            batch_size=self.batch_size,
            class_mode='categorical',
            shuffle=False
        )
        
        self.num_classes = len(self.train_data.class_indices)
        self.class_names = list(self.train_data.class_indices.keys())
        
        # Print dataset info
        print("\n" + "="*60)
        print("DATASET INFO")
        print("="*60)
        print(f"Number of classes: {self.num_classes}")
        print(f"Class names: {self.class_names}")
        print(f"Training samples: {self.train_data.samples}")
        print(f"Validation samples: {self.val_data.samples}")
        print(f"Test samples: {self.test_data.samples}")
        
        # Save class indices
        class_indices_path = os.path.join(self.model_save_dir, 'class_indices.json')
        with open(class_indices_path, 'w') as f:
            json.dump(self.train_data.class_indices, f, indent=2)
        print(f"\nClass indices saved to: {class_indices_path}")

        # Save class names
        class_names_path = os.path.join(self.model_save_dir, 'class_names.txt')
        with open(class_names_path, 'w') as f:
            f.write('\n'.join(self.class_names))
        print(f"Class names saved to: {class_names_path}")
        
    def build_model(self, model_type='transfer', base_model='MobileNetV2'):
        """
        Build and compile the model
        
        Args:
            model_type: 'transfer' for transfer learning, 'custom' for custom CNN
            base_model: 'MobileNetV2', 'EfficientNetB0', or 'ResNet50'
        """
        
        crop_model = CropDiseaseModel(
            num_classes=self.num_classes,
            input_shape=(*self.img_size, 3)
        )
        
        if model_type == 'transfer':
            print(f"\nBuilding transfer learning model ({base_model})...")
            self.model = crop_model.build_transfer_learning_model(base_model)
        else:
            print("\nBuilding custom CNN model...")
            self.model = crop_model.build_custom_cnn()
        
        crop_model.compile_model(learning_rate=0.001)
        self.model = crop_model.model
        
        # Print model summary
        print("\n" + "="*60)
        print(" MODEL ARCHITECTURE")
        print("="*60)
        self.model.summary()
        
    def train(self, use_class_weights=True):
        """
        Train the model
        """
        
        # Callbacks
        callbacks = [
            # Save best model
            ModelCheckpoint(
                filepath=os.path.join(self.model_save_dir, 'best_model.keras'),
                monitor='val_accuracy',
                save_best_only=True,
                mode='max',
                verbose=1
            ),
            # Early stopping
            EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True,
                verbose=1
            ),
            # Reduce learning rate
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-7,
                verbose=1
            ),
            # TensorBoard logging
            TensorBoard(
                log_dir=os.path.join(self.model_save_dir, 'logs'),
                histogram_freq=1
            )
        ]
        
        # Calculate steps
        steps_per_epoch = max(1, self.train_data.samples // self.batch_size)
        validation_steps = max(1, self.val_data.samples // self.batch_size)
        
        # Calculate class weights if needed
        class_weight = None
        if use_class_weights:
            print("\nCalculating class weights...")
            from sklearn.utils.class_weight import compute_class_weight
            labels = self.train_data.classes
            class_weights = compute_class_weight(
                class_weight='balanced',
                classes=np.unique(labels),
                y=labels
            )
            class_weight = dict(enumerate(class_weights))
        
        print("\n" + "="*60)
        print(" STARTING TRAINING")
        print("="*60)
        print(f"Epochs: {self.epochs}")
        print(f"Steps per epoch: {steps_per_epoch}")
        print(f"Validation steps: {validation_steps}")
        print("="*60 + "\n")
        
        # Train
        self.history = self.model.fit(
            self.train_data,
            epochs=self.epochs,
            steps_per_epoch=steps_per_epoch,
            validation_data=self.val_data,
            validation_steps=validation_steps,
            callbacks=callbacks,
            class_weight=class_weight,
            verbose=1
        )
        
        print("\n Training completed!")
        
    def fine_tune(self, fine_tune_epochs=10, fine_tune_layers=20):
        """
        Fine-tune the model by unfreezing some layers
        """
        print("\n" + "="*60)
        print(" FINE-TUNING MODEL")
        print("="*60)
        
        # Unfreeze the base model
        for layer in self.model.layers:
            if 'mobilenet' in layer.name.lower() or 'efficientnet' in layer.name.lower() or 'resnet' in layer.name.lower():
                layer.trainable = True
                
                # Freeze all layers except last N
                for sub_layer in layer.layers[:-fine_tune_layers]:
                    sub_layer.trainable = False
        
        # Recompile with lower learning rate
        self.model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        print(f"Unfreezing last {fine_tune_layers} layers")
        print(f"Fine-tuning for {fine_tune_epochs} epochs\n")
        
        # Fine-tune
        fine_tune_history = self.model.fit(
            self.train_data,
            epochs=fine_tune_epochs,
            validation_data=self.val_data,
            callbacks=[
                EarlyStopping(monitor='val_loss', patience=5, verbose=1),
                ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, verbose=1)
            ]
        )
        
        # Combine histories
        if self.history:
            for key in fine_tune_history.history:
                if key in self.history.history:
                    self.history.history[key].extend(fine_tune_history.history[key])
                else:
                    self.history.history[key] = fine_tune_history.history[key]
        
        print("\n Fine-tuning completed!")
        
    def evaluate(self):
        """
        Evaluate the model on test data
        """
        print("\n" + "="*60)
        print(" EVALUATING MODEL")
        print("="*60)
        
        # Load best model
        best_model_path = os.path.join(self.model_save_dir, 'best_model.keras')
        if os.path.exists(best_model_path):
            print(f"Loading best model from: {best_model_path}")
            self.model = tf.keras.models.load_model(best_model_path)
        
        # Evaluate
        test_loss, test_accuracy = self.model.evaluate(self.test_data)
        
        print(f"\n TEST RESULTS:")
        print(f"Loss: {test_loss:.4f}")
        print(f"Accuracy: {test_accuracy:.4f} ({test_accuracy*100:.2f}%)")
        
        # Save results
        results = {
            'test_loss': float(test_loss),
            'test_accuracy': float(test_accuracy),
            'num_classes': self.num_classes,
            'class_names': self.class_names,
            'training_date': datetime.now().isoformat()
        }
        
        results_path = os.path.join(self.model_save_dir, 'evaluation_results.json')
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n Results saved to: {results_path}")
        
        return results
        
    def plot_history(self):
        """
        Plot and save training history
        """
        if not self.history:
            print(" No training history available")
            return
        
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
        
        # Accuracy
        axes[0].plot(self.history.history['accuracy'], label='Training Accuracy', linewidth=2)
        axes[0].plot(self.history.history['val_accuracy'], label='Validation Accuracy', linewidth=2)
        axes[0].set_title('Model Accuracy', fontsize=14)
        axes[0].set_xlabel('Epoch')
        axes[0].set_ylabel('Accuracy')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        # Loss
        axes[1].plot(self.history.history['loss'], label='Training Loss', linewidth=2)
        axes[1].plot(self.history.history['val_loss'], label='Validation Loss', linewidth=2)
        axes[1].set_title('Model Loss', fontsize=14)
        axes[1].set_xlabel('Epoch')
        axes[1].set_ylabel('Loss')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        history_path = os.path.join(self.model_save_dir, 'training_history.png')
        plt.savefig(history_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f" Training history plot saved to: {history_path}")
        
        # Save history data
        history_data = {k: [float(v) for v in vals] for k, vals in self.history.history.items()}
        history_json = os.path.join(self.model_save_dir, 'training_history.json')
        with open(history_json, 'w') as f:
            json.dump(history_data, f, indent=2)
        print(f" Training history data saved to: {history_json}")
        
    def save_final_model(self):
        """
        Save the final model in multiple formats
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        print("\n" + "="*60)
        print(" SAVING MODEL")
        print("="*60)
        
        # Save as Keras
        keras_path = os.path.join(self.model_save_dir, f'crop_disease_model_{timestamp}.keras')
        self.model.save(keras_path)
        print(f" Model saved (Keras): {keras_path}")
        
        # Save as SavedModel
        savedmodel_path = os.path.join(self.model_save_dir, f'crop_disease_model_{timestamp}')
        self.model.save(savedmodel_path, save_format='tf')
        print(f" Model saved (SavedModel): {savedmodel_path}")
        
        # Save as TFLite (for mobile)
        try:
            converter = tf.lite.TFLiteConverter.from_keras_model(self.model)
            tflite_model = converter.convert()
            tflite_path = os.path.join(self.model_save_dir, f'crop_disease_model_{timestamp}.tflite')
            with open(tflite_path, 'wb') as f:
                f.write(tflite_model)
            print(f" Model saved (TFLite): {tflite_path}")
        except Exception as e:
            print(f"Could not save TFLite model: {str(e)}")


def main():
    import sys

    # Default paths for direct execution (relative to backend/model/)
    data_dir = '../../dataset/processed'
    model_save_dir = '../../saved_models'
    epochs = 50
    batch_size = 32
    model_type = 'transfer'
    base_model = 'MobileNetV2'
    fine_tune = False

    # Override with CLI args if provided
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description='Train Crop Disease Detection Model')
        parser.add_argument('--data_dir', type=str, default=data_dir, help='Path to processed dataset')
        parser.add_argument('--model_save_dir', type=str, default=model_save_dir, help='Path to save models')
        parser.add_argument('--epochs', type=int, default=epochs, help='Number of training epochs')
        parser.add_argument('--batch_size', type=int, default=batch_size, help='Batch size')
        parser.add_argument('--model_type', type=str, default=model_type, choices=['transfer', 'custom'], help='Model type')
        parser.add_argument('--base_model', type=str, default=base_model, choices=['MobileNetV2', 'EfficientNetB0', 'ResNet50'], help='Base model for transfer learning')
        parser.add_argument('--fine_tune', action='store_true', help='Whether to fine-tune the model')
        args = parser.parse_args()

        data_dir = args.data_dir
        model_save_dir = args.model_save_dir
        epochs = args.epochs
        batch_size = args.batch_size
        model_type = args.model_type
        base_model = args.base_model
        fine_tune = args.fine_tune

    # Initialize trainer
    trainer = ModelTrainer(
        data_dir=data_dir,
        model_save_dir=model_save_dir
    )
    trainer.epochs = epochs
    trainer.batch_size = batch_size

    # Load data
    trainer.load_data()

    # Build model
    trainer.build_model(model_type=model_type, base_model=base_model)

    # Train
    trainer.train()

    # Fine-tune if requested
    if fine_tune:
        trainer.fine_tune()

    # Evaluate
    trainer.evaluate()

    # Plot history
    trainer.plot_history()

    # Save model
    trainer.save_final_model()

    print("\n" + "="*60)
    print(" TRAINING COMPLETED SUCCESSFULLY!")
    print("="*60)


if __name__ == "__main__":
    main()