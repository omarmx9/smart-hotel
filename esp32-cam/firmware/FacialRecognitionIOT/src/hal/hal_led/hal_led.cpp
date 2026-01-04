/**
 * @file hal_led.cpp
 * @brief Hardware Abstraction Layer - LED Implementation
 */

#include "hal_led.h"
#include "../../app_cfg.h"
#include <Arduino.h>

namespace hal {

void ledInit() {
#if defined(LED_GPIO_NUM)
    pinMode(LED_GPIO_NUM, OUTPUT);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
}

void ledOn() {
#if defined(LED_GPIO_NUM)
    digitalWrite(LED_GPIO_NUM, HIGH);
#endif
}

void ledOff() {
#if defined(LED_GPIO_NUM)
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
}

void ledFlash(int durationMs) {
#if defined(LED_GPIO_NUM)
    digitalWrite(LED_GPIO_NUM, HIGH);
    delay(durationMs);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
}

}  // namespace hal
