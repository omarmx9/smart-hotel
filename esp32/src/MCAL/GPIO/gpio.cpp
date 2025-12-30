#include <Arduino.h>
#include "gpio.h"
#include "../../App_cfg.h"

#if GPIO_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

/* this function to ConfigerAPP_cfg
  1-pin mode : 1.GPIO_INPUT
             2.GPIO_INPUT_PULLUP
             3.GPIO_OUTPUT

  2-Pin States : 1.GPIO_LOW
                 2. GPIO_HIGH

*/
void GPIO_PinInit(uint8_t pin_number, uint8_t pin_mode)
{
#if SENSORH_ENABLED == STD_ON
    DEBUG_PRINTLN("Pin" + String(pin_number) + "Initialized");
    pinMode(pin_number, pin_mode);
#endif
}
/*
this function to write Pin States : GPIO_LOW
*/
void write_pin_Low(uint8_t pin_number)
{
#if SENSORH_ENABLED == STD_ON
    DEBUG_PRINTLN("Write LOW On Pin" + String(pin_number));
    digitalWrite(pin_number, LOW);
#endif
}
/*
this function to write Pin States : GPIO_HIGH
*/
void write_pin_high(uint8_t pin_number)
{
#if SENSORH_ENABLED == STD_ON
    DEBUG_PRINTLN("Writr HIGH On Pin " + String(pin_number));
    digitalWrite(pin_number, HIGH);
#endif
}
/*
this function to get Pin value
*/
int read_pin(uint8_t pin_number)
{
#if SENSORH_ENABLED == STD_ON
    DEBUG_PRINTLN("Read Pin" + String(pin_number));
    return (digitalRead(pin_number) == HIGH ? HIGH : LOW);
#endif
}
/*
this function to toggle pin value
*/
void Toggle(uint8_t pin_number)
{
#if SENSORH_ENABLED == STD_ON
    DEBUG_PRINTLN("Toggle Pin" + String(pin_number));
    digitalWrite(pin_number, !(digitalRead(pin_number)));
#endif
}
