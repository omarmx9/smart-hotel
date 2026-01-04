#ifndef ROOM_LOGIC_H
#define ROOM_LOGIC_H

#include "room_types.h"
#include "room_config.h"

// Initialization
void Room_Logic_Init(void);

// Mode Control
void Room_Logic_SetMode(Room_Mode_t mode);
Room_Mode_t Room_Logic_GetMode(void);
const char* Room_Logic_GetModeString(void);

// LED Control (only works in MANUAL mode)
void Room_Logic_SetLED(Room_LED_t led, Room_LED_State_t state, Room_ControlSource_t source);
void Room_Logic_ToggleLED(Room_LED_t led, Room_ControlSource_t source);
Room_LED_State_t Room_Logic_GetLEDState(Room_LED_t led);
uint8_t Room_Logic_GetLEDBrightness(Room_LED_t led);

// Auto-dimming (deprecated - use Room_Logic_SetMode instead)
void Room_Logic_SetAutoDimMode(Room_AutoDimMode_t mode);
Room_AutoDimMode_t Room_Logic_GetAutoDimMode(void);
void Room_Logic_UpdateAutoDimming(void);

// Auto Mode Control
void Room_Logic_UpdateAutoMode(void);

// LDR Processing
void Room_Logic_UpdateLDR(void);
uint16_t Room_Logic_GetLDRRaw(void);
uint16_t Room_Logic_GetLDRPercentage(void);

// Button Processing
void Room_Logic_ProcessButtons(void);

// MQTT Message Processing
void Room_Logic_ProcessMQTTMessage(const char* topic, const char* payload);

// Status
void Room_Logic_GetStatus(Room_Status_t* status);

#endif // ROOM_LOGIC_H
