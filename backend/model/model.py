try:
    import tensorflow as tf
    from tensorflow.keras import layers, models, regularizers
    import numpy as np
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None
    layers = None
    models = None
    regularizers = None
    np = None

class CropDiseaseModel:
    """
    CNN Model for Crop Disease Detection
    """
    
    def __init__(self, num_classes, input_shape=(224, 224, 3)):
        self.num_classes = num_classes
        self.input_shape = input_shape
        self.model = None
        
    def build_custom_cnn(self):
        """
        Build a custom CNN model optimized for plant disease detection
        """
        
        inputs = layers.Input(shape=self.input_shape)
        
        # Data augmentation (only active during training)
        x = layers.RandomFlip("horizontal_and_vertical")(inputs)
        x = layers.RandomRotation(0.2)(x)
        x = layers.RandomZoom(0.2)(x)
        x = layers.RandomContrast(0.2)(x)
        
        # Preprocessing
        x = layers.Rescaling(1./255)(x)
        
        # Block 1
        x = layers.Conv2D(32, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(32, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)
        x = layers.Dropout(0.25)(x)
        
        # Block 2
        x = layers.Conv2D(64, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(64, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)
        x = layers.Dropout(0.25)(x)
        
        # Block 3
        x = layers.Conv2D(128, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(128, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)
        x = layers.Dropout(0.25)(x)
        
        # Block 4
        x = layers.Conv2D(256, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(256, (3, 3), activation='relu', padding='same')(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)
        x = layers.Dropout(0.25)(x)
        
        # Global Average Pooling
        x = layers.GlobalAveragePooling2D()(x)
        
        # Dense layers
        x = layers.Dense(512, activation='relu', kernel_regularizer=regularizers.l2(0.001))(x)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.5)(x)
        
        x = layers.Dense(256, activation='relu', kernel_regularizer=regularizers.l2(0.001))(x)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.3)(x)
        
        # Output layer
        outputs = layers.Dense(self.num_classes, activation='softmax')(x)
        
        self.model = models.Model(inputs, outputs, name='CropDiseaseModel')
        return self.model
    
    def build_transfer_learning_model(self, base_model_name='MobileNetV2'):
        """
        Build model using transfer learning for better performance
        Options: 'MobileNetV2', 'EfficientNetB0', 'ResNet50'
        """
        
        inputs = layers.Input(shape=self.input_shape)
        
        # Data augmentation
        x = layers.RandomFlip("horizontal")(inputs)
        x = layers.RandomRotation(0.1)(x)
        x = layers.RandomZoom(0.1)(x)
        
        # Select base model
        if base_model_name == 'MobileNetV2':
            base_model = tf.keras.applications.MobileNetV2(
                weights='imagenet',
                include_top=False,
                input_shape=self.input_shape
            )
            preprocess_input = tf.keras.applications.mobilenet_v2.preprocess_input
        elif base_model_name == 'EfficientNetB0':
            base_model = tf.keras.applications.EfficientNetB0(
                weights='imagenet',
                include_top=False,
                input_shape=self.input_shape
            )
            preprocess_input = tf.keras.applications.efficientnet.preprocess_input
        elif base_model_name == 'ResNet50':
            base_model = tf.keras.applications.ResNet50(
                weights='imagenet',
                include_top=False,
                input_shape=self.input_shape
            )
            preprocess_input = tf.keras.applications.resnet.preprocess_input
        else:
            raise ValueError(f"Unknown base model: {base_model_name}")
        
        # Freeze base model
        base_model.trainable = False
        
        # Preprocessing
        x = preprocess_input(x)
        
        # Base model
        x = base_model(x, training=False)
        
        # Classification head
        x = layers.GlobalAveragePooling2D()(x)
        x = layers.BatchNormalization()(x)
        
        x = layers.Dense(512, activation='relu')(x)
        x = layers.Dropout(0.5)(x)
        x = layers.BatchNormalization()(x)
        
        x = layers.Dense(256, activation='relu')(x)
        x = layers.Dropout(0.3)(x)
        
        # Output
        outputs = layers.Dense(self.num_classes, activation='softmax')(x)
        
        self.model = models.Model(inputs, outputs, name=f'CropDisease_{base_model_name}')
        return self.model
    
    def compile_model(self, learning_rate=0.001):
        """
        Compile the model with optimizer and loss function
        """
        if self.model is None:
            raise ValueError("Model not built. Call build_custom_cnn() or build_transfer_learning_model() first.")
        
        # Use only accuracy metric for compatibility
        self.model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
    def get_model_summary(self):
        """Print model summary"""
        if self.model:
            self.model.summary()
        else:
            print("❌ Model not built yet. Call build method first.")


def get_class_weights(train_data):
    """
    Calculate class weights for imbalanced dataset
    """
    from sklearn.utils.class_weight import compute_class_weight
    import numpy as np
    
    # Get all labels
    labels = []
    for i in range(len(train_data)):
        _, batch_labels = train_data[i]
        labels.extend(np.argmax(batch_labels, axis=1))
    
    # Calculate class weights
    class_weights = compute_class_weight(
        class_weight='balanced',
        classes=np.unique(labels),
        y=labels
    )
    
    return dict(enumerate(class_weights))


if __name__ == "__main__":
    # Test model creation
    model = CropDiseaseModel(num_classes=15)
    model.build_transfer_learning_model('MobileNetV2')
    model.compile_model()
    model.get_model_summary()