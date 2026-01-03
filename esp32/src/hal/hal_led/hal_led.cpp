#include <Arduino.h>
#include "../../app_cfg.h"
#include "../../drivers/driver_gpio/driver_gpio.h"
#include "hal_led.h"

#if LED_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

void LED_init(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    GPIO_PinInit(LED, GPIO_OUTPUT);
    DEBUG_PRINTLN("Iint LED" + String(LED));
#endif
}
void LED_ON(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    GPIO_WritePin_High(LED);
    DEBUG_PRINTLN("LED HIGH");
#endif
}
void LED_OFF(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    GPIO_WritePin_Low(LED);
    DEBUG_PRINTLN("LED LOW");
#endif
}
void LED_Toggle(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    GPIO_TogglePin(LED);
    DEBUG_PRINTLN("LED Toggle");
#endif
}