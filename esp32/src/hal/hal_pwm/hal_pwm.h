#ifndef HAL_PWM_H
#define HAL_PWM_H

#include <stdint.h>

// PWM channel type
typedef uint8_t PWM_Channel_t;

// Function prototypes
void PWM_Init(PWM_Channel_t channel, uint8_t pin, uint32_t frequency, uint8_t resolution);
void PWM_Write(PWM_Channel_t channel, uint8_t value);
void PWM_SetFrequency(PWM_Channel_t channel, uint32_t frequency);

#endif // HAL_PWM_H

