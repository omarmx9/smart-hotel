#include <Arduino.h>
#include "HAL/MQTT/MQTT.h"
#include "HAL/WIFI/wifi.h"
#include "APP/Thermostat/Thermostat.h"
#include "App_cfg.h"

bool thermostatInitialized = false;


void setup() 
{
    Serial.begin(9600);
    delay(1000);
    
    Serial.println("\n=== Smart Thermostat System ===");
    Serial.println("Initializing...");

    // Configure WiFi
    WIFI_Config_t g_wifiCfg_cpy = {
        .ssid = WIFI_SSID,
        .password = WIFI_SSID,
        .reconnect_interval_ms = 5000,
        .on_connect = onWifiConnected,
        .on_disconnect = onWifiDisconnected
    };

    // Initialize WiFi
    WIFI_Init_(&g_wifiCfg_cpy);
    
    Serial.println("WiFi initialization started");
    
    delay(2000);
    
    Thermostat_Init();
    thermostatInitialized = true;
    
    Serial.println("Thermostat hardware initialized");
    Serial.println("System ready!");


}

void loop() 
{
    WIFI_Process();

    if (WIFI_IsConnected() && mqttInitialized) 
    {
        MQTT_Loop();
        
        if (thermostatInitialized)
        {
            Thermostat_Process();
        }
    }
    
    static unsigned long lastStatus = 0;
    if (millis() - lastStatus > 10000) // Every 10 seconds
    {
        Serial.println("\n--- System Status ---");
        Serial.print("WiFi: ");
        Serial.println(WIFI_IsConnected() ? "Connected" : "Disconnected");
        Serial.print("MQTT: ");
        Serial.println(MQTT_IsConnected() ? "Connected" : "Disconnected");
        
        if (thermostatInitialized)
        {
            Thermostat_Status_t status = Thermostat_GetStatus();
            Serial.print("Temp: ");
            Serial.print(status.temperature, 1);
            Serial.print("°C | Target: ");
            Serial.print(status.target_temp, 1);
            Serial.print("°C | Humidity: ");
            Serial.print(status.humidity, 1);
            Serial.print("% | Fan: ");
            Serial.print(status.fan_speed);
            Serial.print(" | Heating: ");
            Serial.println(status.heating ? "ON" : "OFF");
        }
        
        lastStatus = millis();
    }
    
    delay(10);
}