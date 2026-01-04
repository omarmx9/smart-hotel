#include <Arduino.h>
#include "../../../app_cfg.h"
#include "../SensorH/SensorH.h"
#include "hal_ldr.h"

#if LDR_1_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#define DEBUG_PRINT(var) Serial.print(var)
#else
#define DEBUG_PRINTLN(var)
#define DEBUG_PRINT(var)
#endif

// Sensor configuration
static  SensorH_t config = {LDR_PIN, ADC_RESOLUTION};
// Sensor data
static uint16_t rawLdrValue;
static uint16_t lightPercentage;

void LDR_1_init(void)
{
#if LDR_1_ENABLED == STD_ON
    SensorH_Init(&config);
#endif
}

void LDR_1_main(void)
{
#if LDR_1_ENABLED == STD_ON
    static unsigned long lastReadTime = 0;
    const unsigned long READ_INTERVAL = 100; // 100ms for LDR (faster than gas sensor)
    
    if (millis() - lastReadTime >= READ_INTERVAL) {
        lastReadTime = millis();
        
        rawLdrValue = SensorH_ReadValue(config.channel);
        rawLdrValue = constrain(rawLdrValue, ADC_MIN_RAW, ADC_MAX_RAW);
        
        // Map to percentage (0-100%) or keep raw value
        lightPercentage = map(rawLdrValue, ADC_MIN_RAW, ADC_MAX_RAW, 0, 100);

        DEBUG_PRINT("LDR Raw: ");
        DEBUG_PRINT(rawLdrValue);
        DEBUG_PRINT(" | Light %: ");
        DEBUG_PRINTLN(lightPercentage);
    }
#endif
}

uint16_t LDR_1_getRawValue(void)
{
#if LDR_1_ENABLED == STD_ON
    return rawLdrValue;
#else
    return 0xFFFF; // Indicate error if LDR_1 is disabled
#endif
}

uint16_t LDR_1_getAveragedValue(void)
{
    uint32_t sum = 0;
    for (uint8_t i = 0; i < LDR_SAMPLE_COUNT; i++) {
        sum += SensorH_ReadValue(config.channel);
        delay(10);
    }
    return sum / LDR_SAMPLE_COUNT;
}

float LDR_1_calculateLux(void)
{
    // This is a simplified example - calibration required
    float voltage = (rawLdrValue * voltage) / ADC_MAX_RAW;
    // Add your lux calculation formula here
    return 0.0; // Placeholder
}

uint16_t LDR_1_getLightPercentage(void)
{
#if LDR_1_ENABLED == STD_ON
    return lightPercentage;
#else
    return 0xFFFF; // Indicate error if LDR_1 is disabled
#endif
}