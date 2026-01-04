#ifndef THERMOSTAT_CONFIG_H
#define THERMOSTAT_CONFIG_H

// ==================== DEBUG CONFIGURATION ====================
#define DEBUG_ENABLED           1 // Set to 0 to disable all debug output
#define DEBUG_TEMP_SENSOR       1  // Debug temperature sensor task
#define DEBUG_USER_INPUT        1  // Debug user input task
#define DEBUG_FAN_CONTROL       1  // Debug fan control task
#define DEBUG_MQTT              1  // Debug MQTT task
#define DEBUG_WIFI              1  // Debug WiFi task
#define DEBUG_STACK_MONITOR     0  // Monitor stack usage
#define DEBUG_TIMING            0  // Show timing information
#define DEBUG_QUEUE_STATUS      0  // Monitor queue status
#define DEBUG_HUM_SENSOR        1  // Debug temperature sensor task

// Stack monitoring interval (ms)
#define STACK_MONITOR_INTERVAL_MS  10000

// ==================== DEBUG MACROS ====================
#if DEBUG_ENABLED
    #define DEBUG_PRINT(module, fmt, ...) \
        do { \
            if (DEBUG_##module) { \
                Serial.print("[" #module "] "); \
                Serial.printf(fmt, ##__VA_ARGS__); \
                Serial.println(); \
            } \
        } while(0)
    
    #define DEBUG_PRINT_RAW(module, fmt, ...) \
        do { \
            if (DEBUG_##module) { \
                Serial.printf(fmt, ##__VA_ARGS__); \
            } \
        } while(0)
#else
    #define DEBUG_PRINT(module, fmt, ...)
    #define DEBUG_PRINT_RAW(module, fmt, ...)
#endif



// ==================== CONSTANTS ====================
#define TEMP_QUEUE_SIZE              5
#define TEMP_SENSOR_SAMPLE_RATE_MS   3000
#define INPUT_SAMPLE_RATE_MS         3000
#define LOGIC_UPDATE_RATE_MS         3000
#define MQTT_UPDATE_RATE_MS          3000
#define TEMP_CHANGE_THRESHOLD        0.1f   // Celsius
#define HYSTERESIS_VALUE             0.2f   // Celsius
#define INVALID_TEMP_VALUE           -100.0f
#define INVALID_HUMDITY_VALUE        -100.0f

#define TARGET_TEMP_THRESHOLD  1   // degrees Celsius

// Fan state thresholds
#define FAN_MEDIUM_THRESHOLD_HIGH    1.0f   // Switch to medium when delta >= this
#define FAN_MEDIUM_THRESHOLD_LOW     1.0f   // Switch to low when delta < this
#define FAN_HIGH_THRESHOLD_HIGH      3.0f   // Switch to high when delta >= this
#define FAN_HIGH_THRESHOLD_LOW       3.0f   // Switch to medium when delta < this
/////////////////

#define POT_TEMP_PIN     34  // POT1 for temperature reading
#define POT_HUMIDITY_PIN 35  // POT2 for humidity reading
#define POT_TARGET_PIN   32  // POT3 for target temperature knob

#define LED_LOW_SPEED    25  // LED1 for low fan speed
#define LED_MED_SPEED    26  // LED2 for medium fan speed
#define LED_HIGH_SPEED   27  // LED3 for high fan speed

#define POT_TO_TEMP_MIN    15.0f  // Min temp 15°C
#define POT_TO_TEMP_MAX    35.0f  // Max temp 35°C
#define POT_TO_HUMIDITY_MIN 20.0f // Min humidity 20%
#define POT_TO_HUMIDITY_MAX 90.0f // Max humidity 90%

#define TEMP_DEADBAND      0.5f   // Temperature deadband in °C
#define UPDATE_INTERVAL_MS 1000   // Update every 1 second
#define MQTT_PUBLISH_INTERVAL_MS 5000 // Publish every 5 seconds


// ==================== STACK SIZE DEFINITIONS ====================
#define TEMP_SENSOR_STACK_SIZE  3072
#define USER_INPUT_STACK_SIZE   3072
#define FAN_CONTROL_STACK_SIZE  3072
#define MQTT_STACK_SIZE         4096
#define WIFI_STACK_SIZE         4096

// ==================== TASK PRIORITY DEFINITIONS ====================
#define TEMP_SENSOR_PRIORITY    3
#define USER_INPUT_PRIORITY     2
#define FAN_CONTROL_PRIORITY    2
#define MQTT_PRIORITY           1
#define WIFI_PRIORITY           1

// Event bits
#define TEMP_UPDATED_BIT      (1 << 0)
#define TARGET_UPDATED_BIT    (1 << 1)
#define TARGET_FROM_MQTT_BIT  (1 << 2)
#define MODE_UPDATED_BIT      (1 << 3)
#define FAN_SPEED_UPDATED_BIT (1 << 4)

#endif