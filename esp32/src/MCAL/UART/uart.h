#ifndef UART_H
#define UART_H

#include <stdint.h>

typedef enum
{
    UART1,
    UART2,
    UART_MAXLENGH
} UARTN_t;

typedef struct
{
    uint32_t buadRate;
    uint32_t FrameLength;
    uint8_t TXPin;
    uint8_t RXPin;
} UART_t;

void UART_Init(void);
void UART_Receive_Data(UARTN_t uart_n, String &payload);
void UART_Send_Data(UARTN_t uart_n, String payload);
void UART_getSerial(HardwareSerial*serial,UARTN_t uart);

#endif