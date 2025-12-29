#ifndef MQTT_H
#define MQTT_H

#include <PubSubClient.h>

// Make mqttClient accessible to other modules (if needed)

void MQTT_Init(const char* broker, int port);
void MQTT_Loop(void);
void MQTT_SubscribeAll(void);
void MQTT_Publish(const char* topic, const char* payload);  // ← Make sure this line exists
bool MQTT_IsConnected(void);
void MQTT_PublishRandom(void);

#endif // MQTT_H