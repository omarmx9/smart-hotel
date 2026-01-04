#include <Arduino.h>
#include "room_logic.h"
#include "../../hal/hal_pwm/hal_pwm.h"
#include "../../hal/hal_led/hal_led.h"
#include "../../hal/sensors/hal_ldr/hal_ldr.h"
#include "../../drivers/driver_gpio/driver_gpio.h"
#include <string.h>

// Internal state
static Room_Status_t room_status;
static unsigned long button1_last_press = 0;
static unsigned long button2_last_press = 0;
static unsigned long last_brightness_update = 0;

// Internal function prototypes
static void Room_Logic_SetBrightness(Room_LED_t led, uint8_t brightness);
static uint8_t Room_Logic_CalculateBrightness(uint16_t light_percentage);
static void Room_Logic_ApplyLEDState(Room_LED_t led);
static void Room_Logic_TurnOffAllLEDs(void);
static Room_LED_State_t Room_Logic_ParseLEDState(const char* payload);
static Room_Mode_t Room_Logic_ParseMode(const char* payload);
static Room_AutoDimMode_t Room_Logic_ParseAutoDimMode(const char* payload);

void Room_Logic_Init(void)
{
    ROOM_DEBUG_PRINTLN("Room Logic: Initializing...");
    
    // Initialize status structure
    room_status.mode = ROOM_MODE_MANUAL;  // Start in manual mode
    room_status.led1_state = ROOM_LED_OFF;
    room_status.led2_state = ROOM_LED_OFF;
    room_status.led1_brightness = ROOM_BRIGHTNESS_MAX;
    room_status.led2_brightness = ROOM_BRIGHTNESS_MAX;
    room_status.ldr_raw_value = 0;
    room_status.ldr_percentage = 0;
    room_status.mqtt_connected = false;
    
    // Initialize LEDs (basic GPIO init)
    LED_init(ROOM_LED1_PIN);
    LED_init(ROOM_LED2_PIN);
    
    // Setup PWM using HAL wrapper
    PWM_Init(ROOM_PWM_CHANNEL_LED1, ROOM_LED1_PIN, ROOM_PWM_FREQUENCY, ROOM_PWM_RESOLUTION);
    PWM_Init(ROOM_PWM_CHANNEL_LED2, ROOM_LED2_PIN, ROOM_PWM_FREQUENCY, ROOM_PWM_RESOLUTION);
    
    // Initialize buttons
    GPIO_PinInit(ROOM_BUTTON1_PIN, GPIO_INPUT_PULLUP);
    GPIO_PinInit(ROOM_BUTTON2_PIN, GPIO_INPUT_PULLUP);
    
    // Initialize LDR
    LDR_1_init();
    
    ROOM_DEBUG_PRINTLN("Room Logic: Initialized");
}

// ============================================================================
// Mode Control Functions
// ============================================================================

void Room_Logic_SetMode(Room_Mode_t mode)
{
    Room_Mode_t old_mode = room_status.mode;
    room_status.mode = mode;
    
    ROOM_DEBUG_PRINT("Mode changed: ");
    ROOM_DEBUG_PRINT(old_mode == ROOM_MODE_OFF ? "OFF" : 
                     old_mode == ROOM_MODE_MANUAL ? "MANUAL" : "AUTO");
    ROOM_DEBUG_PRINT(" -> ");
    ROOM_DEBUG_PRINTLN(mode == ROOM_MODE_OFF ? "OFF" : 
                       mode == ROOM_MODE_MANUAL ? "MANUAL" : "AUTO");
    
    // Handle mode-specific actions
    switch (mode) {
        case ROOM_MODE_OFF:
            // Turn off all LEDs
            Room_Logic_TurnOffAllLEDs();
            ROOM_DEBUG_PRINTLN("[MODE] All LEDs turned OFF");
            break;
            
        case ROOM_MODE_MANUAL:
            // Keep current LED states, set brightness to max
            room_status.led1_brightness = ROOM_BRIGHTNESS_MAX;
            room_status.led2_brightness = ROOM_BRIGHTNESS_MAX;
            Room_Logic_ApplyLEDState(ROOM_LED_1);
            Room_Logic_ApplyLEDState(ROOM_LED_2);
            ROOM_DEBUG_PRINTLN("[MODE] Manual control enabled");
            break;
            
        case ROOM_MODE_AUTO:
            // Turn on both LEDs and let auto-dimming handle brightness
            room_status.led1_state = ROOM_LED_ON;
            room_status.led2_state = ROOM_LED_ON;
            Room_Logic_UpdateAutoMode();  // Immediately update brightness
            ROOM_DEBUG_PRINTLN("[MODE] Auto control enabled");
            break;
    }
}

Room_Mode_t Room_Logic_GetMode(void)
{
    return room_status.mode;
}

const char* Room_Logic_GetModeString(void)
{
    switch (room_status.mode) {
        case ROOM_MODE_OFF:    return "OFF";
        case ROOM_MODE_MANUAL: return "MANUAL";
        case ROOM_MODE_AUTO:   return "AUTO";
        default:               return "UNKNOWN";
    }
}

// ============================================================================
// LED Control Functions
// ============================================================================

void Room_Logic_SetLED(Room_LED_t led, Room_LED_State_t state, Room_ControlSource_t source)
{
    if (led >= ROOM_LED_COUNT) return;
    
    // Check if mode allows manual control
    if (room_status.mode == ROOM_MODE_OFF) {
        ROOM_DEBUG_PRINTLN("[LED] Cannot control - System is OFF");
        return;
    }
    
    if (room_status.mode == ROOM_MODE_AUTO && source != ROOM_CONTROL_AUTO) {
        ROOM_DEBUG_PRINTLN("[LED] Cannot control - System is in AUTO mode");
        return;
    }
    
    if (led == ROOM_LED_1) {
        room_status.led1_state = state;
        ROOM_DEBUG_PRINT("LED1 set to: ");
    } else {
        room_status.led2_state = state;
        ROOM_DEBUG_PRINT("LED2 set to: ");
    }
    
    ROOM_DEBUG_PRINT(state == ROOM_LED_ON ? "ON" : "OFF");
    ROOM_DEBUG_PRINT(" via ");
    
    switch(source) {
        case ROOM_CONTROL_BUTTON:
            ROOM_DEBUG_PRINTLN("BUTTON");
            break;
        case ROOM_CONTROL_MQTT:
            ROOM_DEBUG_PRINTLN("MQTT");
            break;
        case ROOM_CONTROL_AUTO:
            ROOM_DEBUG_PRINTLN("AUTO");
            break;
    }
    
    Room_Logic_ApplyLEDState(led);
}

void Room_Logic_ToggleLED(Room_LED_t led, Room_ControlSource_t source)
{
    if (led >= ROOM_LED_COUNT) return;
    
    // Check if mode allows manual control
    if (room_status.mode != ROOM_MODE_MANUAL) {
        ROOM_DEBUG_PRINT("[LED] Cannot toggle - Mode is ");
        ROOM_DEBUG_PRINTLN(Room_Logic_GetModeString());
        return;
    }
    
    Room_LED_State_t current_state = (led == ROOM_LED_1) ? 
        room_status.led1_state : room_status.led2_state;
    
    Room_LED_State_t new_state = (current_state == ROOM_LED_ON) ? 
        ROOM_LED_OFF : ROOM_LED_ON;
    
    Room_Logic_SetLED(led, new_state, source);
}

Room_LED_State_t Room_Logic_GetLEDState(Room_LED_t led)
{
    if (led >= ROOM_LED_COUNT) return ROOM_LED_OFF;
    return (led == ROOM_LED_1) ? room_status.led1_state : room_status.led2_state;
}

uint8_t Room_Logic_GetLEDBrightness(Room_LED_t led)
{
    if (led >= ROOM_LED_COUNT) return 0;
    return (led == ROOM_LED_1) ? room_status.led1_brightness : room_status.led2_brightness;
}

void Room_Logic_SetAutoDimMode(Room_AutoDimMode_t mode)
{
    // Deprecated: Map to new mode system
    if (mode == ROOM_AUTO_DIM_ENABLED) {
        Room_Logic_SetMode(ROOM_MODE_AUTO);
    } else {
        Room_Logic_SetMode(ROOM_MODE_MANUAL);
    }
}

Room_AutoDimMode_t Room_Logic_GetAutoDimMode(void)
{
    // Deprecated: Map from new mode system
    return (room_status.mode == ROOM_MODE_AUTO) ? 
        ROOM_AUTO_DIM_ENABLED : ROOM_AUTO_DIM_DISABLED;
}

void Room_Logic_UpdateAutoDimming(void)
{
    // Deprecated: Use Room_Logic_UpdateAutoMode instead
    Room_Logic_UpdateAutoMode();
}

// ============================================================================
// Auto Mode Control
// ============================================================================

void Room_Logic_UpdateAutoMode(void)
{
    // Only update if in AUTO mode
    if (room_status.mode != ROOM_MODE_AUTO) {
        return;
    }
    
    // Throttle updates
    unsigned long current_time = millis();
    if (current_time - last_brightness_update < ROOM_LED_UPDATE_INTERVAL) {
        return;
    }
    last_brightness_update = current_time;
    
    // Calculate new brightness based on LDR
    uint8_t new_brightness = Room_Logic_CalculateBrightness(room_status.ldr_percentage);
    
    // Update if changed
    if (new_brightness != room_status.led1_brightness) {
        room_status.led1_brightness = new_brightness;
        room_status.led2_brightness = new_brightness;
        
        // Ensure LEDs are ON in AUTO mode and apply brightness
        room_status.led1_state = ROOM_LED_ON;
        room_status.led2_state = ROOM_LED_ON;
        
        Room_Logic_ApplyLEDState(ROOM_LED_1);
        Room_Logic_ApplyLEDState(ROOM_LED_2);
        
        ROOM_DEBUG_PRINT("[AUTO] Brightness updated to: ");
        ROOM_DEBUG_PRINT((new_brightness * 100) / 255);
        ROOM_DEBUG_PRINT("% (LDR: ");
        ROOM_DEBUG_PRINT(room_status.ldr_percentage);
        ROOM_DEBUG_PRINTLN("%)");
    }
}

void Room_Logic_UpdateLDR(void)
{
    // Call HAL main function
    LDR_1_main();
    
    // Update status
   // room_status.ldr_raw_value = LDR_1_getRawValue();
    room_status.ldr_percentage = LDR_1_getLightPercentage();
}

uint16_t Room_Logic_GetLDRRaw(void)
{
    return room_status.ldr_raw_value;
}

uint16_t Room_Logic_GetLDRPercentage(void)
{
    return room_status.ldr_percentage;
}

void Room_Logic_ProcessButtons(void)
{
    // Buttons only work in MANUAL mode
    if (room_status.mode != ROOM_MODE_MANUAL) {
        return;
    }
    
    unsigned long current_time = millis();
    
    // Button 1 - LED1 control
    if (digitalRead(ROOM_BUTTON1_PIN) == LOW) {
        if (current_time - button1_last_press > ROOM_BUTTON_DEBOUNCE_MS) {
            button1_last_press = current_time;
            Room_Logic_ToggleLED(ROOM_LED_1, ROOM_CONTROL_BUTTON);
        }
    }
    
    // Button 2 - LED2 control
    if (digitalRead(ROOM_BUTTON2_PIN) == LOW) {
        if (current_time - button2_last_press > ROOM_BUTTON_DEBOUNCE_MS) {
            button2_last_press = current_time;
            Room_Logic_ToggleLED(ROOM_LED_2, ROOM_CONTROL_BUTTON);
        }
    }
}

void Room_Logic_ProcessMQTTMessage(const char* topic, const char* payload)
{
    ROOM_DEBUG_PRINT("[MQTT] Processing - Topic: ");
    ROOM_DEBUG_PRINT(topic);
    ROOM_DEBUG_PRINT(", Payload: ");
    ROOM_DEBUG_PRINTLN(payload);
    
    // Mode Control - Works in any mode
    if (strcmp(topic, ROOM_TOPIC_MODE_CTRL) == 0) {
        Room_Mode_t mode = Room_Logic_ParseMode(payload);
        if (mode != 0xFF) {  // Valid mode
            Room_Logic_SetMode(mode);
            ROOM_DEBUG_PRINT("[MQTT] Mode set to: ");
            ROOM_DEBUG_PRINTLN(Room_Logic_GetModeString());
        } else {
            ROOM_DEBUG_PRINT("[MQTT] Invalid mode command: ");
            ROOM_DEBUG_PRINTLN(payload);
        }
    }
    // LED1 Control - Only works in MANUAL mode
    else if (strcmp(topic, ROOM_TOPIC_LED1_CTRL) == 0) {
        if (room_status.mode != ROOM_MODE_MANUAL) {
            ROOM_DEBUG_PRINT("[MQTT] Cannot control LED1 - Mode is ");
            ROOM_DEBUG_PRINTLN(Room_Logic_GetModeString());
            return;
        }
        Room_LED_State_t state = Room_Logic_ParseLEDState(payload);
        if (state != 0xFF) {  // Valid state
            Room_Logic_SetLED(ROOM_LED_1, state, ROOM_CONTROL_MQTT);
            ROOM_DEBUG_PRINT("[MQTT] LED1 set to: ");
            ROOM_DEBUG_PRINTLN(state == ROOM_LED_ON ? "ON" : "OFF");
        } else {
            ROOM_DEBUG_PRINT("[MQTT] Invalid LED1 command: ");
            ROOM_DEBUG_PRINTLN(payload);
        }
    }
    // LED2 Control - Only works in MANUAL mode
    else if (strcmp(topic, ROOM_TOPIC_LED2_CTRL) == 0) {
        if (room_status.mode != ROOM_MODE_MANUAL) {
            ROOM_DEBUG_PRINT("[MQTT] Cannot control LED2 - Mode is ");
            ROOM_DEBUG_PRINTLN(Room_Logic_GetModeString());
            return;
        }
        Room_LED_State_t state = Room_Logic_ParseLEDState(payload);
        if (state != 0xFF) {  // Valid state
            Room_Logic_SetLED(ROOM_LED_2, state, ROOM_CONTROL_MQTT);
            ROOM_DEBUG_PRINT("[MQTT] LED2 set to: ");
            ROOM_DEBUG_PRINTLN(state == ROOM_LED_ON ? "ON" : "OFF");
        } else {
            ROOM_DEBUG_PRINT("[MQTT] Invalid LED2 command: ");
            ROOM_DEBUG_PRINTLN(payload);
        }
    }
    // Auto-dim Control (deprecated - maps to mode)
    else if (strcmp(topic, ROOM_TOPIC_AUTO_DIM) == 0) {
        Room_AutoDimMode_t autodim_mode = Room_Logic_ParseAutoDimMode(payload);
        if (autodim_mode != 0xFF) {  // Valid mode
            Room_Logic_SetAutoDimMode(autodim_mode);
            ROOM_DEBUG_PRINT("[MQTT] Auto-dim set to: ");
            ROOM_DEBUG_PRINTLN(autodim_mode == ROOM_AUTO_DIM_ENABLED ? "ENABLED" : "DISABLED");
        } else {
            ROOM_DEBUG_PRINT("[MQTT] Invalid auto-dim command: ");
            ROOM_DEBUG_PRINTLN(payload);
        }
    }
    // Unknown topic
    else {
        ROOM_DEBUG_PRINT("[MQTT] Unknown topic: ");
        ROOM_DEBUG_PRINTLN(topic);
    }
}

void Room_Logic_GetStatus(Room_Status_t* status)
{
    if (status != NULL) {
        memcpy(status, &room_status, sizeof(Room_Status_t));
    }
}

// ============================================================================
// Internal Functions
// ============================================================================

static void Room_Logic_TurnOffAllLEDs(void)
{
    room_status.led1_state = ROOM_LED_OFF;
    room_status.led2_state = ROOM_LED_OFF;
    PWM_Write(ROOM_PWM_CHANNEL_LED1, 0);
    PWM_Write(ROOM_PWM_CHANNEL_LED2, 0);
}

static void Room_Logic_ApplyLEDState(Room_LED_t led)
{
    // Don't apply if mode is OFF
    if (room_status.mode == ROOM_MODE_OFF) {
        PWM_Write(ROOM_PWM_CHANNEL_LED1, 0);
        PWM_Write(ROOM_PWM_CHANNEL_LED2, 0);
        return;
    }
    
    uint8_t pwm_channel = (led == ROOM_LED_1) ? 
        ROOM_PWM_CHANNEL_LED1 : ROOM_PWM_CHANNEL_LED2;
    
    Room_LED_State_t state = (led == ROOM_LED_1) ? 
        room_status.led1_state : room_status.led2_state;
    
    uint8_t brightness = (led == ROOM_LED_1) ? 
        room_status.led1_brightness : room_status.led2_brightness;
    
    if (state == ROOM_LED_ON) {
        PWM_Write(pwm_channel, brightness);
    } else {
        PWM_Write(pwm_channel, 0);
    }
}

static uint8_t Room_Logic_CalculateBrightness(uint16_t light_percentage)
{
    uint8_t brightness;
    
    if (light_percentage < ROOM_LIGHT_THRESHOLD_LOW) {
        // Dark environment - full brightness
        brightness = ROOM_BRIGHTNESS_MAX;
    } 
    else if (light_percentage > ROOM_LIGHT_THRESHOLD_HIGH) {
        // Bright environment - minimum brightness
        brightness = ROOM_BRIGHTNESS_MIN;
    } 
    else {
        // Map the range between thresholds
        brightness = map(light_percentage, 
                        ROOM_LIGHT_THRESHOLD_LOW, 
                        ROOM_LIGHT_THRESHOLD_HIGH, 
                        ROOM_BRIGHTNESS_MAX, 
                        ROOM_BRIGHTNESS_MIN);
    }
    
    return brightness;
}

static Room_LED_State_t Room_Logic_ParseLEDState(const char* payload)
{
    // Check for ON commands
    if (strcmp(payload, "ON") == 0 || 
        strcmp(payload, "1") == 0 || 
        strcasecmp(payload, "true") == 0 ||
        strcasecmp(payload, "yes") == 0) {
        return ROOM_LED_ON;
    }
    // Check for OFF commands
    else if (strcmp(payload, "OFF") == 0 || 
             strcmp(payload, "0") == 0 || 
             strcasecmp(payload, "false") == 0 ||
             strcasecmp(payload, "no") == 0) {
        return ROOM_LED_OFF;
    }
    
    // Invalid command
    return (Room_LED_State_t)0xFF;
}

static Room_AutoDimMode_t Room_Logic_ParseAutoDimMode(const char* payload)
{
    // Check for ENABLED commands
    if (strcmp(payload, "ON") == 0 || 
        strcmp(payload, "1") == 0 || 
        strcasecmp(payload, "ENABLED") == 0 ||
        strcasecmp(payload, "ENABLE") == 0 ||
        strcasecmp(payload, "true") == 0 ||
        strcasecmp(payload, "yes") == 0) {
        return ROOM_AUTO_DIM_ENABLED;
    }
    // Check for DISABLED commands
    else if (strcmp(payload, "OFF") == 0 || 
             strcmp(payload, "0") == 0 || 
             strcasecmp(payload, "DISABLED") == 0 ||
             strcasecmp(payload, "DISABLE") == 0 ||
             strcasecmp(payload, "false") == 0 ||
             strcasecmp(payload, "no") == 0) {
        return ROOM_AUTO_DIM_DISABLED;
    }
    
    // Invalid command
    return (Room_AutoDimMode_t)0xFF;
}

static Room_Mode_t Room_Logic_ParseMode(const char* payload)
{
    // Check for OFF mode
    if (strcasecmp(payload, "OFF") == 0 || 
        strcmp(payload, "0") == 0) {
        return ROOM_MODE_OFF;
    }
    // Check for MANUAL mode
    else if (strcasecmp(payload, "MANUAL") == 0 || 
             strcmp(payload, "1") == 0 ||
             strcasecmp(payload, "MAN") == 0) {
        return ROOM_MODE_MANUAL;
    }
    // Check for AUTO mode
    else if (strcasecmp(payload, "AUTO") == 0 || 
             strcmp(payload, "2") == 0 ||
             strcasecmp(payload, "AUTOMATIC") == 0) {
        return ROOM_MODE_AUTO;
    }
    
    // Invalid command
    return (Room_Mode_t)0xFF;
}
