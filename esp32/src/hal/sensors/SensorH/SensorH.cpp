#include <Arduino.h>
#include "../../../app_cfg.h"
#include "SensorH.h"

#if SENSORH_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

void SensorH_Init( SensorH_t  *config)
{
#if SENSORH_ENABLED == STD_ON

    DEBUG_PRINTLN("SensorH Initialized");
    DEBUG_PRINTLN("Channel: " + String(config->channel));
    DEBUG_PRINTLN("Resolution: " + String(config->resolution));
    analogReadResolution(config->resolution);

#endif
}

uint32_t SensorH_ReadValue(uint8_t channel)
{
#if SENSORH_ENABLED == STD_ON
    int rawValue = analogRead(channel);
    DEBUG_PRINTLN("Read Value from channel " + String(channel) + ": " + String(rawValue));
    return rawValue;
#endif
}