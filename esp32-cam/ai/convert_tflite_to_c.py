"""
TFLite to C Array Converter
Converts TensorFlow Lite model to C header for embedded deployment on ESP32
"""

import os
import sys
import json
from pathlib import Path

def tflite_to_c_array(tflite_path, output_header_path, var_name='g_model'):
    """
    Convert TFLite binary model to C-style byte array.
    
    Usage:
        python convert_tflite_to_c.py model.tflite output.h
    """
    
    # Read TFLite model
    with open(tflite_path, 'rb') as f:
        model_data = f.read()
    
    model_size = len(model_data)
    print(f"Model size: {model_size} bytes ({model_size/1024:.2f} KB)")
    
    # Generate C header
    header_content = f"""// Auto-generated TensorFlow Lite model
// Generated from: {Path(tflite_path).name}
// Model size: {model_size} bytes
//
// This model should be placed in PROGMEM (program memory) on ESP32
// Example usage in Arduino:
//   #include "{Path(output_header_path).name}"
//   const uint8_t* model_data = {var_name};
//   size_t model_size = {var_name}_len;

#ifndef MODEL_H
#define MODEL_H

#include <cstdint>
#include <cstddef>

// Model as byte array
const uint8_t {var_name}[] PROGMEM = {{"""
    
    # Add bytes in hex format (16 bytes per line for readability)
    bytes_per_line = 16
    for i in range(0, len(model_data), bytes_per_line):
        chunk = model_data[i:i+bytes_per_line]
        hex_bytes = ', '.join(f'0x{b:02x}' for b in chunk)
        header_content += f'\n    {hex_bytes},'
    
    # Remove last comma and close array
    header_content = header_content.rstrip(',')
    header_content += f'\n}};\n\n'
    
    # Add size constant
    header_content += f'const size_t {var_name}_len = {model_size};\n\n'
    
    header_content += f"""// Model input specifications
// Input shape: (1, 96, 96, 3)
// Input type: uint8 in range [0, 255] (no normalization)
// Output shape: (1, num_classes)
// Output type: uint8 (quantized probabilities, dequantize if needed)

#endif // MODEL_H
"""
    
    # Write header file
    os.makedirs(os.path.dirname(output_header_path), exist_ok=True)
    with open(output_header_path, 'w') as f:
        f.write(header_content)
    
    print(f"✓ C header generated: {output_header_path}")
    print(f"  File size: {os.path.getsize(output_header_path) / 1024:.2f} KB")
    
    return output_header_path

def generate_class_labels_header(class_labels_json, output_header_path):
    """Generate C header with class labels mapping - compatible with ESP32/Arduino"""
    
    with open(class_labels_json, 'r') as f:
        labels = json.load(f)
    
    num_classes = len(labels)
    
    header_content = f"""// Auto-generated class labels
// Generated from: {Path(class_labels_json).name}
// Number of classes: {num_classes}
//
// Copy this to your ESP32 project to keep labels in sync with training

#ifndef CLASS_LABELS_H
#define CLASS_LABELS_H

#define NUM_CLASSES {num_classes}

// Class labels array - order matches model output indices
static const char* kLabels[NUM_CLASSES] = {{"""
    
    for idx in sorted(int(k) for k in labels.keys()):
        label = labels[str(idx)]
        header_content += f'\n    "{label}",'
    
    header_content = header_content.rstrip(',')
    header_content += f'\n}};\n\n'
    
    header_content += f"""// Helper function to get label from index
inline const char* get_class_label(int index) {{
    if (index >= 0 && index < NUM_CLASSES) {{
        return kLabels[index];
    }}
    return "Unknown";
}}

#endif // CLASS_LABELS_H
"""
    
    os.makedirs(os.path.dirname(output_header_path), exist_ok=True)
    with open(output_header_path, 'w') as f:
        f.write(header_content)
    
    print(f"✓ Class labels header generated: {output_header_path}")
    print(f"  Classes ({num_classes}): {', '.join(labels[str(i)] for i in range(num_classes))}")
    return output_header_path

def main():
    """Main converter"""
    
    if len(sys.argv) < 2:
        print("Usage: python convert_tflite_to_c.py <model.tflite> [output_dir]")
        print("\nExample:")
        print("  python convert_tflite_to_c.py face_recognition.tflite ./esp32_model")
        sys.exit(1)
    
    tflite_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '.'
    
    if not os.path.exists(tflite_path):
        print(f"Error: Model file not found: {tflite_path}")
        sys.exit(1)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Convert model
    model_header = os.path.join(output_dir, 'model_data.h')
    tflite_to_c_array(tflite_path, model_header, 'face_recognition_model')
    
    # Try to find and convert class labels if they exist
    model_dir = os.path.dirname(tflite_path)
    labels_json = os.path.join(model_dir, 'class_labels.json')
    
    if os.path.exists(labels_json):
        labels_header = os.path.join(output_dir, 'class_labels.h')
        generate_class_labels_header(labels_json, labels_header)
    
    print(f"\n✓ Conversion complete!")
    print(f"  Output directory: {output_dir}")
    print(f"\nNext steps:")
    print(f"  1. Copy the header files to your ESP32 project")
    print(f"  2. Include the headers in your inference code")
    print(f"  3. Use TensorFlow Lite Micro interpreter to run inference")

if __name__ == '__main__':
    main()
