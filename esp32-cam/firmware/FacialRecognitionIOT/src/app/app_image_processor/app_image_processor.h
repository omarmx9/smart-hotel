/**
 * @file app_image_processor.h
 * @brief Image Processing Module
 * 
 * Image cropping, resizing, RGB565 to model format conversion
 */

#ifndef APP_IMAGE_PROCESSOR_H
#define APP_IMAGE_PROCESSOR_H

#include "esp_camera.h"
#include "tensorflow/lite/micro/micro_interpreter.h"

namespace app {

/**
 * @brief Process camera frame for model input
 * 
 * Crops, resizes, and normalizes RGB565 frame to model input format
 * 
 * @param fb Camera frame buffer (RGB565)
 * @param input Model input tensor (uint8 or float32)
 */
void processImage(camera_fb_t* fb, TfLiteTensor* input);

/**
 * @brief Convert RGB565 pixel to RGB888
 * @param pixel RGB565 pixel
 * @param r Output red (0-255)
 * @param g Output green (0-255)
 * @param b Output blue (0-255)
 */
void rgb565ToRgb888(uint16_t pixel, uint8_t* r, uint8_t* g, uint8_t* b);

}  // namespace app

#endif // APP_IMAGE_PROCESSOR_H
