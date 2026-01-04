/**
 * @file hal_mqtt.h
 * @brief Hardware Abstraction Layer - MQTT Communication
 * 
 * Low-level MQTT connection and publish operations
 */

#ifndef HAL_MQTT_H
#define HAL_MQTT_H

#include <Arduino.h>

namespace hal {

/**
 * @brief Initialize MQTT connection
 * @return true if connected to broker
 */
bool mqttInit();

/**
 * @brief Check if connected to MQTT broker
 * @return true if connected
 */
bool mqttIsConnected();

/**
 * @brief Reconnect to MQTT broker
 * @return true if reconnection successful
 */
bool mqttReconnect();

/**
 * @brief Publish message to topic
 * @param topic MQTT topic
 * @param payload Message payload
 * @return true on success
 */
bool mqttPublish(const char* topic, const char* payload);

/**
 * @brief Subscribe to topic (optional for future features)
 * @param topic MQTT topic
 * @return true on success
 */
bool mqttSubscribe(const char* topic);

/**
 * @brief Process MQTT events (keep-alive, callbacks)
 */
void mqttProcess();

/**
 * @brief Cleanup MQTT resources
 */
void mqttCleanup();

}  // namespace hal

#endif // HAL_MQTT_H
