#include "hal_mqtt.h"
#include <WiFi.h>
#include "../hal_wifi/hal_wifi.h"
#include "../../../app/thermostat/thermostat_fan_control.h"
#include "../../../app_cfg.h"
#include "../../../app/room/room_config.h"
#include "../../../app/room/room_types.h"
#include "../../../app/room/room_logic.h"
#include "../../../app/room/room_rtos.h"
#include "helpers.h"

static WiFiClient wifiClient;
static PubSubClient mqttClient(wifiClient);



static const char* g_broker;
static int g_port;


/**
 * @brief Parse mode string to enum
 */
static Thermostat_Mode_t ParseMode(const char* mode_str) {
    if (strcasecmp(mode_str, "off") == 0) {
        return THERMOSTAT_MODE_OFF;
    } else if (strcasecmp(mode_str, "auto") == 0) {
        return THERMOSTAT_MODE_AUTO;
    } else if (strcasecmp(mode_str, "manual") == 0) {
        return THERMOSTAT_MODE_MANUAL;
    }
    return THERMOSTAT_MODE_OFF;  // Default to OFF for safety
}

/**
 * @brief Parse fan speed string to enum
 */
static Fan_Speed_t ParseFanSpeed(const char* speed_str) {
    if (strcasecmp(speed_str, "off") == 0 || strcmp(speed_str, "0") == 0) {
        return FAN_SPEED_OFF;
    } else if (strcasecmp(speed_str, "low") == 0 || strcmp(speed_str, "1") == 0) {
        return FAN_SPEED_LOW;
    } else if (strcasecmp(speed_str, "medium") == 0 || strcmp(speed_str, "2") == 0) {
        return FAN_SPEED_MEDIUM;
    } else if (strcasecmp(speed_str, "high") == 0 || strcmp(speed_str, "3") == 0) {
        return FAN_SPEED_HIGH;
    }
    return FAN_SPEED_OFF;  // Default to OFF
}






static void MQTT_Reconnect(void);

static void mqttCallback(char* topic, byte* payload, unsigned int length)
{
    char buffer[32];
    if (length >= sizeof(buffer)) length = sizeof(buffer) - 1;

    memcpy(buffer, payload, length);
    buffer[length] = '\0';

    if (strcmp(topic, MQTT_TOPIC_TARGET) == 0)
    {
        float newTarget = atof(buffer);
        bool  changed   = Thermostat_SetTargetTemp(newTarget);

        if(changed)
        {
            thermostatMqttEventSet(); /// in mqtt.cpp
        }

        Serial.print("New target temp from MQTT: ");
        Serial.println(newTarget);
    }
}



/**
 * @brief MQTT message callback - Called when message is received
 * @param topic The topic the message was received on
 * @param payload The message payload (NOT null-terminated!)
 * @param length Length of the payload
 * 
 * @note This is typically called from the MQTT library's callback
 *       Add this to your PubSubClient or MQTT library callback
 */
void MQTT_MessageCallback(char* topic, uint8_t* payload, unsigned int length) {
    // Create null-terminated string from payload
    char message[128] = {0};  // Increased size for room messages
    if (length >= sizeof(message)) {
        length = sizeof(message) - 1;
    }
    memcpy(message, payload, length);
    message[length] = '\0';
    
    Serial.printf("[MQTT RX] Topic: %s, Payload: %s\n", topic, message);
    
    // ========================================================================
    // THERMOSTAT TOPICS
    // ========================================================================
    
    if (strcmp(topic, MQTT_TOPIC_TARGET) == 0) {
        // Set target temperature from MQTT
        float target = atof(message);
        if (target >= 15.0f && target <= 35.0f) {  // Validate range
            Thermostat_SetTargetTemp(target);
            thermostatMqttEventSet();  // Trigger fan control update
            Serial.printf("[MQTT] Target temp set to: %.1f°C\n", target);
        } else {
            Serial.printf("[MQTT] Invalid target temp: %.1f°C\n", target);
        }
    }
    else if (strcmp(topic, MQTT_TOPIC_CONTROL) == 0) {
        // Set thermostat mode from MQTT
        Thermostat_Mode_t mode = ParseMode(message);
        Thermostat_SetMode(mode);
        thermostatMqttModeEventSet();  // Trigger fan control update
        
        const char* mode_name = (mode == THERMOSTAT_MODE_OFF) ? "OFF" :
                                (mode == THERMOSTAT_MODE_AUTO) ? "AUTO" :
                                (mode == THERMOSTAT_MODE_MANUAL) ? "MANUAL" : "UNKNOWN";
        Serial.printf("[MQTT] Thermostat mode set to: %s\n", mode_name);
        
        // Publish mode status confirmation
        //MQTT_Publish(MQTT_TOPIC_MODE_STATUS, mode_name);
    }
    else if (strcmp(topic, MQTT_TOPIC_SET_SPEED) == 0) {
        // Set manual fan speed from MQTT (only works in MANUAL mode)
        Fan_Speed_t speed = ParseFanSpeed(message);
        
        Thermostat_Mode_t current_mode = Thermostat_GetMode();
        if (current_mode == THERMOSTAT_MODE_MANUAL) {
            Thermostat_SetFanSpeed(speed);
            thermostatMqttFanSpeedEventSet();  // Trigger fan control update
            
            const char* speed_name = (speed == FAN_SPEED_OFF) ? "OFF" :
                                     (speed == FAN_SPEED_LOW) ? "LOW" :
                                     (speed == FAN_SPEED_MEDIUM) ? "MEDIUM" :
                                     (speed == FAN_SPEED_HIGH) ? "HIGH" : "UNKNOWN";
            Serial.printf("[MQTT] Fan speed set to: %s\n", speed_name);
            
            // Publish speed status confirmation
            //MQTT_Publish(MQTT_TOPIC_FAN_SPEED_STATUS, speed_name);
        } else {
            Serial.printf("[MQTT] Cannot set fan speed - not in MANUAL mode (current: %d)\n", current_mode);
        }
    }
    
    // ========================================================================
    // ROOM LIGHTING TOPICS
    // ========================================================================
    
    else if (strcmp(topic, ROOM_TOPIC_MODE_CTRL) == 0) {
        // Set room lighting mode from MQTT
        Room_Mode_t room_mode = Room_Logic_ParseMode(message);
        if (room_mode != 0xFF) {  // Valid mode
            Room_Logic_SetMode(room_mode);
            const char* mode_str = Room_Logic_GetModeString();
            Serial.printf("[MQTT] Room mode set to: %s\n", mode_str);
            
            // Publish mode status confirmation
            Room_RTOS_PublishModeStatus();
        } else {
            Serial.printf("[MQTT] Invalid room mode: %s\n", message);
        }
    }
    else if (strcmp(topic, ROOM_TOPIC_LED1_CTRL) == 0) {
        // Control LED1 (only works in MANUAL mode)
        Room_Mode_t current_room_mode = Room_Logic_GetMode();
        
        if (current_room_mode != ROOM_MODE_MANUAL) {
            Serial.printf("[MQTT] Cannot control LED1 - Room mode is %s (need MANUAL)\n", 
                         Room_Logic_GetModeString());
            return;
        }
        
        Room_LED_State_t state = Room_Logic_ParseLEDState(message);
        if (state != 0xFF) {  // Valid state
            Room_Logic_SetLED(ROOM_LED_1, state, ROOM_CONTROL_MQTT);
            Serial.printf("[MQTT] LED1 set to: %s\n", state == ROOM_LED_ON ? "ON" : "OFF");
            
            // Publish LED status confirmation
            Room_RTOS_PublishLEDStatus(ROOM_LED_1);
        } else {
            Serial.printf("[MQTT] Invalid LED1 command: %s\n", message);
        }
    }
    else if (strcmp(topic, ROOM_TOPIC_LED2_CTRL) == 0) {
        // Control LED2 (only works in MANUAL mode)
        Room_Mode_t current_room_mode = Room_Logic_GetMode();
        
        if (current_room_mode != ROOM_MODE_MANUAL) {
            Serial.printf("[MQTT] Cannot control LED2 - Room mode is %s (need MANUAL)\n", 
                         Room_Logic_GetModeString());
            return;
        }
        
        Room_LED_State_t state = Room_Logic_ParseLEDState(message);
        if (state != 0xFF) {  // Valid state
            Room_Logic_SetLED(ROOM_LED_2, state, ROOM_CONTROL_MQTT);
            Serial.printf("[MQTT] LED2 set to: %s\n", state == ROOM_LED_ON ? "ON" : "OFF");
            
            // Publish LED status confirmation
            Room_RTOS_PublishLEDStatus(ROOM_LED_2);
        } else {
            Serial.printf("[MQTT] Invalid LED2 command: %s\n", message);
        }
    }
    else if (strcmp(topic, ROOM_TOPIC_AUTO_DIM) == 0) {
        // Deprecated: Auto-dim control (maps to room mode)
        Room_AutoDimMode_t autodim_mode = Room_Logic_ParseAutoDimMode(message);
        if (autodim_mode != 0xFF) {  // Valid mode
            Room_Logic_SetAutoDimMode(autodim_mode);  // This maps to AUTO/MANUAL mode
            Serial.printf("[MQTT] Auto-dim set to: %s\n", 
                         autodim_mode == ROOM_AUTO_DIM_ENABLED ? "ENABLED" : "DISABLED");
            
            // Publish mode status confirmation
            Room_RTOS_PublishModeStatus();
        } else {
            Serial.printf("[MQTT] Invalid auto-dim command: %s\n", message);
        }
    }
    
    // ========================================================================
    // UNKNOWN TOPIC
    // ========================================================================
    
    else {
        Serial.printf("[MQTT] Unknown topic: %s\n", topic);
    }
}



void MQTT_Init(const char* broker, int port)
{
    g_broker = broker;
    g_port = port;

    mqttClient.setServer(g_broker, g_port);
    mqttClient.setCallback(MQTT_MessageCallback);
}

void MQTT_Loop(void)
{
    // Only try MQTT if WiFi is connected
    if (WIFI_IsConnected())
    {
        if (!mqttClient.connected()) MQTT_Reconnect();
        mqttClient.loop();
    }
}

void MQTT_SubscribeAll(void)
{
    mqttClient.subscribe("home/thermostat/temperature");
    mqttClient.subscribe("home/thermostat/humidity");
    mqttClient.subscribe (MQTT_TOPIC_TARGET);
    mqttClient.subscribe("home/thermostat/heating");
    mqttClient.subscribe("home/thermostat/distance");
    mqttClient.subscribe("home/thermostat/pot");
    mqttClient.subscribe("home/thermostat/control");
}


void MQTT_Publish(const char* topic, const char* payload)
{
    if (!WIFI_IsConnected() || !mqttClient.connected()) 
    {
        Serial.println("MQTT publish failed: Not connected");
        return;
    }

    if (mqttClient.publish(topic, payload))
    {
        Serial.print("Published to ");
        Serial.print(topic);
        Serial.print(": ");
        Serial.println(payload);
    }
    else
    {
        Serial.println("MQTT publish failed");
    }
}


bool MQTT_IsConnected(void)
{
    return mqttClient.connected();
}
void MQTT_SubscribeTopics(void)
{
    if (MQTT_IsConnected())
    {
        mqttClient.subscribe(MQTT_TOPIC_TARGET);
        mqttClient.subscribe(MQTT_TOPIC_TEMP);
        mqttClient.subscribe(MQTT_TOPIC_SET_SPEED);
        mqttClient.subscribe(MQTT_TOPIC_CONTROL);
        mqttClient.subscribe(MQTT_TOPIC_HUMIDITY);
        
        mqttClient.subscribe(ROOM_TOPIC_MODE_CTRL);
        mqttClient.subscribe(ROOM_TOPIC_LED1_CTRL);
        mqttClient.subscribe(ROOM_TOPIC_LED2_CTRL);
    //    mqttClient.subscribe(ROOM_TOPIC_AUTO_DIM);

        Serial.println("[MQTT] Subscribed to target & control topics");
    }
}


static void MQTT_Reconnect(void)
{
    while (!mqttClient.connected())
    {
        if (!WIFI_IsConnected())
        {
            delay(1000); // Wait until WiFi reconnects
            continue;
        }

        String id = "ESP32-" + String(random(0xffff), HEX);
        if (mqttClient.connect(id.c_str()))
        {
            MQTT_SubscribeAll();
        }
        else
        {
            delay(2000);
        }
    }
}
