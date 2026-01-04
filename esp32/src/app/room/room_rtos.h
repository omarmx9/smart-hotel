#ifndef ROOM_RTOS_H
#define ROOM_RTOS_H

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "room_types.h"

// Task priorities
#define ROOM_TASK_PRIORITY_HIGH     3
#define ROOM_TASK_PRIORITY_MEDIUM   2
#define ROOM_TASK_PRIORITY_LOW      1

// Task stack sizes
#define ROOM_TASK_STACK_SIZE_LARGE  4096
#define ROOM_TASK_STACK_SIZE_MEDIUM 3072
#define ROOM_TASK_STACK_SIZE_SMALL  2048

// Queue sizes
#define ROOM_MQTT_QUEUE_SIZE        10

// Task handles
extern TaskHandle_t room_sensor_task_handle;
extern TaskHandle_t room_control_task_handle;
extern TaskHandle_t room_mqtt_task_handle;
extern TaskHandle_t room_button_task_handle;

// Queue handles
extern QueueHandle_t room_mqtt_rx_queue;
extern QueueHandle_t room_mqtt_tx_queue;

// Mutex handles
extern SemaphoreHandle_t room_status_mutex;
extern SemaphoreHandle_t room_mutex;

// Initialization
void Room_RTOS_Init(void);

// Task functions
void Room_RTOS_SensorTask(void* parameter);
void Room_RTOS_ControlTask(void* parameter);
void Room_RTOS_ButtonTask(void* parameter);
void Room_RTOS_MQTTWarrper(void );
// Queue management
bool Room_RTOS_SendMQTTMessage(const Room_MQTTMessage_t* message);
bool Room_RTOS_ReceiveMQTTMessage(Room_MQTTMessage_t* message, uint32_t timeout_ms);

// Status publishing
void Room_RTOS_PublishLEDStatus(Room_LED_t led);
void Room_RTOS_PublishLDRData(void);
void Room_RTOS_PublishModeStatus(void);

#endif // ROOM_RTOS_H
