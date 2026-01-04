// cam_config.h - Camera Configuration for Multiple Sensors
#ifndef CAM_CONFIG_H
#define CAM_CONFIG_H

#include "esp_camera.h"

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
    #define INITIAL_PIXEL_FORMAT PIXFORMAT_JPEG
    #define INITIAL_FRAME_SIZE FRAMESIZE_XGA        // 1024x768
    #define INITIAL_GRAB_MODE CAMERA_GRAB_LATEST
    #define INITIAL_JPEG_QUALITY 10
    #define INITIAL_FB_COUNT 2
    #define XCLK_FREQ_HZ 20000000                   // 20MHz
    #define MAX_FRAME_SIZE FRAMESIZE_UXGA           // 1600x1200 max
    #define SENSOR_DESCRIPTION "OV2640 - Hardware JPEG encoder, up to UXGA (1600x1200)"
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
    #define MAX_FRAME_SIZE FRAMESIZE_240X240        // 240x240 max (frame buffer limitation)
    #define SENSOR_DESCRIPTION "RHYX M21-45 - NO hardware JPEG, limited to 240x240 resolution"
#endif

// Validate sensor selection
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
    sensor_t * s = esp_camera_sensor_get();
    if (!s) {
        Serial.println("Failed to get sensor!");
        return ESP_FAIL;
    }

    Serial.printf("Detected Sensor PID: 0x%x\n", s->id.PID);
    Serial.printf("Configured for: %s\n", SENSOR_NAME);
    Serial.printf("Description: %s\n", SENSOR_DESCRIPTION);

    // Apply sensor-specific tuning
#ifdef SENSOR_OV2640
    // OV2640 optimal settings
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    s->set_lenc(s, 1);  // Enable lens correction
    Serial.println("✓ OV2640 sensor tuning applied");
#endif

#ifdef SENSOR_RHYX_M21_45
    // RHYX M21-45 minimal tuning (this sensor doesn't support many OV-series settings)
    // Keep it minimal for stability
    Serial.println("✓ RHYX M21-45 minimal configuration applied");
#endif

    // Hardware stability pins
    pinMode(2, INPUT_PULLUP);
    pinMode(4, INPUT_PULLUP);
    pinMode(12, INPUT_PULLUP);
    pinMode(13, INPUT_PULLUP);
    pinMode(14, INPUT_PULLUP);
    pinMode(15, INPUT_PULLUP);

    return ESP_OK;
}

// ===========================
// Get Supported Resolutions HTML
// ===========================
String getSupportedResolutionsHTML() {
#ifdef SENSOR_OV2640
    return R"(
                <option value="10">UXGA (1600x1200)</option>
                <option value="9">SXGA (1280x1024)</option>
                <option value="8" selected>XGA (1024x768) - Recommended</option>
                <option value="7">SVGA (800x600)</option>
                <option value="6">VGA (640x480)</option>
                <option value="5">CIF (400x296)</option>
                <option value="4">QVGA (320x240)</option>
                <option value="3">HQVGA (240x176)</option>
                <option value="2">QCIF (176x144)</option>
                <option value="1">QQVGA (160x120)</option>
    )";
#endif

#ifdef SENSOR_RHYX_M21_45
    return R"(
                <option value="10" disabled>UXGA (1600x1200) - Not supported</option>
                <option value="9" disabled>SXGA (1280x1024) - Not supported</option>
                <option value="8" disabled>XGA (1024x768) - Not supported</option>
                <option value="7" disabled>SVGA (800x600) - Not supported</option>
                <option value="6" disabled>VGA (640x480) - Not supported</option>
                <option value="5" disabled>CIF (400x296) - Not supported</option>
                <option value="4" disabled>QVGA (320x240) - Not supported</option>
                <option value="3" disabled>HQVGA (240x176) - Not supported</option>
                <option value="2" disabled>QCIF (176x144) - Not supported</option>
                <option value="1" disabled>QQVGA (160x120) - Not supported</option>
                <option value="17" selected>240x240 - ONLY supported size!</option>
    )";
#endif
}

// ===========================
// Get Sensor Tips HTML
// ===========================
String getSensorTipsHTML() {
#ifdef SENSOR_OV2640
    return R"(
                <li><strong>OV2640 sensor with hardware JPEG encoder</strong></li>
                <li>Supports resolutions up to UXGA (1600x1200)</li>
                <li>XGA (1024x768) recommended for best quality/speed balance</li>
    )";
#endif

#ifdef SENSOR_RHYX_M21_45
    return R"(
                <li><strong>⚠️ RHYX M21-45 is limited to 240x240 resolution only!</strong></li>
                <li>This sensor has NO hardware JPEG encoder</li>
                <li>Frame buffer size limits maximum resolution</li>
    )";
#endif
}

#endif // CAM_CONFIG_H
