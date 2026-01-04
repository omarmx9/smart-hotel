"""
TensorFlow Facial Recognition Training Pipeline
Trains a custom face recognition model using transfer learning with MobileNetV2
Converts to TFLite for deployment on ESP32-CAM
"""

import os
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import MobileNetV2
from pathlib import Path
import json
from datetime import datetime

# ==================== CONFIGURATION ====================
# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.resolve()

CONFIG = {
    'dataset_path': SCRIPT_DIR / '../dataset',  # Dataset is one level up from ai/ folder
    'models_output': SCRIPT_DIR / '../trained_models',
    'img_size': (96, 96),  # Smaller input size for ESP32 (saves memory)
    'batch_size': 16,
    'epochs': 200,  # More epochs for better convergence
    'validation_split': 0.2,  # 15% for validation
    'learning_rate': 0.0001,  # Learning rate for loss optimization
    'mobilenet_alpha': 0.5,  # Model size (~1.5MB model)
    'augmentation_target': 200,  # Moderate augmentation
    'debug': True,  # Enable debug output
    # Loss-focused training parameters
    'min_delta_loss': 0.001,  # Minimum improvement in loss to continue training
    'patience_loss': 15,  # Patience for early stopping based on loss
}

# ==================== SETUP ====================
def setup_directories():
    """Create necessary output directories"""
    os.makedirs(CONFIG['models_output'], exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_dir = os.path.join(CONFIG['models_output'], f'model_{timestamp}')
    os.makedirs(model_dir, exist_ok=True)
    return model_dir

# ==================== DATA LOADING & PREPROCESSING ====================
def load_and_preprocess_images(dataset_path, img_size):
    """
    Load all images from dataset directory structure:
    dataset_path/
    ├── person1/
    │   ├── img1.jpg
    │   └── img2.jpg
    ├── person2/
    ...
    
    Returns: (X, y, class_labels)
    """
    X = []
    y = []
    class_labels = {}
    class_idx = 0
    
    dataset_path = Path(dataset_path)
    
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
    
    # Load images from each person's directory
    for person_dir in sorted(dataset_path.iterdir()):
        if person_dir.is_dir():
            person_name = person_dir.name
            class_labels[class_idx] = person_name
            print(f"Loading images for {person_name} (class {class_idx})...")
            
            image_count = 0
            for img_path in person_dir.glob('*'):
                if img_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    try:
                        img = keras.preprocessing.image.load_img(
                            img_path, 
                            target_size=img_size
                        )
                        img_array = keras.preprocessing.image.img_to_array(img)
                        X.append(img_array)
                        y.append(class_idx)
                        image_count += 1
                    except Exception as e:
                        print(f"Error loading {img_path}: {e}")
            
            print(f"  ✓ Loaded {image_count} images for {person_name}")
            class_idx += 1
    
    # Add "unknown" class for random non-face images (you should add some!)
    # For now, we'll create synthetic "unknown" by using augmented versions
    print(f"\nDataset structure created:")
    print(f"  Total classes: {class_idx}")
    print(f"  Total images: {len(X)}")
    
    X = np.array(X, dtype='float32')
    y = np.array(y)
    
    # Normalize to [-1, 1] range (MobileNetV2 prefers this)
    X = (X / 127.5) - 1.0
    
    return X, y, class_labels

# ==================== DATA AUGMENTATION ====================
def augment_dataset_balanced(X, y, class_labels, target_samples_per_class=None):
    """
    Class-balanced augmentation to handle imbalanced datasets.
    Augments smaller classes MORE to reach target sample count.
    
    Args:
        X: Original images (normalized to [-1, 1])
        y: Labels
        class_labels: Dict of class_idx -> name
        target_samples_per_class: Target count per class (default: max_class * 1.5)
    
    Returns:
        Balanced X, y arrays
    """
    print(f"\n🔄 CLASS-BALANCED AUGMENTATION")
    print("="*50)
    
    # Analyze class distribution
    unique, counts = np.unique(y, return_counts=True)
    class_counts = dict(zip(unique, counts))
    max_count = max(counts)
    
    # Target: bring all classes to just match the largest class (minimal augmentation)
    # Less synthetic data = higher confidence on real faces
    if target_samples_per_class is None:
        target_samples_per_class = int(max_count * 1.0)  # Just balance, don't over-augment
    
    print(f"📊 Original distribution:")
    for class_idx, count in class_counts.items():
        print(f"   {class_labels[class_idx]}: {count} images")
    print(f"\n🎯 Target per class: {target_samples_per_class} samples")
    
    # Create augmentation generator with MINIMAL augmentation
    # Less augmentation = higher confidence on real data
    datagen = ImageDataGenerator(
        rotation_range=10,           # Minimal rotation for higher confidence
        width_shift_range=0.1,       # Minimal shifts
        height_shift_range=0.1,
        shear_range=0.05,            # Minimal shear
        zoom_range=0.1,              # Minimal zoom
        horizontal_flip=True,
        brightness_range=[0.9, 1.1], # Very tight brightness range
        fill_mode='nearest'
    )
    
    # Convert back to [0, 255] for augmentation
    X_uint8 = ((X + 1.0) * 127.5).astype('uint8')
    
    X_balanced = []
    y_balanced = []
    
    for class_idx in unique:
        class_name = class_labels[class_idx]
        class_mask = (y == class_idx)
        X_class = X[class_mask]
        X_class_uint8 = X_uint8[class_mask]
        original_count = len(X_class)
        
        # Calculate augmentation factor for this class
        augment_count = target_samples_per_class - original_count
        
        if augment_count <= 0:
            # Class already has enough samples, skip augmentation
            aug_factor = 0
            augment_count = 0
            print(f"\n👤 {class_name}: {original_count} samples (no augmentation needed, already above target)")
        else:
            aug_factor = augment_count // original_count + 1
            print(f"\n👤 {class_name}: {original_count} → ~{original_count + augment_count} samples (aug factor: {aug_factor}x)")
        
        # Add original images
        X_balanced.extend(X_class)
        y_balanced.extend([class_idx] * original_count)
        
        # Generate augmented images
        augmented_generated = 0
        while augmented_generated < augment_count:
            for img_uint8, img_norm in zip(X_class_uint8, X_class):
                if augmented_generated >= augment_count:
                    break
                
                # Generate augmented image
                img_reshaped = img_uint8.reshape((1,) + img_uint8.shape)
                aug_iter = datagen.flow(img_reshaped, batch_size=1)
                aug_img = next(aug_iter)[0]
                
                # Normalize back to [-1, 1]
                aug_img = (aug_img / 127.5) - 1.0
                
                X_balanced.append(aug_img)
                y_balanced.append(class_idx)
                augmented_generated += 1
        
        print(f"   ✓ Generated {augmented_generated} augmented images")
    
    X_final = np.array(X_balanced, dtype='float32')
    y_final = np.array(y_balanced)
    
    # Shuffle
    indices = np.random.permutation(len(X_final))
    X_final = X_final[indices]
    y_final = y_final[indices]
    
    # Print final distribution
    print(f"\n📊 Final balanced distribution:")
    unique_final, counts_final = np.unique(y_final, return_counts=True)
    for class_idx, count in zip(unique_final, counts_final):
        print(f"   {class_labels[class_idx]}: {count} images")
    
    print(f"\n✓ Total: {len(X)} → {len(X_final)} samples")
    
    return X_final, y_final


def augment_dataset(X, y, augmentation_factor=5):
    """
    LEGACY: Simple uniform augmentation (kept for compatibility).
    Use augment_dataset_balanced() for imbalanced datasets.
    """
    print(f"\n🔄 Augmenting dataset (factor: {augmentation_factor}x)...")
    
    # Create augmentation generator
    datagen = ImageDataGenerator(
        rotation_range=20,
        width_shift_range=0.2,
        height_shift_range=0.2,
        shear_range=0.15,
        zoom_range=0.2,
        horizontal_flip=True,
        brightness_range=[0.8, 1.2],
        fill_mode='nearest'
    )
    
    # Convert back to [0, 255] for augmentation
    X_original = ((X + 1.0) * 127.5).astype('uint8')
    
    X_augmented = [X]  # Start with original
    y_augmented = [y]
    
    for i in range(augmentation_factor):
        batch_augmented = []
        for img in X_original:
            # Reshape for datagen
            img_reshaped = img.reshape((1,) + img.shape)
            # Generate one augmented image
            aug_iter = datagen.flow(img_reshaped, batch_size=1)
            aug_img = next(aug_iter)[0]
            # Normalize back to [-1, 1]
            aug_img = (aug_img / 127.5) - 1.0
            batch_augmented.append(aug_img)
        
        X_augmented.append(np.array(batch_augmented))
        y_augmented.append(y.copy())
        print(f"  ✓ Augmentation batch {i+1}/{augmentation_factor} complete")
    
    X_final = np.concatenate(X_augmented, axis=0)
    y_final = np.concatenate(y_augmented, axis=0)
    
    # Shuffle
    indices = np.random.permutation(len(X_final))
    X_final = X_final[indices]
    y_final = y_final[indices]
    
    print(f"  ✓ Dataset augmented: {len(X)} → {len(X_final)} samples")
    
    return X_final, y_final

# ==================== MODEL BUILDING ====================
def build_transfer_learning_model(num_classes, img_size):
    """
    Build a facial recognition model using MobileNetV2 as base.
    Full fine-tuning - keep original architecture, just replace classifier.
    """
    
    # Pre-trained MobileNetV2 base model with original pooling
    base_model = MobileNetV2(
        input_shape=(*img_size, 3),
        include_top=False,
        weights='imagenet',
        alpha=CONFIG['mobilenet_alpha'],
        pooling='avg'  # Use MobileNetV2's built-in global average pooling
    )
    
    # Fine-tune entire model
    base_model.trainable = True
    
    # Build model - just add final classifier
    inputs = keras.Input(shape=(*img_size, 3))
    x = base_model(inputs, training=True)
    outputs = layers.Dense(num_classes, activation='softmax', name='predictions')(x)
    
    model = keras.Model(inputs=inputs, outputs=outputs, name='FacialRecognition')
    
    return model

# ==================== TRAINING ====================
def train_model(X, y, class_labels, model_dir):
    """
    Loss-focused training approach with accuracy monitoring.
    Primary focus: minimize validation loss
    Secondary metric: track accuracy for reference
    """
    
    num_classes = len(class_labels)
    
    # Split data
    from sklearn.model_selection import train_test_split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=CONFIG['validation_split'], 
        random_state=42, stratify=y
    )
    print(f"\n📊 Training set: {len(X_train)} samples")
    print(f"📊 Validation set: {len(X_val)} samples")
    
    print("\n" + "="*60)
    print("BUILDING MODEL")
    print("="*60)
    
    model = build_transfer_learning_model(num_classes, CONFIG['img_size'])
    
    print(f"\nModel summary:")
    model.summary()
    
    # Compile - focus on LOSS optimization, track ACCURACY for reference
    print("\n" + "="*60)
    print("TRAINING (Loss-focused optimization + Accuracy tracking)")
    print("="*60)
    
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=CONFIG['learning_rate']),
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy']  # Track accuracy but don't optimize for it
    )
    
    # Loss-focused callbacks
    callbacks = [
        # Early stopping based on validation LOSS
        keras.callbacks.EarlyStopping(
            monitor='val_loss',
            min_delta=CONFIG['min_delta_loss'],
            patience=CONFIG['patience_loss'],
            restore_best_weights=True,
            verbose=1,
            mode='min'  # Minimize loss
        ),
        # Reduce learning rate when loss plateaus
        keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=8,
            min_lr=1e-7,
            verbose=1,
            mode='min'
        ),
        # Custom callback to log both loss and accuracy every epoch
        keras.callbacks.LambdaCallback(
            on_epoch_end=lambda epoch, logs: print(
                f"Epoch {epoch+1}: "
                f"train_loss={logs['loss']:.4f}, "
                f"val_loss={logs['val_loss']:.4f}, "
                f"train_acc={logs['accuracy']:.4f}, "
                f"val_acc={logs['val_accuracy']:.4f}"
            )
        )
    ]
    
    history = model.fit(
        X_train, y_train,
        batch_size=CONFIG['batch_size'],
        epochs=CONFIG['epochs'],
        validation_data=(X_val, y_val),
        callbacks=callbacks,
        verbose=1
    )
    
    # Report final metrics
    final_train_loss = history.history.get('loss', [float('inf')])[-1]
    final_val_loss = history.history.get('val_loss', [float('inf')])[-1]
    final_train_acc = history.history.get('accuracy', [0])[-1]
    final_val_acc = history.history.get('val_accuracy', [0])[-1]
    
    print(f"\n✓ Training complete.")
    print(f"  Final train loss: {final_train_loss:.4f}")
    print(f"  Final val loss: {final_val_loss:.4f}")
    print(f"  Final train accuracy: {final_train_acc*100:.2f}%")
    print(f"  Final val accuracy: {final_val_acc*100:.2f}%")
    
    # Save Keras model
    keras_model_path = os.path.join(model_dir, 'face_recognition_model.keras')
    model.save(keras_model_path)
    print(f"\n✓ Keras model saved to {keras_model_path}")
    
    # Save class labels
    labels_path = os.path.join(model_dir, 'class_labels.json')
    with open(labels_path, 'w') as f:
        json.dump(class_labels, f, indent=2)
    print(f"✓ Class labels saved to {labels_path}")
    
    # Save training history (loss AND accuracy curves)
    history_path = os.path.join(model_dir, 'training_history.json')
    history_dict = {
        'loss': [float(x) for x in history.history.get('loss', [])],
        'val_loss': [float(x) for x in history.history.get('val_loss', [])],
        'accuracy': [float(x) for x in history.history.get('accuracy', [])],
        'val_accuracy': [float(x) for x in history.history.get('val_accuracy', [])],
        'final_train_loss': float(final_train_loss),
        'final_val_loss': float(final_val_loss),
        'final_train_accuracy': float(final_train_acc),
        'final_val_accuracy': float(final_val_acc)
    }
    with open(history_path, 'w') as f:
        json.dump(history_dict, f, indent=2)
    print(f"✓ Training history saved to {history_path}")
    
    return model, history, (X_val, y_val)

# ==================== MODEL CONVERSION ====================
def convert_to_tflite(model, model_dir, X_representative, optimize=True):
    """
    Convert Keras model to TensorFlow Lite format.
    Uses FULL INTEGER QUANTIZATION for ESP32 TFLite Micro compatibility.
    
    Args:
        model: Trained Keras model
        model_dir: Output directory
        X_representative: Sample data for calibration (needed for full int8 quantization)
        optimize: Whether to apply int8 quantization
    """
    
    print("\n" + "="*60)
    print("CONVERTING TO TENSORFLOW LITE")
    print("="*60)
    
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    
    if optimize:
        # FULL INTEGER QUANTIZATION (required for ESP32 TFLite Micro!)
        # This quantizes both weights AND activations to int8
        
        def representative_dataset_gen():
            """Generator that yields representative samples for calibration"""
            # Use MORE samples for better calibration (reduces quantization error)
            # Use diverse samples from different classes and augmented versions
            num_samples = min(500, len(X_representative))  # Increased from 100 to 500
            indices = np.random.choice(len(X_representative), num_samples, replace=False)
            
            print(f"  Calibrating quantization with {num_samples} samples...")
            for i in indices:
                # Yield one sample at a time with batch dimension
                # Keep as float32 [-1, 1] - quantizer needs this to learn proper mapping
                sample = X_representative[i:i+1].astype(np.float32)
                yield [sample]
        
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = representative_dataset_gen
        
        # Force full integer quantization (int8 input/output)
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.uint8   # uint8 input
        converter.inference_output_type = tf.uint8  # uint8 output
        
        tflite_path = os.path.join(model_dir, 'face_recognition_int8.tflite')
        print("✓ Full INT8 quantization enabled (ESP32 TFLite Micro compatible)")
        print("  - Weights: int8")
        print("  - Activations: int8")
        print("  - Input/Output: uint8")
        print("  - Representative dataset: 500 samples for better calibration")
    else:
        tflite_path = os.path.join(model_dir, 'face_recognition_float32.tflite')
        print("Float32 model (larger, not recommended for ESP32)")
    
    tflite_model = converter.convert()
    
    with open(tflite_path, 'wb') as f:
        f.write(tflite_model)
    
    # Get file sizes
    keras_size = os.path.getsize(os.path.join(model_dir, 'face_recognition_model.keras')) / (1024*1024)
    tflite_size = os.path.getsize(tflite_path) / (1024*1024)
    compression = (1 - tflite_size/keras_size) * 100
    
    print(f"\n✓ TFLite model saved to {tflite_path}")
    print(f"\nModel size comparison:")
    print(f"  Keras model: {keras_size:.2f} MB")
    print(f"  TFLite model: {tflite_size:.2f} MB")
    print(f"  Compression: {compression:.1f}%")
    
    return tflite_path

# ==================== EVALUATION ====================
def evaluate_model(model, X, y):
    """Evaluate model - primary focus on loss, secondary focus on accuracy"""
    print("\n" + "="*60)
    print("MODEL EVALUATION")
    print("="*60)
    
    loss, accuracy = model.evaluate(X, y, verbose=0)
    print(f"Validation Loss: {loss:.4f} (PRIMARY METRIC)")
    print(f"Validation Accuracy: {accuracy*100:.2f}% (REFERENCE METRIC)")
    
    return loss, accuracy

# ==================== MAIN ====================
def debug_dataset(X, y, class_labels):
    """Debug and verify dataset before training"""
    print("\n" + "="*60)
    print("DEBUG: DATASET VERIFICATION")
    print("="*60)
    
    print(f"\n📊 Dataset Statistics:")
    print(f"  • Total samples: {len(X)}")
    print(f"  • Image shape: {X[0].shape}")
    print(f"  • Data type: {X.dtype}")
    print(f"  • Value range: [{X.min():.2f}, {X.max():.2f}] (expected: [-1, 1])")
    
    print(f"\n👥 Class Distribution:")
    unique, counts = np.unique(y, return_counts=True)
    for class_idx, count in zip(unique, counts):
        pct = count / len(y) * 100
        print(f"  • {class_labels[class_idx]}: {count} samples ({pct:.1f}%)")
    
    # Check for class imbalance
    max_count = max(counts)
    min_count = min(counts)
    imbalance_ratio = max_count / min_count
    if imbalance_ratio > 2:
        print(f"\n⚠️  WARNING: Class imbalance detected (ratio: {imbalance_ratio:.1f}x)")
        print(f"     Consider adding more images to smaller classes")
    else:
        print(f"\n✓ Class balance OK (ratio: {imbalance_ratio:.1f}x)")
    
    # Train/Val split preview
    val_size = int(len(X) * CONFIG['validation_split'])
    train_size = len(X) - val_size
    print(f"\n📈 Train/Validation Split ({(1-CONFIG['validation_split'])*100:.0f}/{CONFIG['validation_split']*100:.0f}):")
    print(f"  • Training samples: {train_size}")
    print(f"  • Validation samples: {val_size}")
    
    if val_size < len(class_labels):
        print(f"\n⚠️  WARNING: Validation set ({val_size}) smaller than number of classes ({len(class_labels)})")
    
    print("\n" + "="*60)
    return True


def main():
    """Main training pipeline"""
    
    print("\n" + "="*60)
    print("FACIAL RECOGNITION TRAINING PIPELINE")
    print("PRIMARY: Loss Optimization | SECONDARY: Accuracy Tracking")
    print("="*60)
    print(f"TensorFlow version: {tf.__version__}")
    print(f"GPU available: {len(tf.config.list_physical_devices('GPU')) > 0}")
    if tf.config.list_physical_devices('GPU'):
        for gpu in tf.config.list_physical_devices('GPU'):
            print(f"  • {gpu}")
    
    # Setup
    model_dir = setup_directories()
    print(f"\nModel output directory: {model_dir}")
    
    # Load data
    print("\n" + "="*60)
    print("LOADING DATASET")
    print("="*60)
    X, y, class_labels = load_and_preprocess_images(
        CONFIG['dataset_path'],
        CONFIG['img_size']
    )
    
    print(f"\nClass labels: {class_labels}")
    print(f"Data shape: {X.shape}")
    print(f"Labels shape: {y.shape}")
    
    # Debug phase
    if CONFIG['debug']:
        debug_dataset(X, y, class_labels)
    
    # Augment dataset with CLASS BALANCING
    X, y = augment_dataset_balanced(X, y, class_labels, 
                                    target_samples_per_class=CONFIG['augmentation_target'])
    
    # Train (loss-focused with accuracy tracking)
    model, history, (X_val, y_val) = train_model(X, y, class_labels, model_dir)
    
    # Evaluate on validation set
    final_loss, final_accuracy = evaluate_model(model, X_val, y_val)
    
    # Convert to TFLite
    tflite_path = convert_to_tflite(model, model_dir, X_representative=X, optimize=True)
    
    # Summary
    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print("="*60)
    print(f"\n📊 Final Metrics:")
    print(f"  Validation Loss: {final_loss:.4f} (PRIMARY)")
    print(f"  Validation Accuracy: {final_accuracy*100:.2f}% (REFERENCE)")
    print(f"\n📁 Output files in: {model_dir}")
    print(f"  - face_recognition_model.keras (Keras format)")
    print(f"  - face_recognition_int8.tflite (For ESP32 TFLite Micro)")
    print(f"  - class_labels.json (Person labels)")
    print(f"  - training_history.json (Loss + Accuracy curves)")
    print(f"\n📈 Next steps:")
    print(f"  1. Plot loss AND accuracy curves from training_history.json")
    print(f"  2. Test the model with test_camera.py")
    print(f"  3. Run: python3 convert_tflite_to_c.py <model_dir>/face_recognition_int8.tflite")
    print(f"  4. Copy model_data.h to ESP32 firmware
