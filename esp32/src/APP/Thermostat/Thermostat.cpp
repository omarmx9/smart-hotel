#include "Thermostat.h"
#include "../../App_cfg.h"
#include "../../HAL/POT/POT.h"
#include "../../HAL/LED/LED.h"
#include "../../HAL/MQTT/MQTT.h"
#include <Arduino.h>

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

typedef enum {
    STATE_OFF,
    STATE_HEATING_LOW,
    STATE_HEATING_MEDIUM,
    STATE_HEATING_HIGH
} ThermostatState_t;

static ThermostatState_t g_state = STATE_OFF;

static Thermostat_Status_t g_status = {
    .temperature = 0.0f,
    .humidity = 0.0f,
    .target_temp = 22.0f,
    .fan_speed = FAN_SPEED_OFF,
    .mode = THERMOSTAT_MODE_AUTO,
    .heating = false
};

static unsigned long g_lastUpdate = 0;
static unsigned long g_lastPublish = 0;

// Private function prototypes
static float mapPotToTemp(uint16_t pot_value);
static float mapPotToHumidity(uint16_t pot_value);
static void updateLEDs(void);
static void autoControlLogic(void);

void Thermostat_Init(void)
{
    // Initialize all three POTs (you'll need to modify POT.cpp to support multiple instances)
    POT_init();
    
    // Initialize LEDs
    LED_init(LED_LOW_SPEED);
    LED_init(LED_MED_SPEED);
    LED_init(LED_HIGH_SPEED);
    
    // Turn off all LEDs initially
    LED_OFF(LED_LOW_SPEED);
    LED_OFF(LED_MED_SPEED);
    LED_OFF(LED_HIGH_SPEED);
    
    Serial.println("Thermostat initialized");
}

void Thermostat_Process(void)
{
    unsigned long now = millis();
    
    // Update sensor readings periodically
    if (now - g_lastUpdate >= UPDATE_INTERVAL_MS)
    {
        
        // Read temperature POT
        uint16_t temp_raw = analogRead(POT_TEMP_PIN);

            Serial.print("Pot value: ");
            Serial.println(temp_raw);

            delay(500);  // slow down prints

        g_status.temperature = mapPotToTemp(temp_raw);
        
        // Read humidity POT
        uint16_t humidity_raw = analogRead(POT_HUMIDITY_PIN);
        g_status.humidity = mapPotToHumidity(humidity_raw);
        
        // Read target temperature POT
        uint16_t target_raw = analogRead(POT_TARGET_PIN);
        g_status.target_temp = mapPotToTemp(target_raw);
        
        // Apply control logic if in AUTO mode
        if (g_status.mode == THERMOSTAT_MODE_AUTO)
        {
            autoControlLogic();
        }
        
        // Update LED display
        updateLEDs();
        
        g_lastUpdate = now;
    }
    
    // Publish to MQTT periodically
    if (now - g_lastPublish >= MQTT_PUBLISH_INTERVAL_MS)
    {
        Thermostat_PublishData();
        g_lastPublish = now;
    }
}

void Thermostat_SetMode(Thermostat_Mode_t mode)
{
    g_status.mode = mode;
    
    if (mode == THERMOSTAT_MODE_OFF)
    {
        g_status.fan_speed = FAN_SPEED_OFF;
        g_status.heating = false;
        updateLEDs();
    }
}

void Thermostat_SetFanSpeed(Fan_Speed_t speed)
{
    if (g_status.mode == THERMOSTAT_MODE_MANUAL)
    {
        g_status.fan_speed = speed;
        updateLEDs();
    }
}

void Thermostat_SetTargetTemp(float temp)
{
    if (temp >= POT_TO_TEMP_MIN && temp <= POT_TO_TEMP_MAX)
    {
        g_status.target_temp = temp;
    }
}

Thermostat_Status_t Thermostat_GetStatus(void)
{
    return g_status;
}

void Thermostat_PublishData(void)
{
    char buffer[16];
    
    // Publish temperature
    dtostrf(g_status.temperature, 4, 1, buffer);
    MQTT_Publish("home/thermostat/temperature", buffer);
    
    // Publish humidity
    dtostrf(g_status.humidity, 4, 1, buffer);
    MQTT_Publish("home/thermostat/humidity", buffer);
    
    // Publish target temperature
    dtostrf(g_status.target_temp, 4, 1, buffer);
    MQTT_Publish("home/thermostat/target", buffer);
    
    // Publish fan speed
    snprintf(buffer, sizeof(buffer), "%d", g_status.fan_speed);
    MQTT_Publish("home/thermostat/fanspeed", buffer);
    
    // Publish heating status
    MQTT_Publish("home/thermostat/heating", g_status.heating ? "1" : "0");
    
    // Publish mode
    snprintf(buffer, sizeof(buffer), "%d", g_status.mode);
    MQTT_Publish("home/thermostat/mode", buffer);
}
// Private functions
static float mapPotToTemp(uint16_t pot_value)
{
    // Map 0-4095 (12-bit ADC) to temperature range
    return POT_TO_TEMP_MIN + ((float)pot_value / 4095.0f) * (POT_TO_TEMP_MAX - POT_TO_TEMP_MIN);
}

static float mapPotToHumidity(uint16_t pot_value)
{
    // Map 0-4095 (12-bit ADC) to humidity range
    return POT_TO_HUMIDITY_MIN + ((float)pot_value / 4095.0f) * (POT_TO_HUMIDITY_MAX - POT_TO_HUMIDITY_MIN);
}

static void updateLEDs(void)
{
    // Turn on appropriate LED based on fan speed
    switch (g_status.fan_speed)
    {
        case FAN_SPEED_LOW:
            LED_OFF(LED_MED_SPEED);
            LED_OFF(LED_HIGH_SPEED);
            LED_ON(LED_LOW_SPEED);
            break;
        case FAN_SPEED_MEDIUM:
            LED_ON(LED_MED_SPEED);
            LED_OFF(LED_HIGH_SPEED);
            LED_OFF(LED_LOW_SPEED);
            break;
        case FAN_SPEED_HIGH:
            LED_OFF(LED_MED_SPEED);
            LED_ON(LED_HIGH_SPEED);
            LED_OFF(LED_LOW_SPEED);
            break;
        case FAN_SPEED_OFF:
        default:
            break;
    }
}

static void autoControlLogic(void)
{
    float temp_diff = g_status.target_temp - g_status.temperature;
    
    // Determine if heating is needed
    if (temp_diff > TEMP_DEADBAND)
    {
        g_status.heating = true;
        
        // Adjust fan speed based on temperature difference
        if (temp_diff > 5.0f)
        {
            g_status.fan_speed = FAN_SPEED_HIGH;
        }
        else if (temp_diff > 2.0f)
        {
            g_status.fan_speed = FAN_SPEED_MEDIUM;
        }
        else
        {
            g_status.fan_speed = FAN_SPEED_LOW;
        }
    }
    else if (temp_diff < -TEMP_DEADBAND)
    {
        // Too hot, turn off heating but keep fan on low for circulation
        g_status.heating = false;
        g_status.fan_speed = FAN_SPEED_LOW;
    }
    else
    {
        // Within deadband, maintain current state or turn off
        g_status.heating = false;
        g_status.fan_speed = FAN_SPEED_OFF;
    }
}