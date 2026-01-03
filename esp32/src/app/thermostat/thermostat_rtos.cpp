#include "thermostat_rtos.h"
#include "thermostat_config.h"
#include "thermostat_types.h"
#include "thermostat_fan_control.h"

#include "../../hal/communication/hal_wifi/hal_wifi.h"
#include "../../hal/communication/hal_mqtt/hal_mqtt.h"
#include "../../hal/sensors/hal_dht/hal_dht.h"
#include "../../hal/sensors/hal_potentiometer/hal_potentiometer.h"
#include "../../app_cfg.h"


// ==================== NAMING CONVENTIONS ====================
// Functions:     PascalCase or camelCase (choose one)
// Variables:     camelCase for locals, g_camelCase for globals
// Constants:     UPPER_SNAKE_CASE
// Types/Enums:   PascalCase_t
// Task Handles:  camelCaseTaskHandle
// Queues:        camelCaseQueue
// Event Groups:  camelCaseEventGroup
// Macros:        UPPER_SNAKE_CASE


// ==================== TASK HANDLES ====================
TaskHandle_t tempSensorTaskHandle   = NULL;
TaskHandle_t userInputTaskHandle    = NULL;
TaskHandle_t fanControlTaskHandle   = NULL;
TaskHandle_t mqttPublishTaskHandle  = NULL;
TaskHandle_t wifiTaskHandle         = NULL;

// ==================== GLOBAL VARIABLES ====================
Thermostat_Status_t thermostat_values;

// ==================== RTOS OBJECTS ====================
EventGroupHandle_t thermostatEventGroup = NULL;
QueueHandle_t mqttPublishQueue = NULL;
SemaphoreHandle_t wifiConnectedSem = NULL;

// ==================== DEBUG STATISTICS ====================
#if DEBUG_ENABLED

TaskDebugStats_t g_tempSensorStats = {0};
TaskDebugStats_t g_userInputStats = {0};
TaskDebugStats_t g_fanControlStats = {0};
TaskDebugStats_t g_mqttStats = {0};
TaskDebugStats_t g_wifiStats = {0};
#endif

// ==================== DEBUG HELPER FUNCTIONS ====================
#if DEBUG_STACK_MONITOR
void Debug_PrintStackUsage(const char* taskName, TaskHandle_t handle, TaskDebugStats_t* stats) {
    if (handle != NULL) {
        UBaseType_t stackRemaining = uxTaskGetStackHighWaterMark(handle);
        
        // Update min stack remaining
        if (stats->minStackRemaining == 0 || stackRemaining < stats->minStackRemaining) {
            stats->minStackRemaining = stackRemaining;
        }
        
        Serial.printf("[STACK] %s: %u bytes free (min: %u)\n", 
                     taskName, stackRemaining * 4, stats->minStackRemaining * 4);
    }
}

void Debug_PrintAllStackUsage(void) {
    Serial.println("\n========== STACK USAGE REPORT ==========");
    Debug_PrintStackUsage("TempSensor", tempSensorTaskHandle, &g_tempSensorStats);
    Debug_PrintStackUsage("UserInput", userInputTaskHandle, &g_userInputStats);
    Debug_PrintStackUsage("FanControl", fanControlTaskHandle, &g_fanControlStats);
    Debug_PrintStackUsage("MQTT", mqttPublishTaskHandle, &g_mqttStats);
    Debug_PrintStackUsage("WiFi", wifiTaskHandle, &g_wifiStats);
    Serial.println("========================================\n");
}
#endif

#if DEBUG_QUEUE_STATUS
void Debug_PrintQueueStatus(void) {
    if (mqttPublishQueue != NULL) {
        UBaseType_t messagesWaiting = uxQueueMessagesWaiting(mqttPublishQueue);
        UBaseType_t spacesAvailable = uxQueueSpacesAvailable(mqttPublishQueue);
        Serial.printf("[QUEUE] MQTT Queue: %u/%u messages\n", 
                     messagesWaiting, messagesWaiting + spacesAvailable);
    }
}
#endif

void Debug_PrintSystemInfo(void) {
    Serial.println("\n========== SYSTEM INFORMATION ==========");
    Serial.printf("Free Heap: %u bytes\n", ESP.getFreeHeap());
    Serial.printf("Min Free Heap: %u bytes\n", ESP.getMinFreeHeap());
    Serial.printf("Heap Size: %u bytes\n", ESP.getHeapSize());
    
    #if DEBUG_STACK_MONITOR
    Debug_PrintAllStackUsage();
    #endif
    
    #if DEBUG_QUEUE_STATUS
    Debug_PrintQueueStatus();
    #endif
    
    Serial.println("========================================\n");
}

// ==================== EVENT HANDLER ====================
void thermostatMqttEventSet(void) {
    if (thermostatEventGroup != NULL) {
        xEventGroupSetBits(thermostatEventGroup, TARGET_FROM_MQTT_BIT);
        DEBUG_PRINT(MQTT, "Event set: TARGET_FROM_MQTT_BIT");
    }
}

void thermostatMqttModeEventSet(void) {
    if (thermostatEventGroup != NULL) {
        xEventGroupSetBits(thermostatEventGroup, MODE_UPDATED_BIT);
        DEBUG_PRINT(MQTT, "Event set: MODE_UPDATED_BIT");
    }
}

void thermostatMqttFanSpeedEventSet(void) {
    if (thermostatEventGroup != NULL) {
        xEventGroupSetBits(thermostatEventGroup, FAN_SPEED_UPDATED_BIT);
        DEBUG_PRINT(MQTT, "Event set: FAN_SPEED_UPDATED_BIT");
    }
}



// ==================== INITIALIZATION ====================
/**
 * @brief Initialize thermostat system and create all RTOS tasks
 * @note Call this once during system startup
 */
void InitThermostat(void) {
    DEBUG_PRINT(TEMP_SENSOR, "=== Initializing Thermostat ===");
    
    // Initialize hardware
    Thermostat_Init_Hardware();
    DEBUG_PRINT(TEMP_SENSOR, "✓ Hardware OK");
    
    // Create event group
    thermostatEventGroup = xEventGroupCreate();
    if (thermostatEventGroup == NULL) {
        Serial.println("[ERROR] Event group failed!");
        return;
    }
    
    // Init fan control mutex
    Thermostat_InitMutexes();
    
    // Create MQTT publish queue
    mqttPublishQueue = xQueueCreate(5, sizeof(mqtt_pub_msg_t));
    if (mqttPublishQueue == NULL) {
        Serial.println("[ERROR] MQTT queue failed!");
        return;
    }
    DEBUG_PRINT(MQTT, "✓ Queue created");
    
    // Create WiFi semaphore
    wifiConnectedSem = xSemaphoreCreateBinary();
    if (wifiConnectedSem == NULL) {
        Serial.println("[ERROR] Semaphore failed!");
        return;
    }
    DEBUG_PRINT(WIFI, "✓ Semaphore created");
    
    // Create tasks
    BaseType_t result;
    
    result = xTaskCreate(
        Task_TemperatureSensor,
        "TempSensor",
        TEMP_SENSOR_STACK_SIZE,
        NULL,
        TEMP_SENSOR_PRIORITY,
        &tempSensorTaskHandle
    );
    if (result != pdPASS) {
        Serial.println("[ERROR] Failed to create TempSensor task!");
        return;
    }
    DEBUG_PRINT(TEMP_SENSOR, "Task created (Stack: %d, Priority: %d)", 
                TEMP_SENSOR_STACK_SIZE, TEMP_SENSOR_PRIORITY);
    
    result = xTaskCreate(
        Task_UserInput,
        "UserInput",
        USER_INPUT_STACK_SIZE,
        NULL,
        USER_INPUT_PRIORITY,
        &userInputTaskHandle
    );
    if (result != pdPASS) {
        Serial.println("[ERROR] Failed to create UserInput task!");
        return;
    }
    DEBUG_PRINT(USER_INPUT, "Task created (Stack: %d, Priority: %d)", 
                USER_INPUT_STACK_SIZE, USER_INPUT_PRIORITY);
    
    result = xTaskCreate(
        Task_FanControl,
        "FanControl",
        FAN_CONTROL_STACK_SIZE,
        NULL,
        FAN_CONTROL_PRIORITY,
        &fanControlTaskHandle
    );
    if (result != pdPASS) {
        Serial.println("[ERROR] Failed to create FanControl task!");
        return;
    }
    DEBUG_PRINT(FAN_CONTROL, "Task created (Stack: %d, Priority: %d)", 
                FAN_CONTROL_STACK_SIZE, FAN_CONTROL_PRIORITY);
    
    result = xTaskCreate(
        Task_Mqtt,
        "MqttPublish",
        MQTT_STACK_SIZE,
        NULL,
        MQTT_PRIORITY,
        &mqttPublishTaskHandle
    );
    if (result != pdPASS) {
        Serial.println("[ERROR] Failed to create MQTT task!");
        return;
    }
    DEBUG_PRINT(MQTT, "Task created (Stack: %d, Priority: %d)", 
                MQTT_STACK_SIZE, MQTT_PRIORITY);
    
    result = xTaskCreate(
        Task_Wifi,
        "Wifi_Task",
        WIFI_STACK_SIZE,
        NULL,
        WIFI_PRIORITY,
        &wifiTaskHandle
    );
    if (result != pdPASS) {
        Serial.println("[ERROR] Failed to create WiFi task!");
        return;
    }
    DEBUG_PRINT(WIFI, "Task created (Stack: %d, Priority: %d)", 
                WIFI_STACK_SIZE, WIFI_PRIORITY);
    
    Serial.println("[INIT] ✓ All tasks ready\n");
}

// ==================== TASKS ====================

/**
 * @brief Task: Read temperature sensor periodically
 * @param pvParameters Unused
 */
void Task_TemperatureSensor(void* pvParameters) {
    (void)pvParameters;
    
    float temperature = INVALID_TEMP_VALUE;
    float last_temp = INVALID_TEMP_VALUE;
    mqtt_pub_msg_t msg;
    
    #if DEBUG_TIMING
    uint32_t startTime = 0;
    uint32_t executionTime = 0;
    #endif
    
    DEBUG_PRINT(TEMP_SENSOR, "Started");
    vTaskDelay(pdMS_TO_TICKS(1000));
    
    while (1) {
        #if DEBUG_TIMING
        startTime = millis();
        #endif
        
        #if DEBUG_ENABLED
        g_tempSensorStats.taskRunCount++;
        g_tempSensorStats.lastRunTime = millis();
        #endif
        
        // Read sensor (simulated with random for testing)
      //  temperature = random(1500, 3500) / 100.0f;  // Random 15-35°C
        
        DEBUG_PRINT(TEMP_SENSOR, "[%u] Temp=%.2f°C", g_tempSensorStats.taskRunCount, temperature);
        
        // Check if temperature changed significantly
        if (fabs(temperature - last_temp) >= TARGET_TEMP_THRESHOLD) {
            Thermostat_StoreTemp(temperature);
            last_temp = temperature;
            
            // Prepare MQTT message
            msg.type = MQTT_PUB_TEMP;
            msg.value = temperature;
            
            // Send to queue
            if (xQueueSend(mqttPublishQueue, &msg, pdMS_TO_TICKS(100)) == pdPASS) {
                DEBUG_PRINT(TEMP_SENSOR, "→ MQTT Queue");
            } else {
                DEBUG_PRINT(TEMP_SENSOR, "✗ Queue FULL");
            }
            
            // Signal fan control
            xEventGroupSetBits(thermostatEventGroup, TEMP_UPDATED_BIT);
        }
        

        
        #if DEBUG_STACK_MONITOR
        static uint32_t lastStackCheck = 0;
        if (millis() - lastStackCheck > STACK_MONITOR_INTERVAL_MS) {
            Debug_PrintStackUsage("TempSensor", tempSensorTaskHandle, &g_tempSensorStats);
            lastStackCheck = millis();
        }
        #endif
        
        vTaskDelay(pdMS_TO_TICKS(TEMP_SENSOR_SAMPLE_RATE_MS));
    }
}

/**
 * @brief Task: Read user input (potentiometer) for target temperature
 * @param pvParameters Unused
 */
void Task_UserInput(void* pvParameters) {
    (void)pvParameters;
    
    int pot_value = 0;
    float target_temp = INVALID_TEMP_VALUE;
    float last_target_temp = INVALID_TEMP_VALUE;
    mqtt_pub_msg_t msg;
    
    #if DEBUG_TIMING
    uint32_t startTime = 0;
    uint32_t executionTime = 0;
    #endif
    
    DEBUG_PRINT(USER_INPUT, "Started");
    vTaskDelay(pdMS_TO_TICKS(1500));
    
    while (1) {
        #if DEBUG_TIMING
        startTime = millis();
        #endif
        
        #if DEBUG_ENABLED
        g_userInputStats.taskRunCount++;
        g_userInputStats.lastRunTime = millis();
        #endif
        
        // Read potentiometer
        POT_main();
        pot_value = POT_value_Getter();
        target_temp = mapPotToTemp(pot_value);
        
        DEBUG_PRINT(USER_INPUT, "[%u] ADC=%d → %.1f°C", g_userInputStats.taskRunCount, pot_value, target_temp);
        
        // Check if target changed significantly
        if (fabs(target_temp - last_target_temp) >= TARGET_TEMP_THRESHOLD) {
            Thermostat_SetTargetTemp(target_temp);
            last_target_temp = target_temp;
            
            // Prepare MQTT message
            msg.type = MQTT_PUB_TARGET;
            msg.value = target_temp;
            
            // Send to queue
            if (xQueueSend(mqttPublishQueue, &msg, pdMS_TO_TICKS(100)) == pdPASS) {
                DEBUG_PRINT(USER_INPUT, "→ MQTT Queue");
            } else {
                DEBUG_PRINT(USER_INPUT, "✗ Queue FULL");
            }
            
            // Signal fan control
            xEventGroupSetBits(thermostatEventGroup, TARGET_UPDATED_BIT);
        }
        

        
        #if DEBUG_STACK_MONITOR
        static uint32_t lastStackCheck = 0;
        if (millis() - lastStackCheck > STACK_MONITOR_INTERVAL_MS) {
            Debug_PrintStackUsage("UserInput", userInputTaskHandle, &g_userInputStats);
            lastStackCheck = millis();
        }
        #endif
        
        vTaskDelay(pdMS_TO_TICKS(INPUT_SAMPLE_RATE_MS));
    }
}

/**
 * @brief Task: Control fan based on temperature difference
 * @param pvParameters Unused
 */
void Task_FanControl(void* pvParameters) {
    (void)pvParameters;
    
    float current_temp = INVALID_TEMP_VALUE;
    float target_temp = INVALID_TEMP_VALUE;
    bool temp_valid = false;
    bool target_valid = false;
    
    Thermostat_Mode_t current_mode = THERMOSTAT_MODE_OFF;
    Fan_Speed_t manual_fan_speed = FAN_SPEED_OFF;
    
    DEBUG_PRINT(FAN_CONTROL, "Started");
    
    while (1) {
        #if DEBUG_ENABLED
        g_fanControlStats.taskRunCount++;
        g_fanControlStats.lastRunTime = millis();
        #endif
        
        // Wait for any relevant event
        EventBits_t bits = xEventGroupWaitBits(
            thermostatEventGroup,
            TEMP_UPDATED_BIT | TARGET_UPDATED_BIT | TARGET_FROM_MQTT_BIT | 
            MODE_UPDATED_BIT | FAN_SPEED_UPDATED_BIT,
            pdTRUE,    // Clear bits after reading
            pdFALSE,   // Wait for ANY bit (not all)
            portMAX_DELAY
        );
        
        // Process temperature update
        if (bits & TEMP_UPDATED_BIT) {
            current_temp = Thermostat_GetTemp();
            temp_valid = true;
            DEBUG_PRINT(FAN_CONTROL, "Current: %.2f°C", current_temp);
        }
        
        // Process target temperature update (from POT)
        if (bits & TARGET_UPDATED_BIT) {
            target_temp = Thermostat_GetTargetTemp();
            target_valid = true;
            DEBUG_PRINT(FAN_CONTROL, "Target(POT): %.1f°C", target_temp);
        }
        
        // Process target temperature update (from MQTT)
        if (bits & TARGET_FROM_MQTT_BIT) {
            target_temp = Thermostat_GetTargetTemp();
            target_valid = true;
            DEBUG_PRINT(FAN_CONTROL, "Target(MQTT): %.1f°C", target_temp);
        }
        
        // Process mode change (from MQTT)
        if (bits & MODE_UPDATED_BIT) {
            current_mode = Thermostat_GetMode();
            const char* mode_str = (current_mode == THERMOSTAT_MODE_OFF) ? "OFF" :
                                   (current_mode == THERMOSTAT_MODE_AUTO) ? "AUTO" :
                                   (current_mode == THERMOSTAT_MODE_MANUAL) ? "MANUAL" : "UNKNOWN";
            DEBUG_PRINT(FAN_CONTROL, "Mode: %s", mode_str);
        }
        
        // Process manual fan speed update (from MQTT)
        if (bits & FAN_SPEED_UPDATED_BIT) {
            manual_fan_speed = Thermostat_GetFanSpeed();
            const char* speed_str = (manual_fan_speed == FAN_SPEED_OFF) ? "OFF" :
                                    (manual_fan_speed == FAN_SPEED_LOW) ? "LOW" :
                                    (manual_fan_speed == FAN_SPEED_MEDIUM) ? "MEDIUM" :
                                    (manual_fan_speed == FAN_SPEED_HIGH) ? "HIGH" : "UNKNOWN";
            DEBUG_PRINT(FAN_CONTROL, "Manual Speed: %s", speed_str);
        }
        
        // Execute fan control logic based on mode
        current_mode = Thermostat_GetMode();  // Always get latest mode
        
        switch (current_mode) {
            case THERMOSTAT_MODE_OFF:
                // Turn off fan
                DEBUG_PRINT(FAN_CONTROL, "[%u] Mode=OFF → Fan OFF", g_fanControlStats.taskRunCount);
                Thermostat_SetFanSpeed(FAN_SPEED_OFF);
                break;
            
            case THERMOSTAT_MODE_AUTO:
                // Run automatic logic based on temperature difference
                if (temp_valid && target_valid) {
                    float diff = target_temp - current_temp;
                    DEBUG_PRINT(FAN_CONTROL, "[%u] Mode=AUTO, Δ=%.2f°C → Auto Logic", 
                               g_fanControlStats.taskRunCount, diff);
                    Fan_Logic(target_temp, current_temp);
                } else {
                    DEBUG_PRINT(FAN_CONTROL, "[%u] Mode=AUTO but missing data (temp=%d, target=%d)",
                               g_fanControlStats.taskRunCount, temp_valid, target_valid);
                }
                break;
            
            case THERMOSTAT_MODE_MANUAL:
                // Use manually set fan speed
                manual_fan_speed = Thermostat_GetFanSpeed();
                DEBUG_PRINT(FAN_CONTROL, "[%u] Mode=MANUAL → Speed=%d", 
                           g_fanControlStats.taskRunCount, manual_fan_speed);
                Thermostat_SetFanSpeed(manual_fan_speed);
                break;
            
            default:
                DEBUG_PRINT(FAN_CONTROL, "✗ Unknown mode=%d", current_mode);
                break;
        }
        
        #if DEBUG_STACK_MONITOR
        static uint32_t lastStackCheck = 0;
        if (millis() - lastStackCheck > STACK_MONITOR_INTERVAL_MS) {
            Debug_PrintStackUsage("FanControl", fanControlTaskHandle, &g_fanControlStats);
            lastStackCheck = millis();
        }
        #endif
    }
}

/**
 * @brief Task: MQTT publish and listen to data from dashboard
 * @param pvParameters Unused
 */
void Task_Mqtt(void *pvParameters) {
    mqtt_pub_msg_t msg;
    char payload[16];
    
    DEBUG_PRINT(MQTT, "Started - Waiting WiFi");
    
    xSemaphoreTake(wifiConnectedSem, portMAX_DELAY);
    DEBUG_PRINT(MQTT, "✓ WiFi ready");
    
    for (;;) {
        #if DEBUG_ENABLED
        g_mqttStats.taskRunCount++;
        g_mqttStats.lastRunTime = millis();
        #endif
        
        if (WIFI_IsConnected() && mqttInitialized) {
            // Keep alive
            MQTT_Loop();

            static bool subscribed = false;
            if (!subscribed && MQTT_IsConnected())
            {
                MQTT_SubscribeTopics();
                subscribed = true;
            }

            // Check queue
            if (xQueueReceive(mqttPublishQueue, &msg, pdMS_TO_TICKS(200)) == pdTRUE) {
                switch (msg.type) {
                    case MQTT_PUB_TEMP:
                        snprintf(payload, sizeof(payload), "%.2f", msg.value);
                        MQTT_Publish(MQTT_TOPIC_TEMP, payload);
                        DEBUG_PRINT(MQTT, "Pub: temp=%s", payload);
                        break;
                    
                    case MQTT_PUB_TARGET:
                        snprintf(payload, sizeof(payload), "%.1f", msg.value);
                        MQTT_Publish(MQTT_TOPIC_TARGET, payload);
                        DEBUG_PRINT(MQTT, "Pub: target=%s", payload);
                        break;
                    
                    default:
                        DEBUG_PRINT(MQTT, "✗ Unknown type=%d", msg.type);
                        break;
                }
            }
        }
        
        #if DEBUG_STACK_MONITOR
        static uint32_t lastStackCheck = 0;
        if (millis() - lastStackCheck > STACK_MONITOR_INTERVAL_MS) {
            Debug_PrintStackUsage("MQTT", mqttPublishTaskHandle, &g_mqttStats);
            Debug_PrintQueueStatus();
            lastStackCheck = millis();
        }
        #endif
        
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

/**
 * @brief Task: WiFi connection management
 * @param pvParameters Unused
 */
void Task_Wifi(void *pvParameters) {
    static bool wasConnected = false;
    
    DEBUG_PRINT(WIFI, "Started");
    
    for (;;) {
        #if DEBUG_ENABLED
        g_wifiStats.taskRunCount++;
        g_wifiStats.lastRunTime = millis();
        #endif
        
        bool connected = WIFI_IsConnected();
        
        if (connected) {
            if (!wasConnected) {
                DEBUG_PRINT(WIFI, "✓ Connected");
                
                if (mqttPublishTaskHandle != NULL) {
                    xSemaphoreGive(wifiConnectedSem);
                    vTaskResume(mqttPublishTaskHandle);
                }
                wasConnected = true;
            }
        } else {
            if (wasConnected) {
                DEBUG_PRINT(WIFI, "✗ Disconnected");
                
                if (mqttPublishTaskHandle != NULL) {
                    vTaskSuspend(mqttPublishTaskHandle);
                }
                wasConnected = false;
            }
        }
        
        WIFI_Process();
        
        #if DEBUG_STACK_MONITOR
        static uint32_t lastStackCheck = 0;
        if (millis() - lastStackCheck > STACK_MONITOR_INTERVAL_MS) {
            Debug_PrintStackUsage("WiFi", wifiTaskHandle, &g_wifiStats);
            Debug_PrintSystemInfo();  // Print full system info periodically
            lastStackCheck = millis();
        }
        #endif
        
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}