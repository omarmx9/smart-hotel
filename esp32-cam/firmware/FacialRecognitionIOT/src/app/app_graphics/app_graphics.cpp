/**
 * @file app_graphics.cpp
 * @brief Graphics Implementation
 */

#include "app_graphics.h"
#include "../../app_cfg.h"

namespace app {

void drawBox(camera_fb_t* fb, int x, int y, int w, int h, 
             uint16_t color, int thickness) {
    if (!fb || fb->format != PIXFORMAT_RGB565) return;

    // Clamp coordinates
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x + w > (int)fb->width) w = fb->width - x;
    if (y + h > (int)fb->height) h = fb->height - y;

    uint16_t* buf = (uint16_t*)fb->buf;
    int maxIdx = fb->width * fb->height;

    // Draw horizontal lines (top & bottom)
    for (int t = 0; t < thickness; t++) {
        for (int i = x; i < x + w; i++) {
            int topIdx = (y + t) * fb->width + i;
            int botIdx = (y + h - 1 - t) * fb->width + i;
            if (topIdx < maxIdx) buf[topIdx] = color;
            if (botIdx < maxIdx) buf[botIdx] = color;
        }
    }

    // Draw vertical lines (left & right)
    for (int t = 0; t < thickness; t++) {
        for (int j = y; j < y + h; j++) {
            int leftIdx = j * fb->width + (x + t);
            int rightIdx = j * fb->width + (x + w - 1 - t);
            if (leftIdx < maxIdx) buf[leftIdx] = color;
            if (rightIdx < maxIdx) buf[rightIdx] = color;
        }
    }
}

void drawCropRegion(camera_fb_t* fb, uint16_t color) {
    drawBox(fb, CROP_X_OFFSET, CROP_Y_OFFSET, CROP_SIZE, CROP_SIZE, color);
}

}  // namespace app
