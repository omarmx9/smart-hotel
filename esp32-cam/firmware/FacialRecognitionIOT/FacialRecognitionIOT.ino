/**
 * @file FacialRecognitionIOT.ino
 * @brief Arduino Sketch Entry Point
 * 
 * Main Arduino sketch for ESP32-CAM Face Recognition with MQTT
 * All supporting code is in src/ subfolders
 */

#include "src/FacialRecognition_mgr/FacialRecognition_mgr.h"

void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    delay(1000);
    
    // Initialize face recognition system
    if (!FacialRecognition_mgr::init()) {
        Serial.println("FATAL: System initialization failed!");
        // System remains in error state
    }
}

void loop() {
    // Main face recognition loop with MQTT publishing
    FacialRecognition_mgr::run();
}
