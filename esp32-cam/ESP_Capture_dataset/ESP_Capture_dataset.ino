// ESP32-CAM Dataset Capture - Modular Version
// Supports multiple camera sensors: OV2640, RHYX M21-45
// Configure your sensor in cam_config.h

#include <Arduino.h>
#include <WiFi.h>
#include <FS.h>
#include <SD_MMC.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "board_config.h"
#include "camera_pins.h"
#include "cam_config.h"    // Camera configuration and sensor selection
#include "web_server.h"    // HTTP server and web interface

// ===========================
// WiFi Configuration
// ===========================
const char* ssid = "omar";
const char* password = "12345678";

// ===========================
// Global Variables
// ===========================
String currentPerson = "";
int imageCounter = 0;
bool sdCardAvailable = false;
bool useJPEG = SENSOR_HAS_JPEG;  // Set from cam_config.h based on sensor
bool continuousCapture = false;  // For streaming capture mode
bool ledFlashEnabled = false;    // LED flash toggle - default OFF
uint32_t lastCaptureTime = 0;    // Timestamp tracking for adaptive timing
int consecutiveFailures = 0;     // Track failures to adapt capture timing

// ===========================
// SD Card Functions
// ===========================
bool createPersonDirectory(String personName) {
    String path = "/dataset/" + personName;
    if(!SD_MMC.exists(path)) {
        if(SD_MMC.mkdir(path)) {
            Serial.println("Created directory: " + path);
            return true;
        } else {
            Serial.println("Failed to create directory: " + path);
            return false;
        }
    }
    return true;
}

int getImageCount(String personName) {
    String path = "/dataset/" + personName;
    File dir = SD_MMC.open(path);
    if(!dir || !dir.isDirectory()) {
        return 0;
    }
    
    int count = 0;
    File file = dir.openNextFile();
    while(file) {
        if(!file.isDirectory()) {
            count++;
        }
        file = dir.openNextFile();
    }
    return count;
}

bool saveImage(camera_fb_t* fb, String personName, int imageNum) {
    String filenameBase = "/dataset/" + personName + "/img_" + String(imageNum);
    
    if (useJPEG && fb->format == PIXFORMAT_JPEG) {
        // Save as JPEG
        String filename = filenameBase + ".jpg";
        File file = SD_MMC.open(filename, FILE_WRITE);
        if(!file) {
            Serial.println("Failed to open file for writing: " + filename);
            return false;
        }
        file.write(fb->buf, fb->len);
        file.close();
        Serial.println("Saved: " + filename);
        return true;
    } else {
        // Save as PGM (grayscale/RGB565)
        String filename = filenameBase + ".pgm";
        File file = SD_MMC.open(filename, FILE_WRITE);
        if(!file) {
            Serial.println("Failed to open file for writing: " + filename);
            return false;
        }
        
        if (fb->width <= 0 || fb->height <= 0) {
            Serial.printf("Invalid fb dimensions: w=%d h=%d\n", fb->width, fb->height);
            file.close();
            return false;
        }
        
        String header = "P5\n" + String(fb->width) + " " + String(fb->height) + "\n255\n";
        file.print(header);
        file.write(fb->buf, fb->len);
        file.close();
        Serial.println("Saved (PGM): " + filename + "  bytes:" + String(fb->len));
        return true;
    }
}

void setupLedFlash() {
#if defined(LED_GPIO_NUM)
    pinMode(LED_GPIO_NUM, OUTPUT);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
}

// ===========================
// Setup
// ===========================
void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);  // Disable brownout detector
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    
    Serial.println("\n╔════════════════════════════════════════╗");
    Serial.println("║   ESP32-CAM Dataset Capture System    ║");
    Serial.println("╚════════════════════════════════════════╝");
    Serial.println();
    
    // 1. Initialize Camera
    Serial.println("▶ Initializing camera...");
    esp_err_t err = initCamera();  // From cam_config.h
    if (err != ESP_OK) {
        Serial.println("✗ Camera initialization failed!");
        Serial.printf("  Error code: 0x%x\n", err);
        return;
    }
    Serial.println("✓ Camera initialized successfully");
    Serial.println();
    
    // 2. Setup LED Flash
#if defined(LED_GPIO_NUM)
    setupLedFlash();
    Serial.println("✓ LED flash configured");
#endif
    
    // 3. Initialize SD Card
    Serial.println("▶ Initializing SD card...");
    if(!SD_MMC.begin("/sdcard", true)) {
        Serial.println("✗ SD Card mount failed");
        sdCardAvailable = false;
    } else {
        uint8_t cardType = SD_MMC.cardType();
        if(cardType == CARD_NONE) {
            Serial.println("✗ No SD card detected");
            sdCardAvailable = false;
        } else {
            sdCardAvailable = true;
            Serial.println("✓ SD Card initialized");
            Serial.printf("  Card Size: %llu MB\n", SD_MMC.cardSize() / (1024 * 1024));
            
            // Create base dataset directory
            if(!SD_MMC.exists("/dataset")) {
                SD_MMC.mkdir("/dataset");
                Serial.println("  Created /dataset directory");
            }
        }
    }
    Serial.println();
    
    // 4. Connect to WiFi
    Serial.println("▶ Connecting to WiFi...");
    Serial.printf("  SSID: %s\n", ssid);
    WiFi.begin(ssid, password);
    WiFi.setSleep(false);  // CRITICAL for performance!
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    Serial.println();
    
    if(WiFi.status() == WL_CONNECTED) {
        Serial.println("✓ WiFi connected successfully");
        Serial.print("  IP Address: ");
        Serial.println(WiFi.localIP());
        Serial.print("  Signal Strength: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
    } else {
        Serial.println("✗ WiFi connection failed!");
        return;
    }
    Serial.println();
    
    // 5. Start Web Server
    Serial.println("▶ Starting web servers...");
    startCameraServer();  // From web_server.h
    Serial.println();
    
    // 6. Display Access Information
    Serial.println("╔════════════════════════════════════════╗");
    Serial.println("║         SYSTEM READY!                  ║");
    Serial.println("╚════════════════════════════════════════╝");
    Serial.println();
    Serial.println("📱 Access the web interface:");
    Serial.print("   http://");
    Serial.println(WiFi.localIP());
    Serial.println();
    Serial.printf("📷 Sensor: %s\n", SENSOR_NAME);
    Serial.printf("📝 Description: %s\n", SENSOR_DESCRIPTION);
    Serial.println();
    Serial.println("Ready to capture dataset! 📸");
    Serial.println("═══════════════════════════════════════════");
    Serial.println();
}

// ===========================
// Loop
// ===========================
void loop() {
    delay(10);  // Continuous capture now handled via HTTP /capture calls
}
