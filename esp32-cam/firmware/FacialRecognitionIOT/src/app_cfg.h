/**
 * @file app_cfg.h
 * @brief Unified Configuration for FacialRecognitionIOT
 * 
 * Single source of truth for ALL configuration settings.
 * Edit this file to customize the system for your deployment.
 */

#ifndef APP_CFG_H
#define APP_CFG_H

/* =========================
 * Standard Definitions
 * ========================= */
#define STD_ON   1
#define STD_OFF  0

/* =========================
 * Feature Enables
 * ========================= */
#define WIFI_ENABLED        STD_ON
#define MQTT_ENABLED        STD_ON
#define LED_ENABLED         STD_ON

/* =========================
 * Debug Flags
 * ========================= */
#define SERIAL_DEBUG        STD_ON
#define WIFI_DEBUG          STD_ON
#define MQTT_DEBUG          STD_ON

/* =========================
 * Serial Configuration
 * ========================= */
#define SERIAL_BAUD_RATE    115200

/* =========================
 * WiFi Configuration
 * ========================= */
#define WIFI_SSID           "omar"
#define WIFI_PASSWORD       "12345678"
#define WIFI_RECONNECT_MS   5000
#define WIFI_CONNECT_TIMEOUT_MS 15000

/* =========================
 * MQTT Configuration
 * ========================= */
#define MQTT_BROKER                 "mqtt.saddevastator.qzz.io"  // Update with your broker IP
#define MQTT_PORT                   1883
#define MQTT_CLIENT_ID              "esp32cam_face_recognition"
#define MQTT_TOPIC_BASE             "/hotel/kiosk/Room1/FaceRecognition/Authentication"
#define MQTT_LOCATION               "main_lobby"  // Change per location
#define MQTT_RECONNECT_INTERVAL_MS  5000
#define PUBLISH_ONLY_RECOGNIZED     true  // Only publish recognized faces

// Optional MQTT authentication (uncomment to enable)
// #define MQTT_USERNAME            "your_username"
// #define MQTT_PASSWORD            "your_password"

/* =========================
 * Camera Hardware Configuration
 * (ESP32-CAM AI-Thinker)
 * ========================= */
#define CAMERA_MODEL_AI_THINKER

#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27

#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

/* =========================
 * Camera Sensor Configuration
 * ========================= */
// Sensor selection - uncomment ONLY ONE
#define SENSOR_OV2640
// #define SENSOR_RHYX_M21_45

#ifdef SENSOR_OV2640
    #define SENSOR_NAME             "OV2640"
    #define SENSOR_HAS_JPEG         true
    #define INITIAL_PIXEL_FORMAT    PIXFORMAT_RGB565
    #define INITIAL_FRAME_SIZE      FRAMESIZE_QVGA  // 320x240
    #define INITIAL_GRAB_MODE       CAMERA_GRAB_LATEST
    #define INITIAL_JPEG_QUALITY    10
    #define INITIAL_FB_COUNT        2
    #define XCLK_FREQ_HZ            20000000  // 20MHz
    
    // Frame dimensions
    #define FRAME_WIDTH             320
    #define FRAME_HEIGHT            240
    
    // Crop region for 96x96 model (centered 240x240 from 320x240)
    #define CROP_SIZE               240
    #define CROP_X_OFFSET           40   // (320 - 240) / 2
    #define CROP_Y_OFFSET           0    // (240 - 240) / 2
#endif

#ifdef SENSOR_RHYX_M21_45
    #define SENSOR_NAME             "RHYX M21-45"
    #define SENSOR_HAS_JPEG         false
    #define INITIAL_PIXEL_FORMAT    PIXFORMAT_RGB565
    #define INITIAL_FRAME_SIZE      FRAMESIZE_240X240
    #define INITIAL_GRAB_MODE       CAMERA_GRAB_WHEN_EMPTY
    #define INITIAL_JPEG_QUALITY    12
    #define INITIAL_FB_COUNT        2
    #define XCLK_FREQ_HZ            20000000
    
    // Frame dimensions
    #define FRAME_WIDTH             240
    #define FRAME_HEIGHT            240
    
    // No cropping needed - native 240x240
    #define CROP_SIZE               240
    #define CROP_X_OFFSET           0
    #define CROP_Y_OFFSET           0
#endif

// Validate sensor selection
#if !defined(SENSOR_OV2640) && !defined(SENSOR_RHYX_M21_45)
    #error "No sensor selected! Uncomment ONE sensor type above."
#endif

#if defined(SENSOR_OV2640) && defined(SENSOR_RHYX_M21_45)
    #error "Multiple sensors selected! Uncomment ONLY ONE sensor type."
#endif

/* =========================
 * Face Recognition Model Configuration
 * ========================= */
#define MODEL_INPUT_WIDTH       96
#define MODEL_INPUT_HEIGHT      96
#define MODEL_INPUT_CHANNELS    3
#define CONFIDENCE_THRESHOLD    0.995f
#define TENSOR_ARENA_SIZE       (1 * 1024 * 1024)  // 1 MB

/* =========================
 * LED Configuration
 * ========================= */
#define LED_GPIO_NUM            33   // Built-in flash LED on AI-Thinker
#define LED_FLASH_MS            50   // Flash duration on recognition

/* =========================
 * Timing Configuration
 * ========================= */
#define INFERENCE_DELAY_MS      100  // Delay between frames (~10 FPS)

/* =========================
 * Graphics Colors (RGB565)
 * ========================= */
#define COLOR_GREEN     0x07E0
#define COLOR_RED       0xF800
#define COLOR_BLUE      0x001F
#define COLOR_WHITE     0xFFFF
#define COLOR_YELLOW    0xFFE0

#endif /* APP_CFG_H */
