#include <Arduino.h>
#include "../../../app_cfg.h"
#include "../SensorH/SensorH.h"
#include "hal_potentiometer.h"

#if POT_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#define DEBUG_PRINT(var) Serial.print(var)
#else
#define DEBUG_PRINTLN(var)
#define DEBUG_PRINT(var)
#endif

// Sensor object
static SensorH_t config = {POT_PIN, POT_RESOLUTION};

static uint16_t pot_value;

void POT_init(void)
{
#if POT_ENABLED == STD_ON
    SensorH_Init(&config);
#endif
}

void POT_main(void)
{
#if POT_ENABLED == STD_ON
    pot_value = SensorH_ReadValue(config.channel);
    DEBUG_PRINT("POT Value: ");
    DEBUG_PRINTLN(pot_value);
    delay(1000);
#endif
}

uint16_t POT_value_Getter(void)
{
#if POT_ENABLED == STD_ON
    return pot_value;
#endif
}