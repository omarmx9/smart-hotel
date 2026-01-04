#ifndef HELPERS_H
#define HELPERS_H

/* ============================================================================
 * Includes
 * ============================================================================
 */
#include <stdint.h>
#include "hal_mqtt.h"
#include <WiFi.h>
#include "../hal_wifi/hal_wifi.h"
#include "../../../app/thermostat/thermostat_fan_control.h"
#include "../../../app_cfg.h"
#include "../../../app/room/room_config.h"
#include "../../../app/room/room_types.h"
#include "../../../app/room/room_logic.h"
#include "../../../app/room/room_rtos.h"

/* ============================================================================
 * Enums
 * ============================================================================
 */


/* ============================================================================
 * Function Prototypes
 * ============================================================================
 */

/**
 * @brief Parse room mode from string payload
 * @param payload Null-terminated string
 * @return Room_Mode_t or 0xFF if invalid
 */
Room_Mode_t Room_Logic_ParseMode(const char* payload);

/**
 * @brief Parse LED state from string payload
 * @param payload Null-terminated string
 * @return Room_LED_State_t or 0xFF if invalid
 */
Room_LED_State_t Room_Logic_ParseLEDState(const char* payload);

/**
 * @brief Parse auto-dimming mode from string payload
 * @param payload Null-terminated string
 * @return Room_AutoDimMode_t or 0xFF if invalid
 */
Room_AutoDimMode_t Room_Logic_ParseAutoDimMode(const char* payload);


#endif /* HELPERS_H */
