#include <Arduino.h>
#include "../../App_cfg.h"
#include "../../MCAL/GPIO/gpio.h"
#include "LED.h"

#if LED_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

void LED_init(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    GPIO_PinInit(LED, OUTPUT);
    DEBUG_PRINTLN("Iint LED" + String(LED));
#endif
}
void LED_ON(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    write_pin_high(LED);
    DEBUG_PRINTLN("LED HIGH");
#endif
}
void LED_OFF(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    write_pin_Low(LED);
    DEBUG_PRINTLN("LED LOW");
#endif
}
void LED_Toggle(uint8_t LED)
{
#if LED_ENABLED == STD_ON
    Toggle(LED);
    DEBUG_PRINTLN("LED Toggle");
#endif
}