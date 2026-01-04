/**
 * @file hal_camera.h
 * @brief Hardware Abstraction Layer - Camera Interface
 * 
 * Low-level camera hardware initialization and frame capture
 */

#ifndef HAL_CAMERA_H
#define HAL_CAMERA_H

#include <esp_err.h>
#include "esp_camera.h"

namespace hal {

/**
 * @brief Initialize camera hardware
 * @return ESP_OK on success, error code otherwise
 */
esp_err_t cameraInit();

/**
 * @brief Capture a frame from the camera
 * @return Pointer to frame buffer, or nullptr on failure
 */
camera_fb_t* cameraCapture();

/**
 * @brief Return frame buffer to driver
 * @param fb Frame buffer pointer
 */
void cameraRelease(camera_fb_t* fb);

/**
 * @brief Get camera sensor handle for configuration
 * @return Sensor handle or nullptr
 */
sensor_t* cameraGetSensor();

/**
 * @brief Check if camera is initialized
 * @return true if initialized
 */
bool cameraIsReady();

}  // namespace hal

#endif // HAL_CAMERA_H
