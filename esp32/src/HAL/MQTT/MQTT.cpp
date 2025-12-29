#include "MQTT.h"
#include <WiFi.h>
#include "../WIFI/wifi.h"
#include "App_cfg.h"
static WiFiClient wifiClient;
static PubSubClient mqttClient(wifiClient);



static const char* g_broker;
static int g_port;

static const char* mqtt_sub_topics[] =
{
    MQTT_TOPIC_TEMP,
    MQTT_TOPIC_HUMIDITY,
    MQTT_TOPIC_TARGET,
    MQTT_TOPIC_HEATING,
    MQTT_TOPIC_LUMINOSITY,
    MQTT_TOPIC_GAS,
    MQTT_TOPIC_CONTROL
};

void MQTT_SubscribeAll(void)
{
    for (uint8_t i = 0; i < (sizeof(mqtt_sub_topics) / sizeof(mqtt_sub_topics[0])); i++)
    {
        mqttClient.subscribe(mqtt_sub_topics[i]);
    }
}

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

void MQTT_PublishRandom(void)
{
    if (!WIFI_IsConnected())
        return;

    char payload[16];

    /* Temperature: 20.0 – 30.0 */
    float temp = 20.0f + ((float)rand() / RAND_MAX) * 10.0f;
    snprintf(payload, sizeof(payload), "%.2f", temp);
    mqttClient.publish(MQTT_TOPIC_TEMP, payload);

    /* Humidity: 40 – 80 % */
    int humidity = 40 + rand() % 41;
    snprintf(payload, sizeof(payload), "%d", humidity);
    mqttClient.publish(MQTT_TOPIC_HUMIDITY, payload);

    /* Target temperature: 22 – 26 */
    int target = 22 + rand() % 5;
    snprintf(payload, sizeof(payload), "%d", target);
    mqttClient.publish(MQTT_TOPIC_TARGET, payload);

    /* Heating: ON / OFF */
    int heating = rand() % 2;
    snprintf(payload, sizeof(payload), "%d", heating);
    mqttClient.publish(MQTT_TOPIC_HEATING, payload);

    /* Luminosity: 0 – 1023 */
    int luminosity = rand() % 1024;
    snprintf(payload, sizeof(payload), "%d", luminosity);
    mqttClient.publish(MQTT_TOPIC_LUMINOSITY, payload);

    /* Gas level: 0 – 100 % */
    int gas = rand() % 101;
    snprintf(payload, sizeof(payload), "%d", gas);
    mqttClient.publish(MQTT_TOPIC_GAS, payload);
    Serial.println("System ready!");

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
