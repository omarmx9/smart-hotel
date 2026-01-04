/**
 * @file driver_gpio.h
 * @brief Low-level GPIO driver for Arduino platform
 * @author Your Team
 * @date 2025-01-15
 * 
 * @note This is a driver layer - minimal abstraction over hardware
 */

#ifndef DRIVER_GPIO_H
#define DRIVER_GPIO_H

#include <stdint.h>
#include <stdbool.h>

// ==================== TYPE DEFINITIONS ====================

/**
 * @brief GPIO pin modes
 */
typedef enum
{
    GPIO_INPUT = 0,
    GPIO_INPUT_PULLUP,
    GPIO_OUTPUT
} GPIO_ModeType_t_;


/**
 * @brief GPIO pin states
 */
typedef enum {
    GPIO_STATE_LOW = 0,         ///< Logic level 0
    GPIO_STATE_HIGH = 1         ///< Logic level 1
} GPIO_State_t;

// ==================== FUNCTION PROTOTYPES ====================

/**
 * @brief Initialize a GPIO pin with specified mode
 * @param pinNumber Pin number (0-255)
 * @param pinMode Pin mode (INPUT, INPUT_PULLUP, OUTPUT)
 * @return true if successful, false otherwise
 */
void GPIO_PinInit(uint8_t pinNumber, uint8_t pinMode);

/**
 * @brief Set GPIO pin to LOW state
 * @param pinNumber Pin number to write
 */
void GPIO_WritePin_Low(uint8_t pinNumber);

/**
 * @brief Set GPIO pin to HIGH state
 * @param pinNumber Pin number to write
 */
void GPIO_WritePin_High(uint8_t pinNumber);

/**
 * @brief Write specific state to GPIO pin
 * @param pinNumber Pin number to write
 * @param state State to write (GPIO_STATE_LOW or GPIO_STATE_HIGH)
 */
void GPIO_WritePin(uint8_t pinNumber, GPIO_State_t state);

/**
 * @brief Read current state of GPIO pin
 * @param pinNumber Pin number to read
 * @return GPIO_STATE_HIGH or GPIO_STATE_LOW
 */
GPIO_State_t GPIO_ReadPin(uint8_t pinNumber);

/**
 * @brief Toggle GPIO pin state (LOW->HIGH or HIGH->LOW)
 * @param pinNumber Pin number to toggle
 */
void GPIO_TogglePin(uint8_t pinNumber);

#endif // DRIVER_GPIO_H