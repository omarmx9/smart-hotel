/**
 * @file FacialRecognition_mgr.h
 * @brief Main Orchestrator API
 * 
 * Public API that coordinates the entire face recognition system.
 * All external systems interact through this interface.
 */

#ifndef FACIAL_RECOGNITION_MGR_H
#define FACIAL_RECOGNITION_MGR_H

#include "../app/app_face_recognizer/app_face_recognizer.h"

namespace FacialRecognition_mgr {

/**
 * @brief System state enumeration
 */
enum class State {
    UNINITIALIZED,
    INITIALIZING,
    READY,
    RUNNING,
    ERROR
};

/**
 * @brief Initialize all subsystems
 * 
 * Initializes in order:
 * 1. HAL layer (camera, LED, memory)
 * 2. Drivers (TFLite model)
 * 3. Application modules
 * 
 * @return true on success, false on failure
 */
bool init();

/**
 * @brief Process a single frame and run inference
 * 
 * Captures frame, preprocesses, runs inference, and returns result.
 * 
 * @return Face recognition result
 */
app::FaceResult processFrame();

/**
 * @brief Main event loop iteration
 * 
 * Call this in Arduino loop() - handles frame capture,
 * inference, and visual feedback.
 */
void run();

/**
 * @brief Get current system state
 * @return Current state
 */
State getState();

/**
 * @brief Get last recognition result
 * @return Last FaceResult
 */
app::FaceResult getLastResult();

/**
 * @brief Reset system (reinitialize on error)
 * @return true if reset successful
 */
bool reset();

/**
 * @brief Check if system is ready
 * @return true if ready for inference
 */
bool isReady();

/**
 * @brief Set confidence threshold
 * @param threshold Value between 0.0 and 1.0
 */
void setConfidenceThreshold(float threshold);

/**
 * @brief Get total frames processed since startup
 * @return Frame count
 */
int getFramesProcessed();

/**
 * @brief Get total faces recognized since startup
 * @return Recognition count
 */
int getFacesRecognized();

}  // namespace FacialRecognition_mgr

#endif // FACIAL_RECOGNITION_MGR_H
