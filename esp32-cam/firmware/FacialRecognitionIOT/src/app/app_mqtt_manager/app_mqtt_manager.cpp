/**
 * @file app_mqtt_manager.cpp
 * @brief Application Layer - MQTT Manager Implementation
 */

#include "app_mqtt_manager.h"
#include "../../app_cfg.h"
#include "../../hal/hal_mqtt/hal_mqtt.h"
#include <Arduino.h>
#include <time.h>

namespace app {

static char s_currentTopic[256] = {0};
static int s_totalFrames = 0;
static int s_totalRecognized = 0;
static bool s_timeIsSynced = false;

/**
 * @brief Initialize NTP time synchronization
 */
static bool syncTime() {
    if (s_timeIsSynced) return true;
    
    Serial.println("[Time] Configuring NTP...");
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    
    Serial.print("[Time] Syncing");
    for (int i = 0; i < 20; i++) {
        time_t now = time(nullptr);
        if (now > 1577836800) {  // After 2020-01-01
            s_timeIsSynced = true;
            struct tm* timeinfo = gmtime(&now);
            char timeBuf[32];
            strftime(timeBuf, sizeof(timeBuf), "%Y-%m-%d %H:%M:%S UTC", timeinfo);
            Serial.printf("\n[Time] Synced: %s\n", timeBuf);
            return true;
        }
        Serial.print(".");
        delay(500);
    }
    
    Serial.println("\n[Time] Sync failed - timestamps may be incorrect!");
    return false;
}

bool mqttManagerInit() {
    // Sync time before MQTT initialization
    syncTime();
    
    // Format the topic
    snprintf(s_currentTopic, sizeof(s_currentTopic), 
             "%s/%s", MQTT_TOPIC_BASE, MQTT_LOCATION);
    
    Serial.printf("[App MQTT] Topic: %s\n", s_currentTopic);
    
    return hal::mqttInit();
}

/**
 * @brief Format current timestamp in ISO 8601 format (UTC)
 * @return Timestamp string buffer (static, reused each call)
 */
static const char* getTimestampISO8601() {
    static char timestampBuf[32];
    
    // Try to sync if not already synced
    if (!s_timeIsSynced) {
        syncTime();
    }
    
    time_t now = time(nullptr);
    
    // Check if time is valid
    if (now < 1577836800) {
        strcpy(timestampBuf, "TIME_NOT_SYNCED");
        return timestampBuf;
    }
    
    struct tm* timeinfo = gmtime(&now);
    strftime(timestampBuf, sizeof(timestampBuf), 
             "%Y-%m-%dT%H:%M:%SZ", timeinfo);
    
    return timestampBuf;
}

/**
 * @brief Create JSON payload for face detection
 * @return JSON string (static, reused each call)
 */
static const char* formatFaceDetectionPayload(const FaceResult& result) {
    static char payloadBuf[512];
    
    snprintf(payloadBuf, sizeof(payloadBuf),
             "{"
             "\"person_name\":\"%s\","
             "\"confidence_score\":%.3f,"
             "\"timestamp\":\"%s\","
             "\"recognized\":%s,"
             "\"location\":\"%s\""
             "}",
             result.label,
             result.confidence,
             getTimestampISO8601(),
             result.recognized ? "true" : "false",
             MQTT_LOCATION);
    
    return payloadBuf;
}

bool publishFaceDetection(const FaceResult& result) {
#ifdef PUBLISH_ONLY_RECOGNIZED
    if (!result.recognized) {
        return true;
    }
#endif
    
    const char* payload = formatFaceDetectionPayload(result);
    
    Serial.printf("[App MQTT] Publishing: %s\n", payload);
    
    return hal::mqttPublish(s_currentTopic, payload);
}

bool publishStatistics(int framesProcessed, int faceRecognized) {
    static char payload[256];
    
    snprintf(payload, sizeof(payload),
             "{"
             "\"frames_processed\":%d,"
             "\"faces_recognized\":%d,"
             "\"timestamp\":\"%s\","
             "\"location\":\"%s\""
             "}",
             framesProcessed,
             faceRecognized,
             getTimestampISO8601(),
             MQTT_LOCATION);
    
    static char statsTopic[256];
    snprintf(statsTopic, sizeof(statsTopic), 
             "%s/%s/stats", MQTT_TOPIC_BASE, MQTT_LOCATION);
    
    return hal::mqttPublish(statsTopic, payload);
}

const char* getCurrentTopic() {
    return s_currentTopic;
}

bool isMqttReady() {
    return hal::mqttIsConnected();
}

void mqttManagerProcess() {
    hal::mqttProcess();
}

}  // namespace app
