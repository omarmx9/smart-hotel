#include <Arduino.h>
#include "HAL/MQTT/MQTT.h"
#include "HAL/WIFI/wifi.h"
#include "APP/Thermostat/Thermostat.h"
#include "App_cfg.h"



void setup() 
{
    Serial.begin(9600);
    delay(1000);
    
    Serial.println("Initializing...");

    // Configure WiFi
    WIFI_Config_t g_wifiCfg_cpy = {
        .ssid = WIFI_SSID,
        .password = WIFI_PASSWORD,
        .reconnect_interval_ms = 5000,
        .on_connect = onWifiConnected,
        .on_disconnect = onWifiDisconnected
    };

    // Initialize WiFi
    WIFI_Init_(&g_wifiCfg_cpy);
    
    Serial.println("WiFi initialization started");
    
    delay(2000);
    
    Serial.println("Thermostat hardware initialized");
    Serial.println("System ready!");


}

void loop() 
{
    WIFI_Process();

    if (WIFI_IsConnected() && mqttInitialized) 
    {
        MQTT_Loop();
        MQTT_PublishRandom();
        
    }

    

    
    delay(10);
}