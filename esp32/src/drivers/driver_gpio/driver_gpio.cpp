/**
 * @file driver_gpio.cpp
 * @brief Implementation of low-level GPIO driver
 */

#include <Arduino.h>
#include "driver_gpio.h"
#include "../../app_cfg.h"

// ==================== MACROS ====================

#if GPIO_DEBUG == STD_ON
    #define GPIO_DEBUG_LOG(msg) Serial.println(msg)
#else
    #define GPIO_DEBUG_LOG(msg) ((void)0)
#endif


// ==================== PUBLIC FUNCTIONS ====================

/**
 * @brief Initialize GPIO pin with specified mode
 */
void GPIO_PinInit(uint8_t pin_number, uint8_t pin_mode)
{
#if SENSORH_ENABLED == STD_ON
    GPIO_DEBUG_LOG("Pin" + String(pin_number) + "Initialized");
    pinMode(pin_number, pin_mode);
#endif
}

/**
 * @brief Write LOW to GPIO pin
 */
void GPIO_WritePin_Low(uint8_t pinNumber) {
#if GPIO_ENABLED == STD_ON
    digitalWrite(pinNumber, LOW);
    GPIO_DEBUG_LOG(String("GPIO Pin ") + String(pinNumber) + String(" -> LOW"));
#endif
}

/**
 * @brief Write HIGH to GPIO pin
 */
void GPIO_WritePin_High(uint8_t pinNumber) {
#if GPIO_ENABLED == STD_ON
    digitalWrite(pinNumber, HIGH);
    GPIO_DEBUG_LOG(String("GPIO Pin ") + String(pinNumber) + String(" -> HIGH"));
#endif
}

/**
 * @brief Write specific state to GPIO pin
 */
void GPIO_WritePin(uint8_t pinNumber, GPIO_State_t state) {
#if GPIO_ENABLED == STD_ON
    digitalWrite(pinNumber, (state == GPIO_STATE_HIGH) ? HIGH : LOW);
    GPIO_DEBUG_LOG(String("GPIO Pin ") + String(pinNumber) + 
                   String(" -> ") + String(state ? "HIGH" : "LOW"));
#endif
}

/**
 * @brief Read GPIO pin state
 */
GPIO_State_t GPIO_ReadPin(uint8_t pinNumber) {
#if GPIO_ENABLED == STD_ON
    int value = digitalRead(pinNumber);
    GPIO_DEBUG_LOG(String("GPIO Pin ") + String(pinNumber) + 
                   String(" read: ") + String(value));
    return (value == HIGH) ? GPIO_STATE_HIGH : GPIO_STATE_LOW;
#else
    return GPIO_STATE_LOW;
#endif
}

/**
 * @brief Toggle GPIO pin state
 */
void GPIO_TogglePin(uint8_t pinNumber) {
#if GPIO_ENABLED == STD_ON
    int currentState = digitalRead(pinNumber);
    int newState = !currentState;
    digitalWrite(pinNumber, newState);
    GPIO_DEBUG_LOG(String("GPIO Pin ") + String(pinNumber) + 
                   String(" toggled: ") + String(currentState) + 
                   String(" -> ") + String(newState));
#endif
}

