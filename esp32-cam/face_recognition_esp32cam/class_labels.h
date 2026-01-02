// Auto-generated class labels
// Generated from: class_labels.json

#ifndef CLASS_LABELS_H
#define CLASS_LABELS_H

#include <array>
#include <string_view>

constexpr std::array<std::string_view, 4> CLASS_LABELS = {
    "maha",
    "omar",
    "radwan",
    "tarek"
};

constexpr size_t NUM_CLASSES = 4;

// Function to get label from index
constexpr std::string_view get_class_label(int index) {
    if (index >= 0 && index < NUM_CLASSES) {
        return CLASS_LABELS[index];
    }
    return "Unknown";
}

#endif // CLASS_LABELS_H
