#include <Arduino.h>
#include "../../../app_cfg.h"
#include "../SensorH/SensorH.h"
#include "hal_mq5.h"

#if MQ5_1_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#define DEBUG_PRINT(var) Serial.print(var)
#else
#define DEBUG_PRINTLN(var)
#define DEBUG_PRINT(var)
#endif

// Sensor object
static  SensorH_t config = {MQ5_PIN, ADC_RESOLUTION};

static uint16_t MQ5_value;
static uint16_t outputValue;
void MQ5_1_init(void)
{
#if MQ5_1_ENABLED == STD_ON
    SensorH_Init(&config);
#endif
}

void MQ5_1_main(void)
{
#if  MQ5_1_ENABLED == STD_ON
    static unsigned long lastReadTime = 0;
    const unsigned long READ_INTERVAL = 1000;
    
    if (millis() - lastReadTime >= READ_INTERVAL) {
        lastReadTime = millis();
        MQ5_value = SensorH_ReadValue(config.channel);
        MQ5_value = constrain(MQ5_value, MQ5_MIN_RAW, MQ5_MAX_RAW);
        outputValue = map(MQ5_value, MQ5_MIN_RAW, MQ5_MAX_RAW, 
                  MQ5_MIN_MAPPED, MQ5_MAX_MAPPED);
        DEBUG_PRINT("MQ5 Value: ");
        DEBUG_PRINTLN(outputValue);
    }
#endif
}

uint16_t MQ5_1_value(void)
{
#if MQ5_1_ENABLED == STD_ON
    return outputValue;
    #else
    return 0xFFFF;  // Indicate error if MQ5_1 is disabled
#endif
}