#include <Arduino.h>
#include <WiFi.h>
#include "../../App_cfg.h"
#include "wifi.h"
#include "../MQTT/MQTT.h"

#if WIFI_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif


bool mqttInitialized = false;

void onWifiConnected(void)
{
    Serial.println("WiFi Connected! IP: " + WiFi.localIP().toString());
    
    // Initialize MQTT only when WiFi is connected
    if (!mqttInitialized) {
        MQTT_Init("broker.hivemq.com", 1883);
        mqttInitialized = true;
    }
}

void onWifiDisconnected(void)
{
    Serial.println("WiFi Disconnected!");   
}


static WIFI_Config_t g_wifiCfg = {
    .ssid = WIFI_SSID,
    .password = WIFI_SSID,
    .reconnect_interval_ms = 5000,
    .on_connect = NULL,  // Change these to NULL
    .on_disconnect = NULL
};

static WIFI_Status_t g_wifiStatus = WIFI_STATUS_DISCONNECTED;
static unsigned long g_lastReconnectAttempt = 0;
static unsigned long g_connectStartTime = 0;

#define WIFI_CONNECT_TIMEOUT_MS 15000

static void WIFI_StartConnection(void)
{
    if (g_wifiCfg.ssid == NULL || g_wifiCfg.password == NULL)
    {
        g_wifiStatus = WIFI_STATUS_ERROR;
        return;
    }

    WiFi.disconnect(false, false);
    delay(100);

    WiFi.mode(WIFI_STA);
    WiFi.begin(g_wifiCfg.ssid, g_wifiCfg.password);
    g_wifiStatus = WIFI_STATUS_CONNECTING;
    g_connectStartTime = millis();
}

void WIFI_Init_(const WIFI_Config_t *config)
{
    g_wifiCfg = *config;
    g_lastReconnectAttempt = millis();
    WIFI_StartConnection();
}

void WIFI_Process(void)
{
    wl_status_t st = WiFi.status();

    switch (g_wifiStatus)
    {
    case WIFI_STATUS_CONNECTING:
        if (st == WL_CONNECTED)
        {
            delay(500);
            
            if (WiFi.status() == WL_CONNECTED) {
                g_wifiStatus = WIFI_STATUS_CONNECTED;
                Serial.print("WiFi connected! IP: ");
                Serial.println(WiFi.localIP());
                
                if (g_wifiCfg.on_connect)
                    g_wifiCfg.on_connect();
            }
        }
        else if (st == WL_CONNECT_FAILED ||
                 st == WL_NO_SSID_AVAIL)
        {
            g_wifiStatus = WIFI_STATUS_DISCONNECTED;
            g_lastReconnectAttempt = millis();
        }
        else if (millis() - g_connectStartTime >= WIFI_CONNECT_TIMEOUT_MS)
        {
            DEBUG_PRINTLN("WiFi connection timeout");
            WiFi.disconnect(false, false);
            g_wifiStatus = WIFI_STATUS_DISCONNECTED;
            g_lastReconnectAttempt = millis();
        }
        break;

    case WIFI_STATUS_CONNECTED:
        if (st != WL_CONNECTED)
        {
            g_wifiStatus = WIFI_STATUS_DISCONNECTED;
            Serial.println("WiFi disconnected!");
            
            if (g_wifiCfg.on_disconnect)
                g_wifiCfg.on_disconnect();
            g_lastReconnectAttempt = millis();
        }
        break;

    case WIFI_STATUS_DISCONNECTED:
        if (millis() - g_lastReconnectAttempt >= g_wifiCfg.reconnect_interval_ms)
        {
            Serial.println("Attempting to reconnect WiFi...");
            WIFI_StartConnection();
            g_lastReconnectAttempt = millis();
        }
        break;

    case WIFI_STATUS_ERROR:
    default:
        break;
    }
}

WIFI_Status_t WIFI_GetStatus(void)
{
    return g_wifiStatus;
}

bool WIFI_IsConnected(void)
{
    return (g_wifiStatus == WIFI_STATUS_CONNECTED);
}

int WIFI_GetRSSI(void)
{
    if (WiFi.status() == WL_CONNECTED)
        return WiFi.RSSI();
    return 0;
}