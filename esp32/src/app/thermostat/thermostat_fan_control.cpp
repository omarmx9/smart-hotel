#include <Arduino.h>

#include "thermostat_fan_control.h"
#include "../../app_cfg.h"

#include "../../hal/sensors/hal_potentiometer/hal_potentiometer.h"
#include "../../hal/sensors/hal_mq5/hal_mq5.h"
#include "../../hal/sensors/hal_dht/hal_dht.h"
#include "../../hal/hal_led/hal_led.h"
#include "../../hal/communication/hal_mqtt/hal_mqtt.h"

#include "thermostat_config.h"
#include "thermostat_types.h"


static int pot_raw_value = 0 ; 
static int target_temp   = 0 ;

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

static SemaphoreHandle_t g_temperatureMutex    = NULL;
static SemaphoreHandle_t g_targetTempMutex     = NULL; 

void Thermostat_InitMutexes (void)
{
    g_temperatureMutex = xSemaphoreCreateMutex();
    configASSERT(g_temperatureMutex != NULL);  // Ensure creation succeeded

    g_targetTempMutex = xSemaphoreCreateMutex();
    configASSERT(g_targetTempMutex != NULL);  // Ensure creation succeeded

}
// Private function prototypes
static float mapPotToHumidity(uint16_t pot_value);
static void  updateLEDs(void);
static void  autoControlLogic(void);

void Thermostat_Init_Hardware(void)
{
    // Initialize all three POTs (you'll need to modify POT.cpp to support multiple instances)
    POT_init();
    //MQ5_1_init();
    DHT22_INIT();
    // Initialize LEDs
    LED_init(LED_LOW_SPEED);
    LED_init(LED_MED_SPEED);
    LED_init(LED_HIGH_SPEED);
    
    // Turn off all LEDs initially
    LED_OFF(LED_LOW_SPEED);
    LED_OFF(LED_MED_SPEED);
    LED_OFF(LED_HIGH_SPEED);
    
    Serial.println("Thermostat Hardware initialized");
}


void Thermostat_SetMode(Thermostat_Mode_t mode)
{
    g_status.mode = mode;

    Serial.print("[DEBUG] Thermostat_SetMode() -> ");
    Serial.println(mode);

    
}

Thermostat_Mode_t Thermostat_GetMode(void)
{
   return g_status.mode;
    
}



void Thermostat_StoreTemp(float temp)
{
    if (xSemaphoreTake(g_temperatureMutex, portMAX_DELAY) == pdTRUE) {
        if (g_status.temperature != temp) {
            g_status.temperature = temp;
            Serial.print("[DEBUG] Temperature stored: ");
            Serial.println(temp);
        }
        xSemaphoreGive(g_temperatureMutex);
    }
}

float Thermostat_GetTemp(void)
{
    static float cached_temp = 25.0f;

    xSemaphoreTake(g_temperatureMutex, portMAX_DELAY);
    cached_temp = g_status.temperature;
    xSemaphoreGive(g_temperatureMutex);

    Serial.print("[DEBUG] Thermostat_GetTemp() -> ");
    Serial.println(cached_temp);

    return cached_temp ;
}

bool Thermostat_SetTargetTemp(float target_temp)
{
    bool changed = false;
    if (target_temp >= POT_TO_TEMP_MIN && target_temp <= POT_TO_TEMP_MAX)
    {
        if (xSemaphoreTake(g_targetTempMutex, portMAX_DELAY) == pdTRUE) {
            if (g_status.target_temp != target_temp) {
                g_status.target_temp = target_temp;
                changed = true;
                Serial.print("[DEBUG] Target temp updated to: ");
                Serial.println(target_temp);
            }
            xSemaphoreGive(g_targetTempMutex);
        }
    }

    if (!changed) {
        Serial.println("[DEBUG] Target temp unchanged or out of range");
    }

    return changed ; 
}
                                                               
float Thermostat_GetTargetTemp(void)
{
    static float cached_target = 25.0f;

    xSemaphoreTake(g_targetTempMutex, portMAX_DELAY);
    cached_target = g_status.target_temp;
    xSemaphoreGive(g_targetTempMutex);

    Serial.print("[DEBUG] Thermostat_GetTargetTemp() -> ");
    Serial.println(cached_target);

    return cached_target ;
}

void updateLEDs(Fan_Speed_t speed)
{
    // Turn on appropriate LED based on fan speed
    g_status.fan_speed = speed ; 
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

void Thermostat_SetFanSpeed(Fan_Speed_t speed)
{
    if (g_status.mode == THERMOSTAT_MODE_MANUAL)
    {
        g_status.fan_speed = speed;
        Serial.print("[DEBUG] Thermostat_SetFanSpeed() -> ");
        Serial.println(speed);
        updateLEDs(speed);


    }
}

Fan_Speed_t Thermostat_GetFanSpeed (void)
{
    return g_status.fan_speed ;

}

float mapPotToTemp(uint16_t pot_value)
{

    // Map 0-4095 (12-bit ADC) to temperature range
    return POT_TO_TEMP_MIN + ((float)pot_value / 4095.0f) * (POT_TO_TEMP_MAX - POT_TO_TEMP_MIN);
}

Thermostat_Status_t Thermostat_GetStatus(void)
{
    return g_status;
}



void Fan_Logic (float target_temp, float current_temp)
{
        float diff = abs(current_temp - target_temp);

        if (diff <= 0.5) {
            g_status.fan_speed = FAN_SPEED_OFF;
            updateLEDs(FAN_SPEED_OFF);

        } else if (diff <= 1.5) {
            g_status.fan_speed = FAN_SPEED_LOW;
            updateLEDs(FAN_SPEED_LOW);
        } else if (diff <= 3.0) {
            g_status.fan_speed = FAN_SPEED_MEDIUM;
            updateLEDs(FAN_SPEED_MEDIUM);

        } else {
            g_status.fan_speed = FAN_SPEED_HIGH;
            updateLEDs(FAN_SPEED_HIGH);

        }


}