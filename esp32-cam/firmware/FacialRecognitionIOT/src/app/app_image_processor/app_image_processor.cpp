/**
 * @file app_image_processor.cpp
 * @brief Image Processing Implementation
 */

#include "app_image_processor.h"
#include "../../app_cfg.h"

namespace app {

void rgb565ToRgb888(uint16_t pixel, uint8_t* r, uint8_t* g, uint8_t* b) {
    *r = ((pixel >> 11) & 0x1F) << 3;
    *g = ((pixel >> 5) & 0x3F) << 2;
    *b = (pixel & 0x1F) << 3;
}

void processImage(camera_fb_t* fb, TfLiteTensor* input) {
    if (!fb || !input) return;

    // Crop settings from app_cfg.h
    int minSide = CROP_SIZE;
    int cropXStart = CROP_X_OFFSET;
    int cropYStart = CROP_Y_OFFSET;

    uint16_t* rgb565 = (uint16_t*)fb->buf;

    if (input->type == kTfLiteUInt8) {
        // Quantized model - uint8 input [0-255]
        uint8_t* inputData = input->data.uint8;

        for (int y = 0; y < MODEL_INPUT_HEIGHT; y++) {
            for (int x = 0; x < MODEL_INPUT_WIDTH; x++) {
                // Map output coords to cropped input coords
                int srcX = cropXStart + (x * minSide) / MODEL_INPUT_WIDTH;
                int srcY = cropYStart + (y * minSide) / MODEL_INPUT_HEIGHT;

                // Clamp to valid range
                if (srcX >= (int)fb->width) srcX = fb->width - 1;
                if (srcY >= (int)fb->height) srcY = fb->height - 1;

                int srcIdx = srcY * fb->width + srcX;
                uint16_t pixel = rgb565[srcIdx];

                // Extract RGB
                uint8_t r, g, b;
                rgb565ToRgb888(pixel, &r, &g, &b);

                // Store as uint8 (0-255)
                int outIdx = (y * MODEL_INPUT_WIDTH + x) * 3;
                inputData[outIdx + 0] = r;
                inputData[outIdx + 1] = g;
                inputData[outIdx + 2] = b;
            }
        }
    } else if (input->type == kTfLiteFloat32) {
        // Float model - normalize to [-1, 1]
        float* inputData = input->data.f;

        for (int y = 0; y < MODEL_INPUT_HEIGHT; y++) {
            for (int x = 0; x < MODEL_INPUT_WIDTH; x++) {
                int srcX = cropXStart + (x * minSide) / MODEL_INPUT_WIDTH;
                int srcY = cropYStart + (y * minSide) / MODEL_INPUT_HEIGHT;

                if (srcX >= (int)fb->width) srcX = fb->width - 1;
                if (srcY >= (int)fb->height) srcY = fb->height - 1;

                int srcIdx = srcY * fb->width + srcX;
                uint16_t pixel = rgb565[srcIdx];

                uint8_t r, g, b;
                rgb565ToRgb888(pixel, &r, &g, &b);

                // Normalize to [-1, 1] for MobileNetV2
                int outIdx = (y * MODEL_INPUT_WIDTH + x) * 3;
                inputData[outIdx + 0] = (r / 127.5f) - 1.0f;
                inputData[outIdx + 1] = (g / 127.5f) - 1.0f;
                inputData[outIdx + 2] = (b / 127.5f) - 1.0f;
            }
        }
    }
}

}  // namespace app
