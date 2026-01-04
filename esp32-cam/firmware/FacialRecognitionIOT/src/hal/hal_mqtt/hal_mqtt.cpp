/**
 * @file hal_mqtt.cpp
 * @brief Hardware Abstraction Layer - MQTT Implementation
 */

#include "hal_mqtt.h"
#include "../../app_cfg.h"
#include <PubSubClient.h>
#include <WiFi.h>

namespace hal {

// MQTT client instance
static WiFiClient espClient;
static PubSubClient mqttClient(espClient);
static bool s_mqttReady = false;

// MQTT callback for incoming messages (if needed)
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    Serial.printf("[MQTT] Received on %s: ", topic);
    for (int i = 0; i < length; i++) {
        Serial.print((char)payload[i]);
    }
    Serial.println();
}

bool mqttInit() {
    // Configure MQTT client
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
    
    // Attempt connection
    if (mqttReconnect()) {
        s_mqttReady = true;
        Serial.printf("[MQTT] Connected to %s:%d\n", MQTT_BROKER, MQTT_PORT);
        return true;
    }
    
    Serial.println("[MQTT] Initial connection failed");
    return false;
}

bool mqttIsConnected() {
    return mqttClient.connected();
}

bool mqttReconnect() {
    if (mqttClient.connected()) {
        return true;
    }
    
    Serial.printf("[MQTT] Attempting connection to %s\n", MQTT_BROKER);
    
    // Create client ID
    char clientId[50];
    snprintf(clientId, sizeof(clientId), "%s-%llX", MQTT_CLIENT_ID, ESP.getEfuseMac());
    
    // Attempt to connect
    bool connected = false;
#ifdef MQTT_USERNAME
    connected = mqttClient.connect(clientId, MQTT_USERNAME, MQTT_PASSWORD);
#else
    connected = mqttClient.connect(clientId);
#endif
    
    if (!connected) {
        Serial.printf("[MQTT] Connection failed, rc=%d\n", mqttClient.state());
        return false;
    }
    
    Serial.println("[MQTT] Connected!");
    s_mqttReady = true;
    return true;
}

bool mqttPublish(const char* topic, const char* payload) {
    if (!mqttClient.connected()) {
        Serial.println("[MQTT] Not connected, attempting reconnect");
        if (!mqttReconnect()) {
            return false;
        }
    }
    
    if (mqttClient.publish(topic, payload)) {
        Serial.printf("[MQTT] Published to %s\n", topic);
        return true;
    } else {
        Serial.printf("[MQTT] Publish failed, rc=%d\n", mqttClient.state());
        return false;
    }
}

bool mqttSubscribe(const char* topic) {
    if (!mqttClient.connected()) {
        return false;
    }
    
    if (mqttClient.subscribe(topic)) {
        Serial.printf("[MQTT] Subscribed to %s\n", topic);
        return true;
    } else {
        Serial.printf("[MQTT] Subscribe failed, rc=%d\n", mqttClient.state());
        return false;
    }
}

void mqttProcess() {
    if (s_mqttReady) {
        if (!mqttClient.connected()) {
            // Attempt reconnect if not connected
            static unsigned long lastReconnectAttempt = 0;
            unsigned long now = millis();
            
            if (now - lastReconnectAttempt > MQTT_RECONNECT_INTERVAL_MS) {
                lastReconnectAttempt = now;
                if (mqttReconnect()) {
                    lastReconnectAttempt = 0;
                }
            }
        } else {
            // Process incoming messages
            mqttClient.loop();
        }
    }
}

void mqttCleanup() {
    if (mqttClient.connected()) {
        mqttClient.disconnect();
    }
    s_mqttReady = false;
}

}  // namespace hal
