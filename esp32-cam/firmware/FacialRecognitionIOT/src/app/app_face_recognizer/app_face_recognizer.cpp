/**
 * @file app_face_recognizer.cpp
 * @brief Face Recognition Implementation
 */

#include "app_face_recognizer.h"
#include "../../app_cfg.h"
#include "../../model/class_labels.h"
#include "../../drivers/driver_tflite/driver_tflite.h"

namespace app {

static FaceResult s_lastResult = {"Unknown", -1, 0.0f, false, 0};
static float s_confidenceThreshold = CONFIDENCE_THRESHOLD;

FaceResult processOutput() {
    FaceResult result = {"Unknown", -1, 0.0f, false, 0};
    
    TfLiteTensor* output = driver::tfliteGetOutput();
    if (!output) {
        return result;
    }

    float maxScore = 0.0f;
    int maxIdx = 0;

    if (output->type == kTfLiteUInt8) {
        // Quantized output - dequantize
        for (int i = 0; i < NUM_CLASSES; i++) {
            float score = (output->data.uint8[i] - output->params.zero_point)
                          * output->params.scale;
            if (score > maxScore) {
                maxScore = score;
                maxIdx = i;
            }
        }
    } else if (output->type == kTfLiteFloat32) {
        // Float output
        for (int i = 0; i < NUM_CLASSES; i++) {
            float score = output->data.f[i];
            if (score > maxScore) {
                maxScore = score;
                maxIdx = i;
            }
        }
    }

    result.confidence = maxScore;
    result.classIndex = maxIdx;

    if (maxScore >= s_confidenceThreshold) {
        result.label = getClassLabel(maxIdx);
        result.recognized = true;
    } else {
        result.label = "Unknown";
        result.recognized = false;
    }

    s_lastResult = result;
    return result;
}

FaceResult getLastResult() {
    return s_lastResult;
}

void setConfidenceThreshold(float threshold) {
    if (threshold >= 0.0f && threshold <= 1.0f) {
        s_confidenceThreshold = threshold;
    }
}

float getConfidenceThreshold() {
    return s_confidenceThreshold;
}

}  // namespace app
