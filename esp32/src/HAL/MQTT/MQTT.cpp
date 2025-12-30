#include "MQTT.h"
#include <WiFi.h>
#include "../WIFI/wifi.h"

static WiFiClient wifiClient;
static PubSubClient mqttClient(wifiClient);

static const char* g_broker;
static int g_port;

static void MQTT_Reconnect(void);

static void mqttCallback(char* topic, byte* payload, unsigned int length)
{
    char buffer[32];
    if (length >= sizeof(buffer)) length = sizeof(buffer) - 1;
    for (unsigned int i = 0; i < length; i++) buffer[i] = (char)payload[i];
    buffer[length] = '\0';
}

void MQTT_Init(const char* broker, int port)
{
    g_broker = broker;
    g_port = port;

    mqttClient.setServer(g_broker, g_port);
    mqttClient.setCallback(mqttCallback);
}

void MQTT_Loop(void)
{
    // Only try MQTT if WiFi is connected
    if (WIFI_IsConnected())
    {
        if (!mqttClient.connected()) MQTT_Reconnect();
        mqttClient.loop();
    }
}

void MQTT_SubscribeAll(void)
{
    mqttClient.subscribe("home/thermostat/temperature");
    mqttClient.subscribe("home/thermostat/humidity");
    mqttClient.subscribe("home/thermostat/target");
    mqttClient.subscribe("home/thermostat/heating");
    mqttClient.subscribe("home/thermostat/distance");
    mqttClient.subscribe("home/thermostat/pot");
    mqttClient.subscribe("home/thermostat/control");
}


void MQTT_Publish(const char* topic, const char* payload)
{
    if (!WIFI_IsConnected() || !mqttClient.connected()) 
    {
        Serial.println("MQTT publish failed: Not connected");
        return;
    }
    
    if (mqttClient.publish(topic, payload))
    {
        Serial.print("Published to ");
        Serial.print(topic);
        Serial.print(": ");
        Serial.println(payload);
    }
    else
    {
        Serial.println("MQTT publish failed");
    }
}

void MQTT_PublishStatic(void)
{
    if (!WIFI_IsConnected()) return;

    mqttClient.publish("home/thermostat/temperature", "25.5");
    mqttClient.publish("home/thermostat/humidity", "60.2");
    mqttClient.publish("home/thermostat/distance", "120");
    mqttClient.publish("home/thermostat/pot", "512");
    mqttClient.publish("home/thermostat/target", "24");
    mqttClient.publish("home/thermostat/heating", "0");
}

bool MQTT_IsConnected(void)
{
    return mqttClient.connected();
}

static void MQTT_Reconnect(void)
{
    while (!mqttClient.connected())
    {
        if (!WIFI_IsConnected())
        {
            delay(1000); // Wait until WiFi reconnects
            continue;
        }

        String id = "ESP32-" + String(random(0xffff), HEX);
        if (mqttClient.connect(id.c_str()))
        {
            MQTT_SubscribeAll();
        }
        else
        {
            delay(2000);
        }
    }
}
