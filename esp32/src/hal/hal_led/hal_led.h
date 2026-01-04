#ifndef HAL_LED_H
#define HAL_LED_H
#include <stdint.h>

void LED_init(uint8_t LED);
void LED_ON(uint8_t LED);
void LED_OFF(uint8_t LED);
void LED_Toggle(uint8_t LED);
#endif