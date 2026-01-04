#include "helpers.h"
// ============================================================================
// Helper Function: Parse Room Mode from String
// ============================================================================
Room_Mode_t Room_Logic_ParseMode(const char* payload)
{
    // Check for OFF mode
    if (strcasecmp(payload, "OFF") == 0 || 
        strcmp(payload, "0") == 0) {
        return ROOM_MODE_OFF;
    }
    // Check for MANUAL mode
    else if (strcasecmp(payload, "MANUAL") == 0 || 
             strcmp(payload, "1") == 0 ||
             strcasecmp(payload, "MAN") == 0) {
        return ROOM_MODE_MANUAL;
    }
    // Check for AUTO mode
    else if (strcasecmp(payload, "AUTO") == 0 || 
             strcmp(payload, "2") == 0 ||
             strcasecmp(payload, "AUTOMATIC") == 0) {
        return ROOM_MODE_AUTO;
    }
    
    // Invalid command
    return (Room_Mode_t)0xFF;
}

// ============================================================================
// Helper Function: Parse LED State from String
// ============================================================================
Room_LED_State_t Room_Logic_ParseLEDState(const char* payload)
{
    // Check for ON commands
    if (strcmp(payload, "ON") == 0 || 
        strcmp(payload, "1") == 0 || 
        strcasecmp(payload, "true") == 0 ||
        strcasecmp(payload, "yes") == 0) {
        return ROOM_LED_ON;
    }
    // Check for OFF commands
    else if (strcmp(payload, "OFF") == 0 || 
             strcmp(payload, "0") == 0 || 
             strcasecmp(payload, "false") == 0 ||
             strcasecmp(payload, "no") == 0) {
        return ROOM_LED_OFF;
    }
    
    // Invalid command
    return (Room_LED_State_t)0xFF;
}

// ============================================================================
// Helper Function: Parse Auto-Dim Mode from String
// ============================================================================
Room_AutoDimMode_t Room_Logic_ParseAutoDimMode(const char* payload)
{
    // Check for ENABLED commands
    if (strcmp(payload, "ON") == 0 || 
        strcmp(payload, "1") == 0 || 
        strcasecmp(payload, "ENABLED") == 0 ||
        strcasecmp(payload, "ENABLE") == 0 ||
        strcasecmp(payload, "true") == 0 ||
        strcasecmp(payload, "yes") == 0) {
        return ROOM_AUTO_DIM_ENABLED;
    }
    // Check for DISABLED commands
    else if (strcmp(payload, "OFF") == 0 || 
             strcmp(payload, "0") == 0 || 
             strcasecmp(payload, "DISABLED") == 0 ||
             strcasecmp(payload, "DISABLE") == 0 ||
             strcasecmp(payload, "false") == 0 ||
             strcasecmp(payload, "no") == 0) {
        return ROOM_AUTO_DIM_DISABLED;
    }
    
    // Invalid command
    return (Room_AutoDimMode_t)0xFF;
}
