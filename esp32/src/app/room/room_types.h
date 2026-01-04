#ifndef ROOM_TYPES_H
#define ROOM_TYPES_H

#include <stdint.h>

// LED identifiers
typedef enum {
    ROOM_LED_1 = 0,
    ROOM_LED_2,
    ROOM_LED_COUNT
} Room_LED_t;

// LED states
typedef enum {
    ROOM_LED_OFF = 0,
    ROOM_LED_ON
} Room_LED_State_t;

// Room Mode - Main control mode
typedef enum {
    ROOM_MODE_OFF = 0,      // All lights off, no control
    ROOM_MODE_MANUAL,       // Manual control via buttons/MQTT
    ROOM_MODE_AUTO          // Automatic control based on LDR
} Room_Mode_t;

// Control source
typedef enum {
    ROOM_CONTROL_BUTTON = 0,
    ROOM_CONTROL_MQTT,
    ROOM_CONTROL_AUTO
} Room_ControlSource_t;

// Auto-dim mode (deprecated - replaced by Room_Mode_t)
typedef enum {
    ROOM_AUTO_DIM_DISABLED = 0,
    ROOM_AUTO_DIM_ENABLED
} Room_AutoDimMode_t;

// Room status structure
typedef struct {
    Room_Mode_t mode;               // Current operating mode
    Room_LED_State_t led1_state;
    Room_LED_State_t led2_state;
    uint8_t led1_brightness;
    uint8_t led2_brightness;
    uint16_t ldr_raw_value;
    uint16_t ldr_percentage;
    bool mqtt_connected;
} Room_Status_t;

// MQTT message structure
typedef struct {
    char topic[64];
    char payload[128];
    uint16_t length;
} Room_MQTTMessage_t;

#endif // ROOM_TYPES_H
