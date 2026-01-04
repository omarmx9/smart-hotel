"""
Live Camera Face Recognition Test - FLOAT32 Model
Tests the trained Keras model (non-quantized) using your webcam
This tests if quantization is causing low confidence scores
Press 'q' to quit, 's' to save a screenshot
"""

import cv2
import numpy as np
from tensorflow import keras
import json
from pathlib import Path
import time

# ==================== CONFIGURATION ====================
SCRIPT_DIR = Path(__file__).parent.resolve()
MODEL_DIR = SCRIPT_DIR / '../trained_models'

# Find the latest model
model_dirs = sorted([d for d in MODEL_DIR.iterdir() if d.is_dir()], reverse=True)
if not model_dirs:
    raise FileNotFoundError("No trained models found! Run train_facial_recognition.py first.")

LATEST_MODEL = model_dirs[0]
KERAS_MODEL_PATH = LATEST_MODEL / 'face_recognition_model.keras'
CLASS_LABELS_PATH = LATEST_MODEL / 'class_labels.json'

# Model input size (must match training)
INPUT_SIZE = (96, 96)

# Confidence threshold - predictions below this are marked as "Unknown"
CONFIDENCE_THRESHOLD = 0.6

# Camera settings
CAMERA_ID = 0  # Change to 1, 2, etc. if you have multiple cameras
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ==================== LOAD MODEL ====================
print("="*60)
print("LIVE CAMERA FACE RECOGNITION TEST - FLOAT32 MODEL")
print("="*60)
print(f"\nLoading model from: {LATEST_MODEL.name}")

# Load class labels
with open(CLASS_LABELS_PATH, 'r') as f:
    class_labels = json.load(f)
class_labels = {int(k): v for k, v in class_labels.items()}
print(f"Classes: {list(class_labels.values())}")

# Load Keras model (float32)
model = keras.models.load_model(KERAS_MODEL_PATH)
print(f"Model loaded successfully!")
print(f"Model input shape: {model.input_shape}")
print(f"Model output shape: {model.output_shape}")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD:.0%}")

# ==================== FACE DETECTION ====================
# Load OpenCV's pre-trained face detector
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ==================== HELPER FUNCTIONS ====================
def simulate_esp32_cam_quality(frame):
    """
    Simulate ESP32-CAM image quality characteristics:
    - Lower resolution capture then upscale
    - JPEG compression artifacts
    - Slight color shift (ESP32-CAM has different white balance)
    - Added noise
    - Reduced dynamic range
    """
    # 1. Simulate lower resolution capture (ESP32-CAM captures at lower res)
    # Downscale to typical ESP32-CAM resolution then upscale back
    esp_res = (320, 240)  # QVGA - common ESP32-CAM resolution
    small = cv2.resize(frame, esp_res, interpolation=cv2.INTER_LINEAR)
    
    # 2. Simulate JPEG compression (ESP32-CAM uses JPEG)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]  # Lower quality like ESP32
    _, encoded = cv2.imencode('.jpg', small, encode_param)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    
    # 3. Add slight noise (ESP32-CAM sensor noise)
    noise = np.random.normal(0, 5, decoded.shape).astype(np.int16)
    noisy = np.clip(decoded.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # 4. Reduce contrast slightly (ESP32-CAM has lower dynamic range)
    alpha = 0.9  # Contrast reduction
    beta = 10    # Brightness shift
    adjusted = cv2.convertScaleAbs(noisy, alpha=alpha, beta=beta)
    
    # 5. Slight color temperature shift (ESP32-CAM tends to be warmer/cooler)
    # Reduce blue channel slightly, boost red slightly
    b, g, r = cv2.split(adjusted)
    r = np.clip(r.astype(np.int16) + 5, 0, 255).astype(np.uint8)
    b = np.clip(b.astype(np.int16) - 5, 0, 255).astype(np.uint8)
    adjusted = cv2.merge([b, g, r])
    
    # 6. Upscale back to original size
    result = cv2.resize(adjusted, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
    
    return result

def preprocess_frame(frame, target_size=INPUT_SIZE, simulate_esp=True):
    """Preprocess a frame for the model - matches training preprocessing"""
    # Apply ESP32-CAM quality simulation if enabled
    if simulate_esp:
        frame = simulate_esp32_cam_quality(frame)
    
    # Resize to model input size
    resized = cv2.resize(frame, target_size)
    # Convert BGR to RGB
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    # Normalize to [-1, 1] for MobileNetV2 (exactly as in training)
    normalized = (rgb.astype(np.float32) / 127.5) - 1.0
    # Add batch dimension
    batched = np.expand_dims(normalized, axis=0)
    return batched

def predict(frame, simulate_esp=True):
    """Run inference on a frame"""
    preprocessed = preprocess_frame(frame, simulate_esp=simulate_esp)
    predictions = model.predict(preprocessed, verbose=0)
    return predictions[0]

def get_color_for_confidence(confidence):
    """Get color based on confidence level"""
    if confidence >= 0.8:
        return (0, 255, 0)  # Green - high confidence
    elif confidence >= 0.6:
        return (0, 255, 255)  # Yellow - medium confidence
    else:
        return (0, 0, 255)  # Red - low confidence

# ==================== MAIN LOOP ====================
def main():
    print(f"\nOpening camera {CAMERA_ID}...")
    cap = cv2.VideoCapture(CAMERA_ID)
    
    if not cap.isOpened():
        print("Error: Could not open camera!")
        print("Try changing CAMERA_ID to 1 or 2")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    
    print("\n" + "="*60)
    print("CONTROLS:")
    print("  q - Quit")
    print("  s - Save screenshot")
    print("  f - Toggle face detection mode")
    print("  e - Toggle ESP32-CAM quality simulation")
    print("  +/- - Adjust confidence threshold")
    print("="*60)
    print("\nESP32-CAM quality simulation: ON (press 'e' to toggle)")
    print("Testing FLOAT32 (non-quantized) model...")
    print("Compare confidence scores with INT8 quantized model\n")
    
    fps_time = time.time()
    frame_count = 0
    fps = 0
    use_face_detection = True
    confidence_threshold = CONFIDENCE_THRESHOLD
    simulate_esp = True  # ESP32-CAM quality simulation
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame!")
            break
        
        # Mirror the frame for more intuitive interaction
        frame = cv2.flip(frame, 1)
        display_frame = frame.copy()
        
        if use_face_detection:
            # Detect faces
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(60, 60))
            
            for (x, y, w, h) in faces:
                # Add padding around face
                padding = int(w * 0.2)
                x1 = max(0, x - padding)
                y1 = max(0, y - padding)
                x2 = min(frame.shape[1], x + w + padding)
                y2 = min(frame.shape[0], y + h + padding)
                
                # Extract face region
                face_roi = frame[y1:y2, x1:x2]
                
                # Predict with ESP32-CAM simulation
                predictions = predict(face_roi, simulate_esp=simulate_esp)
                predicted_class = np.argmax(predictions)
                confidence = predictions[predicted_class]
                
                # Get label and color
                if confidence >= confidence_threshold:
                    label = f"{class_labels[predicted_class]}: {confidence:.1%}"
                    color = get_color_for_confidence(confidence)
                else:
                    label = f"Unknown: {confidence:.1%}"
                    color = (128, 128, 128)  # Gray for unknown
                
                # Draw rectangle and label
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label background
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(display_frame, 
                             (x1, y1 - label_size[1] - 10), 
                             (x1 + label_size[0] + 10, y1), 
                             color, -1)
                cv2.putText(display_frame, label, (x1 + 5, y1 - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                
                # Show all class probabilities on the side
                for i, (class_id, class_name) in enumerate(class_labels.items()):
                    prob = predictions[class_id]
                    bar_width = int(prob * 100)
                    bar_color = (0, 255, 0) if class_id == predicted_class else (100, 100, 100)
                    
                    y_pos = 80 + i * 25
                    cv2.rectangle(display_frame, (10, y_pos), (10 + bar_width, y_pos + 15), bar_color, -1)
                    cv2.putText(display_frame, f"{class_name}: {prob:.1%}", (120, y_pos + 12),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        else:
            # Full frame prediction (no face detection)
            predictions = predict(frame, simulate_esp=simulate_esp)
            predicted_class = np.argmax(predictions)
            confidence = predictions[predicted_class]
            
            if confidence >= confidence_threshold:
                label = f"{class_labels[predicted_class]}: {confidence:.1%}"
                color = get_color_for_confidence(confidence)
            else:
                label = f"Unknown: {confidence:.1%}"
                color = (128, 128, 128)
            
            cv2.putText(display_frame, label, (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
            
            # Show all probabilities
            for i, (class_id, class_name) in enumerate(class_labels.items()):
                prob = predictions[class_id]
                bar_width = int(prob * 150)
                bar_color = (0, 255, 0) if class_id == predicted_class else (100, 100, 100)
                
                y_pos = 100 + i * 30
                cv2.rectangle(display_frame, (10, y_pos), (10 + bar_width, y_pos + 20), bar_color, -1)
                cv2.putText(display_frame, f"{class_name}: {prob:.1%}", (170, y_pos + 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Calculate FPS
        frame_count += 1
        if time.time() - fps_time >= 1.0:
            fps = frame_count
            frame_count = 0
            fps_time = time.time()
        
        # Draw info overlay
        mode_text = "Face Detection ON" if use_face_detection else "Full Frame Mode"
        esp_text = "ESP32-SIM" if simulate_esp else "HD"
        cv2.putText(display_frame, f"FPS: {fps} | {mode_text} | FLOAT32 | {esp_text}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(display_frame, f"Threshold: {confidence_threshold:.0%}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Show frame
        cv2.imshow('Face Recognition Test - FLOAT32', display_frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            # Save screenshot
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f'screenshot_float32_{timestamp}.jpg'
            cv2.imwrite(filename, display_frame)
            print(f"Screenshot saved: {filename}")
        elif key == ord('f'):
            use_face_detection = not use_face_detection
            print(f"Face detection: {'ON' if use_face_detection else 'OFF'}")
        elif key == ord('e'):
            simulate_esp = not simulate_esp
            print(f"ESP32-CAM simulation: {'ON' if simulate_esp else 'OFF'}")
        elif key == ord('+') or key == ord('='):
            confidence_threshold = min(0.95, confidence_threshold + 0.05)
            print(f"Threshold: {confidence_threshold:.0%}")
        elif key == ord('-'):
            confidence_threshold = max(0.1, confidence_threshold - 0.05)
            print(f"Threshold: {confidence_threshold:.0%}")
    
    cap.release()
    cv2.destroyAllWindows()
    print("\nCamera test ended.")
    print("\nCompare the confidence scores with the INT8 quantized model:")
    print("  - Higher scores with FLOAT32 = quantization is the issue")
    print("  - Similar low scores = model needs retraining with better data/settings")

if __name__ == '__main__':
    main()
