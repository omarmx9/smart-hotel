#ifndef HAL_MQTT_H
#define HAL_MQTT_H

#include <PubSubClient.h>

// Make mqttClient accessible to other modules (if needed)
typedef enum {
    MQTT_PUB_TEMP,
    MQTT_PUB_TARGET,
    MQTT_PUB_HUM

} mqtt_pub_type_t;

typedef struct {
    mqtt_pub_type_t type;
    float value;
} mqtt_pub_msg_t;

void MQTT_Init(const char* broker, int port);
void MQTT_Task_Init(void);
void MQTT_SubscribeTopics(void);
void MQTT_Loop(void);
void MQTT_SubscribeAll(void);
void MQTT_Publish(const char* topic, const char* payload);  // ← Make sure this line exists
bool MQTT_IsConnected(void);

#endif // MQTT_H