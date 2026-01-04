/**
 * @file app_face_recognizer.h
 * @brief Face Recognition Module
 * 
 * Face recognition inference pipeline and result processing
 */

#ifndef APP_FACE_RECOGNIZER_H
#define APP_FACE_RECOGNIZER_H

#include <cstdint>

namespace app {

/**
 * @brief Face recognition result structure
 */
struct FaceResult {
    const char* label;      // Predicted label or "Unknown"
    int classIndex;         // Class index (0 to NUM_CLASSES-1), -1 if unknown
    float confidence;       // Confidence score (0.0 to 1.0)
    bool recognized;        // true if confidence >= threshold
    unsigned long inferenceTimeMs;  // Inference time in milliseconds
};

/**
 * @brief Process model output and get recognition result
 * @return FaceResult structure with prediction details
 */
FaceResult processOutput();

/**
 * @brief Get the last recognition result
 * @return Last FaceResult
 */
FaceResult getLastResult();

/**
 * @brief Set confidence threshold
 * @param threshold Threshold value (0.0 to 1.0)
 */
void setConfidenceThreshold(float threshold);

/**
 * @brief Get current confidence threshold
 * @return Threshold value
 */
float getConfidenceThreshold();

}  // namespace app

#endif // APP_FACE_RECOGNIZER_H
