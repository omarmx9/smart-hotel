/**
 * @file hal_led.h
 * @brief Hardware Abstraction Layer - LED Control
 * 
 * LED control and visual feedback
 */

#ifndef HAL_LED_H
#define HAL_LED_H

namespace hal {

/**
 * @brief Initialize LED GPIO
 */
void ledInit();

/**
 * @brief Turn LED on
 */
void ledOn();

/**
 * @brief Turn LED off
 */
void ledOff();

/**
 * @brief Flash LED briefly for visual feedback
 * @param durationMs Flash duration in milliseconds
 */
void ledFlash(int durationMs = 50);

}  // namespace hal

#endif // HAL_LED_H
