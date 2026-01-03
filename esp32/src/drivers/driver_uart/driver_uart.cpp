#include "Arduino.h"
#include "../../app_cfg.h"
#include "driver_uart.h"
//#include <String.h>

#if UART_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

static UART_t UART[UART_MAXLENGH] = {{UART_BAUD_RATE, UART_FRAME_LENGTH, UART_TX_PIN, UART_RX_PIN}};
static HardwareSerial myserial[UART_MAXLENGH] = {Serial1, Serial2};

void UART_Init(void)
{
#if UART_ENABLED == STD_ON
    for (uint8_t i; i < UART_MAXLENGH; i++)
    {
        myserial[i].begin(UART[i].buadRate, UART[i].FrameLength, UART[i].RXPin, UART[i].TXPin);
        DEBUG_PRINTLN("UART" + String(i) + " initialize");
    }
#endif
}

void UART_Send_Data(UARTN_t uart_n, String payload)
{
#if UART_ENABLED == STD_ON
    if (myserial[uart_n].available())
    {
        myserial[uart_n].println(payload);
        DEBUG_PRINTLN("UART send" + String(payload));
    }
#endif
}
void UART_Receive_Data(UARTN_t uart_n, String &payload)
{
#if UART_ENABLED == STD_ON
    if (myserial[uart_n].available())
    {
        Serial1.print(payload);
        payload = myserial[uart_n].readStringUntil('\n');
        DEBUG_PRINTLN("UART receive" + String(payload));
    }
#endif
}



void UART_getSerial(HardwareSerial&serial,UARTN_t uart)
{
    serial = myserial[uart];
}
