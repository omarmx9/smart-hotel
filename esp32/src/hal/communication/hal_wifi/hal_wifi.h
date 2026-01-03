#ifndef HAL_WIFI_H
#define HAL_WIFI_H

#include <stdint.h>
#include <stdbool.h>

#include <Arduino.h>
#include <WiFi.h>

extern bool mqttInitialized ;


typedef enum
{
    WIFI_STATUS_DISCONNECTED = 0,
    WIFI_STATUS_CONNECTING,
    WIFI_STATUS_CONNECTED,
    WIFI_STATUS_ERROR

} WIFI_Status_t;

typedef void (*WIFI_Callback_t)(void);

typedef struct
{
    const char *ssid;
    const char *password;
    uint32_t reconnect_interval_ms;
    WIFI_Callback_t on_connect;
    WIFI_Callback_t on_disconnect;

} WIFI_Config_t;

void WIFI_Init_(const WIFI_Config_t *config);
void WIFI_Process(void);
WIFI_Status_t WIFI_GetStatus(void);
bool WIFI_IsConnected(void);
int WIFI_GetRSSI(void);
uint32_t WIFI_GetIP_v4(void);

void WIFI_PrintConnectStatus(void);


void onWifiConnected(void);
void onWifiDisconnected(void);

#endif
