// Auto-generated class labels
// Generated from: class_labels.json
// Number of classes: 5
//
// Copy this to your ESP32 project to keep labels in sync with training

#ifndef CLASS_LABELS_H
#define CLASS_LABELS_H

#define NUM_CLASSES 5

// Class labels array - order matches model output indices
static const char* kLabels[NUM_CLASSES] = {
    "maha",
    "mokhtar",
    "omar",
    "radwan",
    "tarek"
};

// Helper function to get label from index
inline const char* get_class_label(int index) {
    if (index >= 0 && index < NUM_CLASSES) {
        return kLabels[index];
    }
    return "Unknown";
}

#endif // CLASS_LABELS_H
