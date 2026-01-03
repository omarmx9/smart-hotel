"""
Live Camera Face Recognition Test
Tests the trained TFLite model using your webcam
Press 'q' to quit, 's' to save a screenshot
"""

import cv2
import numpy as np
import tensorflow as tf
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
TFLITE_MODEL_PATH = LATEST_MODEL / 'face_recognition_int8.tflite'
CLASS_LABELS_PATH = LATEST_MODEL / 'class_labels.json'

# Model input size (must match training)
INPUT_SIZE = (96, 96)

# Confidence threshold - predictions below this are marked as "Unknown"
CONFIDENCE_THRESHOLD = 0.9

# Camera settings
CAMERA_ID = 0  # Change to 1, 2, etc. if you have multiple cameras
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ==================== LOAD MODEL ====================
print("="*60)
print("LIVE CAMERA FACE RECOGNITION TEST")
print("="*60)
print(f"\nLoading model from: {LATEST_MODEL.name}")

# Load class labels
with open(CLASS_LABELS_PATH, 'r') as f:
    class_labels = json.load(f)
class_labels = {int(k): v for k, v in class_labels.items()}
print(f"Classes: {list(class_labels.values())}")

# Load TFLite model
interpreter = tf.lite.Interpreter(model_path=str(TFLITE_MODEL_PATH))
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

print(f"Model input shape: {input_details[0]['shape']}")
print(f"Model input dtype: {input_details[0]['dtype']}")
print(f"Input quantization: {input_details[0]['quantization']}")
print(f"Output quantization: {output_details[0]['quantization']}")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD:.0%}")

# ==================== FACE DETECTION ====================
# Load OpenCV's pre-trained face detector
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ==================== HELPER FUNCTIONS ====================
def preprocess_frame(frame, target_size=INPUT_SIZE):
    """Preprocess a frame for the model - MUST match ESP32 preprocessing"""
    # Resize to model input size
    resized = cv2.resize(frame, target_size)
    # Convert BGR to RGB
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    
    # For quantized model: use raw uint8 values (0-255) - NO normalization
    # This matches the ESP32 code exactly
    if input_details[0]['dtype'] == np.uint8:
        batched = np.expand_dims(rgb, axis=0)
    else:
        # For float model: normalize to [-1, 1] for MobileNetV2
        normalized = (rgb.astype(np.float32) / 127.5) - 1.0
        batched = np.expand_dims(normalized, axis=0)
    
    return batched

def predict(frame):
    """Run inference on a frame"""
    preprocessed = preprocess_frame(frame)
    interpreter.set_tensor(input_details[0]['index'], preprocessed)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])

    # Dequantize output properly based on quantization parameters
    output_details_info = output_details[0]
    scale, zero_point = output_details_info['quantization']
    
    if output_details_info['dtype'] == np.uint8:
        # For uint8 output: dequantize using scale and zero_point
        # Formula: real_value = (quantized_value - zero_point) * scale
        output = (output.astype(np.float32) - zero_point) * scale
    elif output_details_info['dtype'] == np.int8:
        # For int8 output: same dequantization formula
        output = (output.astype(np.float32) - zero_point) * scale
    # else: already float32, no dequantization needed

    # Output is now in the same range as the trained model (logits or probabilities)
    # Since our model has softmax activation, output should already be probabilities
    # But we apply softmax anyway for numerical stability
    output = output[0]
    exp_output = np.exp(output - np.max(output))  # Subtract max for numerical stability
    probabilities = exp_output / np.sum(exp_output)

    return probabilities

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
    print("  +/- - Adjust confidence threshold")
    print("="*60)
    
    fps_time = time.time()
    frame_count = 0
    fps = 0
    use_face_detection = True
    confidence_threshold = CONFIDENCE_THRESHOLD
    
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
                
                # Predict
                predictions = predict(face_roi)
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
            predictions = predict(frame)
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
        cv2.putText(display_frame, f"FPS: {fps} | {mode_text}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(display_frame, f"Threshold: {confidence_threshold:.0%}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Show frame
        cv2.imshow('Face Recognition Test', display_frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            # Save screenshot
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f'screenshot_{timestamp}.jpg'
            cv2.imwrite(filename, display_frame)
            print(f"Screenshot saved: {filename}")
        elif key == ord('f'):
            use_face_detection = not use_face_detection
            print(f"Face detection: {'ON' if use_face_detection else 'OFF'}")
        elif key == ord('+') or key == ord('='):
            confidence_threshold = min(0.95, confidence_threshold + 0.05)
            print(f"Threshold: {confidence_threshold:.0%}")
        elif key == ord('-'):
            confidence_threshold = max(0.1, confidence_threshold - 0.05)
            print(f"Threshold: {confidence_threshold:.0%}")
    
    cap.release()
    cv2.destroyAllWindows()
    print("\nCamera test ended.")

if __name__ == '__main__':
    main()
