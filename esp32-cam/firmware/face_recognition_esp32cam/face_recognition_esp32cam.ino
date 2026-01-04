/**
 * ESP32-CAM Face Recognition Firmware
 * Uses TensorFlow Lite Micro for on-device inference
 * Publishes recognition events via MQTT to Smart Hotel cloud
 * 
 * Hardware: ESP32-CAM (AI-Thinker)
 * Model: MobileNetV2 (96x96 input, 5 classes, quantized uint8)
 * 
 * Arduino IDE Setup:
 *   1. Board: "AI Thinker ESP32-CAM"
 *   2. Partition Scheme: "Huge APP (3MB No OTA/1MB SPIFFS)"
 *   3. PSRAM: "Enabled"
 *   4. Install libraries: PubSubClient, ArduinoJson
 */

#include <Arduino.h>
#include "esp_camera.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// TensorFlow Lite Micro
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

// Camera configuration (sensor selection + initialization)
#include "cam_config.h"

// Model data (stored in PROGMEM)
#include "model_data.h"

// MQTT Client for publishing recognition events
#include "mqtt_client.h"

// ==================== CONFIGURATION ====================

// Model configuration
#define MODEL_INPUT_WIDTH   96
#define MODEL_INPUT_HEIGHT  96
#define MODEL_INPUT_CHANNELS 3
#define NUM_CLASSES         5

// Confidence threshold for recognition
#define CONFIDENCE_THRESHOLD 0.995f

// Enable/disable MQTT publishing
#define MQTT_ENABLED        1

// ==================== CLASS LABELS ====================

static const char* kLabels[] = {
    "maha",
    "mokhtar",
    "omar",
    "radwan",
    "tarek"
};

// ==================== TFLite GLOBALS ====================

const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;

uint8_t* tensor_arena = nullptr;
// constexpr int kTensorArenaSize = 512 * 1024;  // 512 KB
constexpr int kTensorArenaSize = 1 * 1024 * 1024;  // 1 MB
// ==================== STATE ====================

String current_prediction = "Waiting...";
float current_confidence = 0.0;
bool model_ready = false;  // Track if model initialized successfully

// ==================== MQTT CLIENT ====================

#if MQTT_ENABLED
MQTTClient mqttClient;

// Control command callback
void onControlCommand(const char* command) {
    Serial.printf("[Control] Command received: %s\n", command);
    
    if (strcmp(command, "capture") == 0) {
        // Force immediate recognition publish on next frame
        Serial.println("[Control] Forcing capture...");
    }
}
#endif

// ==================== HELPER: DRAW BOX ON FRAME ====================

void draw_box(camera_fb_t* fb, int x, int y, int w, int h, uint16_t color) {
    if (!fb || fb->format != PIXFORMAT_RGB565) return;
    int t = 3;  // Line thickness

    // Clamp coordinates
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x + w > fb->width) w = fb->width - x;
    if (y + h > fb->height) h = fb->height - y;

    uint16_t* buf = (uint16_t*)fb->buf;

    // Draw Horizontal Lines (Top & Bottom)
    for (int i = 0; i < t; i++) {
        for (int j = x; j < x + w; j++) {
            int top_idx = (y + i) * fb->width + j;
            int bot_idx = (y + h - 1 - i) * fb->width + j;
            if (top_idx < fb->width * fb->height) buf[top_idx] = color;
            if (bot_idx < fb->width * fb->height) buf[bot_idx] = color;
        }
    }
    // Draw Vertical Lines (Left & Right)
    for (int i = 0; i < t; i++) {
        for (int j = y; j < y + h; j++) {
            int left_idx = j * fb->width + (x + i);
            int right_idx = j * fb->width + (x + w - 1 - i);
            if (left_idx < fb->width * fb->height) buf[left_idx] = color;
            if (right_idx < fb->width * fb->height) buf[right_idx] = color;
        }
    }
}

// ==================== IMAGE PREPROCESSING ====================

void process_image(camera_fb_t* fb) {
    if (!fb || !input) return;

    // Smart Crop Logic:
    // Use sensor-specific crop settings from cam_config.h
    int min_side = CROP_SIZE;
    int crop_x_start = CROP_X_OFFSET;
    int crop_y_start = CROP_Y_OFFSET;

    uint16_t* rgb565 = (uint16_t*)fb->buf;

    if (input->type == kTfLiteUInt8) {
        // Quantized model - use uint8 input
        uint8_t* input_data = input->data.uint8;

        for (int y = 0; y < MODEL_INPUT_HEIGHT; y++) {
            for (int x = 0; x < MODEL_INPUT_WIDTH; x++) {
                // Map output coords to cropped input coords
                int src_x = crop_x_start + (x * min_side) / MODEL_INPUT_WIDTH;
                int src_y = crop_y_start + (y * min_side) / MODEL_INPUT_HEIGHT;

                // Clamp to valid range
                if (src_x >= fb->width) src_x = fb->width - 1;
                if (src_y >= fb->height) src_y = fb->height - 1;

                int src_idx = src_y * fb->width + src_x;
                uint16_t pixel = rgb565[src_idx];

                // Extract RGB from RGB565
                uint8_t r = ((pixel >> 11) & 0x1F) << 3;
                uint8_t g = ((pixel >> 5) & 0x3F) << 2;
                uint8_t b = (pixel & 0x1F) << 3;

                // Store as uint8 (0-255)
                int out_idx = (y * MODEL_INPUT_WIDTH + x) * 3;
                input_data[out_idx + 0] = r;
                input_data[out_idx + 1] = g;
                input_data[out_idx + 2] = b;
            }
        }
    } else if (input->type == kTfLiteFloat32) {
        // Float model
        float* input_data = input->data.f;

        for (int y = 0; y < MODEL_INPUT_HEIGHT; y++) {
            for (int x = 0; x < MODEL_INPUT_WIDTH; x++) {
                int src_x = crop_x_start + (x * min_side) / MODEL_INPUT_WIDTH;
                int src_y = crop_y_start + (y * min_side) / MODEL_INPUT_HEIGHT;

                if (src_x >= fb->width) src_x = fb->width - 1;
                if (src_y >= fb->height) src_y = fb->height - 1;

                int src_idx = src_y * fb->width + src_x;
                uint16_t pixel = rgb565[src_idx];

                uint8_t r = ((pixel >> 11) & 0x1F) << 3;
                uint8_t g = ((pixel >> 5) & 0x3F) << 2;
                uint8_t b = (pixel & 0x1F) << 3;

                // Normalize to [-1, 1] for MobileNetV2
                int out_idx = (y * MODEL_INPUT_WIDTH + x) * 3;
                input_data[out_idx + 0] = (r / 127.5f) - 1.0f;
                input_data[out_idx + 1] = (g / 127.5f) - 1.0f;
                input_data[out_idx + 2] = (b / 127.5f) - 1.0f;
            }
        }
    }
}

// ==================== SETUP ====================

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);  // Disable brownout detector
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println("\n--- ESP32-CAM Face Recognition ---");
    Serial.printf("Sensor: %s\n", SENSOR_NAME);

    // 1. Camera Init (using cam_config.h)
    esp_err_t cam_err = initCamera();
    if (cam_err != ESP_OK) {
        Serial.println("Camera init failed!");
        return;
    }
    Serial.println("Camera initialized");

    // 1b. Camera Test - verify we can capture frames
    Serial.println("Testing camera capture...");
    camera_fb_t* test_fb = esp_camera_fb_get();
    if (!test_fb) {
        Serial.println("✗ Camera test FAILED - cannot capture frames!");
        return;
    }
    Serial.printf("✓ Camera test OK - captured %dx%d frame (%d bytes)\n", 
                  test_fb->width, test_fb->height, test_fb->len);
    if (test_fb->format != PIXFORMAT_RGB565) {
        Serial.println("✗ WARNING: Expected RGB565 format for inference!");
    }
    esp_camera_fb_return(test_fb);

    // 2. LED Setup
#if defined(LED_GPIO_NUM)
    pinMode(LED_GPIO_NUM, OUTPUT);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif

    // 3. PSRAM Check
    if (psramFound()) {
        Serial.printf("PSRAM found: %d bytes\n", ESP.getPsramSize());
    } else {
        Serial.println("WARNING: No PSRAM found!");
    }

    // 4. TFLite Setup - allocate tensor arena in PSRAM
    tensor_arena = (uint8_t*)heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_SPIRAM);
    if (!tensor_arena) {
        Serial.println("Failed to allocate tensor arena!");
        return;
    }

    // Load model from PROGMEM
    model = tflite::GetModel(face_recognition_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        Serial.printf("Model version mismatch: %d vs %d\n",
                      model->version(), TFLITE_SCHEMA_VERSION);
        return;
    }

    // Op resolver with MobileNetV2 operations
    static tflite::MicroMutableOpResolver<15> resolver;
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddFullyConnected();
    resolver.AddSoftmax();
    resolver.AddReshape();
    resolver.AddAveragePool2D();
    resolver.AddAdd();
    resolver.AddMean();
    resolver.AddQuantize();
    resolver.AddDequantize();
    resolver.AddPad();
    resolver.AddRelu6();

    // Create interpreter
    static tflite::MicroInterpreter static_interpreter(
        model, resolver, tensor_arena, kTensorArenaSize);
    interpreter = &static_interpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("AllocateTensors failed!");
        return;
    }

    input = interpreter->input(0);
    output = interpreter->output(0);

    Serial.printf("Model loaded successfully!\n");
    Serial.printf("Input: [%d, %d, %d, %d] type=%d\n",
                  input->dims->data[0], input->dims->data[1],
                  input->dims->data[2], input->dims->data[3],
                  input->type);
    Serial.printf("Output classes: %d\n", output->dims->data[1]);
    Serial.printf("Arena used: %d bytes\n", interpreter->arena_used_bytes());

    model_ready = true;  // Mark initialization as successful
    Serial.println("\n--- Ready for face recognition ---\n");

#if MQTT_ENABLED
    // Initialize MQTT client
    Serial.println("Initializing MQTT...");
    if (mqttClient.begin()) {
        mqttClient.setControlCallback(onControlCommand);
        mqttClient.publishStatus(true);
        Serial.println("MQTT initialized successfully");
    } else {
        Serial.println("MQTT initialization failed - continuing without MQTT");
    }
#endif
}

// ==================== MAIN LOOP ====================

void loop() {
#if MQTT_ENABLED
    // Maintain MQTT connection
    mqttClient.loop();
#endif

    // Check if model initialized successfully
    if (!model_ready) {
        Serial.println("Model not ready - check initialization errors above");
        delay(5000);  // Wait 5 seconds before next message
        return;
    }

    // 1. Grab frame
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("Camera capture failed");
        delay(1000);
        return;
    }

    // 2. Draw visual feedback box (crop region from cam_config.h)
    draw_box(fb, CROP_X_OFFSET, CROP_Y_OFFSET, CROP_SIZE, CROP_SIZE, 0x07E0);  // Green box

    // 3. Process image (crop and resize to 96x96)
    process_image(fb);

    // 4. Return frame buffer
    esp_camera_fb_return(fb);

    // 5. Run inference
    unsigned long start_time = millis();
    if (interpreter->Invoke() == kTfLiteOk) {
        unsigned long inference_time = millis() - start_time;

        // Find best prediction
        float max_score = 0;
        int max_idx = 0;

        if (output->type == kTfLiteUInt8) {
            // Quantized output - dequantize
            for (int i = 0; i < NUM_CLASSES; i++) {
                float score = (output->data.uint8[i] - output->params.zero_point)
                              * output->params.scale;
                if (score > max_score) {
                    max_score = score;
                    max_idx = i;
                }
            }
        } else if (output->type == kTfLiteFloat32) {
            // Float output
            for (int i = 0; i < NUM_CLASSES; i++) {
                float score = output->data.f[i];
                if (score > max_score) {
                    max_score = score;
                    max_idx = i;
                }
            }
        }

        current_confidence = max_score;

        if (max_score >= CONFIDENCE_THRESHOLD) {
            current_prediction = kLabels[max_idx];

#if MQTT_ENABLED
            // Publish recognition event to MQTT
            mqttClient.publishRecognition(kLabels[max_idx], max_score);
#endif

            // Visual feedback - flash LED on recognition
#if defined(LED_GPIO_NUM)
            digitalWrite(LED_GPIO_NUM, HIGH);
            delay(50);
            digitalWrite(LED_GPIO_NUM, LOW);
#endif
        } else {
            current_prediction = "Unknown";

#if MQTT_ENABLED
            // Optionally publish unknown face events
            if (max_score > 0.5f) {  // Only if some face detected
                mqttClient.publishUnknown(max_score);
            }
#endif
        }

        // Print result
        Serial.printf("[%lu ms] %s (%.1f%%)\n",
                      inference_time,
                      current_prediction.c_str(),
                      current_confidence * 100);
    } else {
        Serial.println("Inference failed!");
    }

    delay(100);  // ~10 FPS
}
