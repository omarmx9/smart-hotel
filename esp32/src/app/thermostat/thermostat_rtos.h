#ifndef THERMOSTATRTOS_H
#define THERMOSTATRTOS_H

#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"


#define TARGET_TEMP_CHANGED_BIT (1 << 0)

// ======= Initialization =======
void InitThermostat();

// ======= Task Prototypes =======
void Task_TemperatureSensor(void* pvParameters);
void Task_UserInput(void* pvParameters);
void Task_FanControl(void* pvParameters);
void Task_Mqtt(void* pvParameters);
void Task_Wifi(void* pvParameters);

#endif
