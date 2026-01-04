/**
 * @file app_mqtt_manager.h
 * @brief Application Layer - MQTT Manager
 * 
 * High-level MQTT logic for face recognition results
 */

#ifndef APP_MQTT_MANAGER_H
#define APP_MQTT_MANAGER_H

#include "../app_face_recognizer/app_face_recognizer.h"

namespace app {

/**
 * @brief Initialize MQTT manager
 * @return true on success
 */
bool mqttManagerInit();

/**
 * @brief Publish face detection result to MQTT
 * @param result Face recognition result
 * @return true on success
 */
bool publishFaceDetection(const FaceResult& result);

/**
 * @brief Publish system statistics
 * @param framesProcessed Total frames processed
 * @param faceRecognized Number of recognized faces
 * @return true on success
 */
bool publishStatistics(int framesProcessed, int faceRecognized);

/**
 * @brief Get current MQTT topic (for debugging)
 * @return Topic string
 */
const char* getCurrentTopic();

/**
 * @brief Check if MQTT is ready for publishing
 * @return true if connected and ready
 */
bool isMqttReady();

/**
 * @brief Process any pending MQTT operations
 */
void mqttManagerProcess();

}  // namespace app

#endif // APP_MQTT_MANAGER_H
