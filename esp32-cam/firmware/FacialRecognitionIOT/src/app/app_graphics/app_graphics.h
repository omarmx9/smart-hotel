/**
 * @file app_graphics.h
 * @brief Graphics Module
 * 
 * Drawing boxes and visual feedback on frames
 */

#ifndef APP_GRAPHICS_H
#define APP_GRAPHICS_H

#include "esp_camera.h"
#include "../../app_cfg.h"
#include <cstdint>

namespace app {

// Colors are defined in app_cfg.h (COLOR_GREEN, COLOR_RED, etc.)

/**
 * @brief Draw a rectangle box on RGB565 frame
 * @param fb Frame buffer
 * @param x Top-left X coordinate
 * @param y Top-left Y coordinate
 * @param w Width
 * @param h Height
 * @param color RGB565 color
 * @param thickness Line thickness (default 3)
 */
void drawBox(camera_fb_t* fb, int x, int y, int w, int h, 
             uint16_t color, int thickness = 3);

/**
 * @brief Draw the crop region box on frame
 * @param fb Frame buffer
 * @param color RGB565 color (default green)
 */
void drawCropRegion(camera_fb_t* fb, uint16_t color = COLOR_GREEN);

}  // namespace app

#endif // APP_GRAPHICS_H
