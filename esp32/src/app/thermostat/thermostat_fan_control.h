#ifndef THERMOSTAT_FAN_CONTROL_H
#define THERMOSTAT_FAN_CONTROL_H

#include <stdint.h>
#include "thermostat_types.h"
// Thermostat modes

// API Functions
void Thermostat_Init_Hardware(void);
void Thermostat_InitMutexes(void);

void Thermostat_Process(void);

void Thermostat_SetMode(Thermostat_Mode_t mode);
Thermostat_Mode_t Thermostat_GetMode(void);

void Thermostat_SetFanSpeed(Fan_Speed_t speed);
Fan_Speed_t Thermostat_GetFanSpeed (void);

bool Thermostat_SetTargetTemp(float temp);
float Thermostat_GetTargetTemp(void);

void Thermostat_StoreTemp(float temp);
float Thermostat_GetTemp(void);

void Fan_Logic (float target_temp, float current_temp);
Thermostat_Status_t Thermostat_GetStatus(void);
void Thermostat_PublishData(void);

void thermostatMqttFanSpeedEventSet(void) ;
void thermostatMqttEventSet();
void thermostatMqttModeEventSet(void) ;

float mapPotToTemp(uint16_t pot_value);

#endif // THERMOSTAT_H