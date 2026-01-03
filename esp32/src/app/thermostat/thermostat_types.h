
#ifndef THERMOSTAT_TYPES_H
#define THERMOSTAT_TYPES_H

#include "thermostat_config.h"
// ======= Enums =======
typedef enum {
    THERMOSTAT_MODE_OFF = 0,
    THERMOSTAT_MODE_AUTO,
    THERMOSTAT_MODE_MANUAL
} Thermostat_Mode_t;

// Fan speeds
typedef enum {
    FAN_SPEED_OFF = 0,
    FAN_SPEED_LOW,
    FAN_SPEED_MEDIUM,
    FAN_SPEED_HIGH
} Fan_Speed_t;

// Thermostat status structure
typedef struct {
    float temperature;      // Current temperature (from POT1)
    float humidity;         // Current humidity (from POT2)
    float target_temp;      // Target temperature (from POT3)
    Fan_Speed_t fan_speed;  // Current fan speed
    Thermostat_Mode_t mode; // Operating mode
    bool heating;           // Heating status
} Thermostat_Status_t;

#if DEBUG_ENABLED
typedef struct {
    uint32_t taskRunCount;
    uint32_t lastRunTime;
    uint32_t minStackRemaining;
} TaskDebugStats_t;

#endif

#endif