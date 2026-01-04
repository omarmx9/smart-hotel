/**
 * @file FacialRecognition_mgr.cpp
 * @brief Main Orchestrator Implementation
 * 
 * Coordinates all subsystems for face recognition on ESP32-CAM
 * Integrates MQTT publishing for detected faces
 */

#include "FacialRecognition_mgr.h"
#include "../app_cfg.h"

// HAL Layer
#include "../hal/hal_camera/hal_camera.h"
#include "../hal/hal_led/hal_led.h"
#include "../hal/hal_memory/hal_memory.h"
#include "../hal/hal_mqtt/hal_mqtt.h"

// Drivers
#include "../drivers/driver_tflite/driver_tflite.h"

// Application
#include "../app/app_image_processor/app_image_processor.h"
#include "../app/app_graphics/app_graphics.h"
#include "../app/app_face_recognizer/app_face_recognizer.h"
#include "../app/app_mqtt_manager/app_mqtt_manager.h"

// Model Data
#include "../model/model_data.h"

#include <Arduino.h>
#include <WiFi.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

namespace FacialRecognition_mgr {

// Internal state
static State s_state = State::UNINITIALIZED;
static app::FaceResult s_lastResult = {"Waiting...", -1, 0.0f, false, 0};
static int s_framesProcessed = 0;
static int s_facesRecognized = 0;
static bool s_wifiConnected = false;

/**
 * @brief Initialize WiFi connection
 */
static bool initWifi() {
#if WIFI_ENABLED == STD_ON
    Serial.printf("[WiFi] Connecting to %s...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - startTime > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("\n[WiFi] Connection timeout!");
            return false;
        }
    }
    
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    s_wifiConnected = true;
    return true;
#else
    return false;
#endif
}

bool init() {
    s_state = State::INITIALIZING;
    
    // Disable brownout detector
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    
    Serial.println("\n=== FacialRecognition_mgr Initializing ===");
    Serial.printf("Sensor: %s\n", SENSOR_NAME);

    // 1. Initialize HAL - Memory
    hal::memoryPrintStatus();
    if (!hal::memoryHasPsram()) {
        Serial.println("[ERROR] PSRAM required but not found!");
        s_state = State::ERROR;
        return false;
    }

    // 2. Initialize HAL - LED
    hal::ledInit();
    Serial.println("[OK] LED initialized");

    // 3. Initialize HAL - Camera
    esp_err_t camErr = hal::cameraInit();
    if (camErr != ESP_OK) {
        Serial.println("[ERROR] Camera initialization failed!");
        s_state = State::ERROR;
        return false;
    }
    Serial.println("[OK] Camera initialized");

    // 4. Test camera capture
    camera_fb_t* testFb = hal::cameraCapture();
    if (!testFb) {
        Serial.println("[ERROR] Camera test capture failed!");
        s_state = State::ERROR;
        return false;
    }
    Serial.printf("[OK] Camera test: %dx%d (%d bytes)\n", 
                  testFb->width, testFb->height, testFb->len);
    if (testFb->format != PIXFORMAT_RGB565) {
        Serial.println("[WARN] Expected RGB565 format for inference!");
    }
    hal::cameraRelease(testFb);

    // 5. Initialize Driver - TFLite
    if (!driver::tfliteInit(face_recognition_model, TENSOR_ARENA_SIZE)) {
        Serial.println("[ERROR] TFLite initialization failed!");
        s_state = State::ERROR;
        return false;
    }
    Serial.println("[OK] TFLite model loaded");

    // 6. Initialize WiFi (required for MQTT)
#if WIFI_ENABLED == STD_ON
    if (!initWifi()) {
        Serial.println("[WARN] WiFi failed, continuing without network features");
    }
#endif

    // 7. Initialize MQTT (optional, don't fail if MQTT unavailable)
#if MQTT_ENABLED == STD_ON
    if (s_wifiConnected) {
        if (app::mqttManagerInit()) {
            Serial.println("[OK] MQTT initialized");
        } else {
            Serial.println("[WARN] MQTT initialization failed, continuing without MQTT");
        }
    }
#endif

    // Success
    s_state = State::READY;
    Serial.println("\n=== System Ready for Face Recognition ===\n");
    return true;
}

app::FaceResult processFrame() {
    app::FaceResult result = {"Error", -1, 0.0f, false, 0};
    
    if (s_state != State::READY && s_state != State::RUNNING) {
        return result;
    }

    s_state = State::RUNNING;
    s_framesProcessed++;

    // 1. Capture frame
    camera_fb_t* fb = hal::cameraCapture();
    if (!fb) {
        Serial.println("[ERROR] Camera capture failed");
        result.label = "Capture Error";
        return result;
    }

    // 2. Draw crop region (visual feedback)
    app::drawCropRegion(fb, COLOR_GREEN);

    // 3. Preprocess image
    TfLiteTensor* input = driver::tfliteGetInput();
    app::processImage(fb, input);

    // 4. Release frame buffer
    hal::cameraRelease(fb);

    // 5. Run inference
    unsigned long startTime = millis();
    bool invokeOk = driver::tfliteInvoke();
    unsigned long inferenceTime = millis() - startTime;

    if (!invokeOk) {
        Serial.println("[ERROR] Inference failed");
        result.label = "Inference Error";
        return result;
    }

    // 6. Process output
    result = app::processOutput();
    result.inferenceTimeMs = inferenceTime;

    // 7. Visual feedback on recognition
    if (result.recognized) {
        hal::ledFlash(LED_FLASH_MS);
        s_facesRecognized++;
        
        // 8. Publish to MQTT if recognized
#if MQTT_ENABLED == STD_ON
        if (s_wifiConnected && app::isMqttReady()) {
            app::publishFaceDetection(result);
        }
#endif
    }

    s_lastResult = result;
    s_state = State::READY;
    return result;
}

void run() {
    if (s_state == State::ERROR) {
        Serial.println("[ERROR] System in error state - call reset()");
        delay(5000);
        return;
    }

    if (s_state == State::UNINITIALIZED) {
        Serial.println("[ERROR] System not initialized - call init()");
        delay(5000);
        return;
    }

    // Process MQTT events
#if MQTT_ENABLED == STD_ON
    if (s_wifiConnected) {
        app::mqttManagerProcess();
    }
#endif

    // Process frame and get result
    app::FaceResult result = processFrame();

    // Print result
    Serial.printf("[%lu ms] %s (%.1f%%)\n",
                  result.inferenceTimeMs,
                  result.label,
                  result.confidence * 100);

    // Delay for target FPS
    delay(INFERENCE_DELAY_MS);
}

State getState() {
    return s_state;
}

app::FaceResult getLastResult() {
    return s_lastResult;
}

bool reset() {
    Serial.println("\n=== Resetting System ===\n");
    driver::tfliteCleanup();
    s_state = State::UNINITIALIZED;
    s_framesProcessed = 0;
    s_facesRecognized = 0;
    return init();
}

bool isReady() {
    return s_state == State::READY || s_state == State::RUNNING;
}

void setConfidenceThreshold(float threshold) {
    app::setConfidenceThreshold(threshold);
}

int getFramesProcessed() {
    return s_framesProcessed;
}

int getFacesRecognized() {
    return s_facesRecognized;
}

}  // namespace FacialRecognition_mgr
