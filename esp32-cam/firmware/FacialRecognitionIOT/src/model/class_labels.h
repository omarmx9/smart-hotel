/**
 * @file class_labels.h
 * @brief Face Recognition Class Labels
 * 
 * Auto-generated class labels matching model output indices
 */

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

/**
 * @brief Get label from class index
 * @param index Class index (0 to NUM_CLASSES-1)
 * @return Label string or "Unknown" if invalid
 */
inline const char* getClassLabel(int index) {
    if (index >= 0 && index < NUM_CLASSES) {
        return kLabels[index];
    }
    return "Unknown";
}

#endif // CLASS_LABELS_H
