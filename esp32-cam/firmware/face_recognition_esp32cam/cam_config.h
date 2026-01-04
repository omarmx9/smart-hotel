// cam_config.h - Camera Sensor Configuration for Face Recognition
// Supports multiple camera sensors with different capabilities
#ifndef CAM_CONFIG_H
#define CAM_CONFIG_H

#include "esp_camera.h"
#include "board_config.h"  // For camera pins

// ===========================
// SENSOR SELECTION - Choose your sensor here!
// ===========================
// Uncomment ONLY ONE sensor type:

#define SENSOR_OV2640        // OV2640 - Has hardware JPEG encoder
// #define SENSOR_RHYX_M21_45   // RHYX M21-45 (GC2415) - NO hardware JPEG, limited resolution

// ===========================
// Sensor Configuration Profiles
// ===========================

#ifdef SENSOR_OV2640
    #define SENSOR_NAME "OV2640"
    #define SENSOR_HAS_JPEG true
    #define INITIAL_PIXEL_FORMAT PIXFORMAT_RGB565   // RGB565 for inference
    #define INITIAL_FRAME_SIZE FRAMESIZE_QVGA       // 320x240 for face recognition
    #define INITIAL_GRAB_MODE CAMERA_GRAB_LATEST
    #define INITIAL_JPEG_QUALITY 10
    #define INITIAL_FB_COUNT 2
    #define XCLK_FREQ_HZ 20000000                   // 20MHz
    #define SENSOR_DESCRIPTION "OV2640 - Hardware JPEG encoder, QVGA (320x240) for inference"
    
    // Crop region for 96x96 model input (centered square from 320x240)
    #define CROP_SIZE 240                           // Crop 240x240 from center
    #define CROP_X_OFFSET 40                        // (320 - 240) / 2
    #define CROP_Y_OFFSET 0                         // (240 - 240) / 2
#endif

#ifdef SENSOR_RHYX_M21_45
    #define SENSOR_NAME "RHYX M21-45 (GC2415)"
    #define SENSOR_HAS_JPEG false
    #define INITIAL_PIXEL_FORMAT PIXFORMAT_RGB565
    #define INITIAL_FRAME_SIZE FRAMESIZE_240X240    // 240x240 ONLY!
    #define INITIAL_GRAB_MODE CAMERA_GRAB_WHEN_EMPTY
    #define INITIAL_JPEG_QUALITY 12
    #define INITIAL_FB_COUNT 2
    #define XCLK_FREQ_HZ 20000000                   // 20MHz
    #define SENSOR_DESCRIPTION "RHYX M21-45 - NO hardware JPEG, native 240x240 resolution"
    
    // No cropping needed - native 240x240 output
    #define CROP_SIZE 240
    #define CROP_X_OFFSET 0
    #define CROP_Y_OFFSET 0
#endif

// ===========================
// Validate Sensor Selection
// ===========================
#if !defined(SENSOR_OV2640) && !defined(SENSOR_RHYX_M21_45)
    #error "No sensor selected! Please uncomment ONE sensor type in cam_config.h"
#endif

#if defined(SENSOR_OV2640) && defined(SENSOR_RHYX_M21_45)
    #error "Multiple sensors selected! Please uncomment ONLY ONE sensor type in cam_config.h"
#endif

// ===========================
// Camera Initialization Function
// ===========================
esp_err_t initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    
    // Apply sensor-specific configuration
    config.xclk_freq_hz = XCLK_FREQ_HZ;
    config.pixel_format = INITIAL_PIXEL_FORMAT;
    config.frame_size = INITIAL_FRAME_SIZE;
    config.grab_mode = INITIAL_GRAB_MODE;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = INITIAL_JPEG_QUALITY;
    config.fb_count = INITIAL_FB_COUNT;

    // Initialize camera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed with error 0x%x\n", err);
        return err;
    }

    // Get sensor for configuration
    sensor_t* s = esp_camera_sensor_get();
    if (!s) {
        Serial.println("Failed to get sensor!");
        return ESP_FAIL;
    }

    Serial.printf("Detected Sensor PID: 0x%x\n", s->id.PID);
    Serial.printf("Configured for: %s\n", SENSOR_NAME);
    Serial.printf("Description: %s\n", SENSOR_DESCRIPTION);

    // Apply sensor-specific tuning
#ifdef SENSOR_OV2640
    // OV2640 optimal settings for face recognition
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 1);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);
    s->set_lenc(s, 1);  // Enable lens correction
    Serial.println("✓ OV2640 sensor tuning applied (optimized for face recognition)");
#endif

#ifdef SENSOR_RHYX_M21_45
    // RHYX M21-45 minimal tuning (this sensor doesn't support many OV-series settings)
    // The 240x240 native resolution is actually ideal for face recognition models!
    Serial.println("✓ RHYX M21-45 configuration applied (native 240x240 - ideal for ML!)");
#endif

    return ESP_OK;
}

// ===========================
// Get Frame Dimensions
// ===========================
inline int getFrameWidth() {
#ifdef SENSOR_OV2640
    return 320;  // QVGA width
#else
    return 240;  // 240x240
#endif
}

inline int getFrameHeight() {
#ifdef SENSOR_OV2640
    return 240;  // QVGA height
#else
    return 240;  // 240x240
#endif
}

#endif // CAM_CONFIG_H
