#ifndef ROOM_CONFIG_H
#define ROOM_CONFIG_H

#include "app_cfg.h"  // Make sure this includes your STD_ON/STD_OFF definitions

// Platform check
#ifndef ESP32
    #error "This application requires ESP32 platform"
#endif


// Hardware Pin Configuration
#define ROOM_LED1_PIN           25
#define ROOM_LED2_PIN           26
#define ROOM_BUTTON1_PIN        18
#define ROOM_BUTTON2_PIN        19

// PWM Configuration
#define ROOM_PWM_CHANNEL_LED1   0
#define ROOM_PWM_CHANNEL_LED2   1
#define ROOM_PWM_FREQUENCY      5000
#define ROOM_PWM_RESOLUTION     8

// Auto-dimming thresholds
#define ROOM_LIGHT_THRESHOLD_LOW    30  // Below this: full brightness
#define ROOM_LIGHT_THRESHOLD_HIGH   70  // Above this: dimmed
#define ROOM_BRIGHTNESS_MAX         255
#define ROOM_BRIGHTNESS_MIN         51  // 20% of 255

// Timing Configuration
#define ROOM_BUTTON_DEBOUNCE_MS     200
#define ROOM_MQTT_PUBLISH_INTERVAL  2000  // Publish LDR every 2 seconds
#define ROOM_LED_UPDATE_INTERVAL    100   // Update LED brightness every 100ms

// Debug Configuration
#define ROOM_DEBUG_ENABLED          STD_ON

#if ROOM_DEBUG_ENABLED == STD_ON
#define ROOM_DEBUG_PRINT(x)     Serial.print(x)
#define ROOM_DEBUG_PRINTLN(x)   Serial.println(x)
#else
#define ROOM_DEBUG_PRINT(x)
#define ROOM_DEBUG_PRINTLN(x)
#endif

#endif // ROOM_CONFIG_H
