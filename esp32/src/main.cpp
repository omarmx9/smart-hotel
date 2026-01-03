#include <Arduino.h>
#include "hal/communication/hal_mqtt/hal_mqtt.h"
#include "hal/communication/hal_wifi/hal_wifi.h"
#include "app/thermostat/thermostat_rtos.h"
#include "app_cfg.h"



void setup() 
{
    Serial.begin(9600);
    delay(1000);
    
    Serial.println("\n=== Smart Thermostat System ===");
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
    
    InitThermostat();

    Serial.println("System ready!");


    MQTT_SubscribeAll();

    vTaskDelete(NULL); //remove void loop() 

}

void loop() 
{    
}