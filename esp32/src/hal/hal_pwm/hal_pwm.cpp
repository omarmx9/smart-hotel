#include "hal_pwm.h"

// Platform-specific includes
#ifdef ARDUINO
    #if defined(ESP32)
        #include <Arduino.h>
        // ESP32 uses ledc functions from esp32-hal-ledc.h (included via Arduino.h)
        // Alternative direct include if needed:
        // #include "esp32-hal-ledc.h"
    #else
        #error "Unsupported platform for PWM"
    #endif
#endif

#if defined(ESP32)
    extern "C" {
        #include "esp32-hal-ledc.h"
    }
#endif


void PWM_Init(PWM_Channel_t channel, uint8_t pin, uint32_t frequency, uint8_t resolution)
{
#if defined(ESP32)
    // ESP32 LEDC (LED Control) PWM
    ledcSetup(channel, frequency, resolution);
    ledcAttachPin(pin, channel);
    ledcWrite(channel, 0); // Start at 0
#else
    // Add support for other platforms here
    #error "PWM not implemented for this platform"
#endif
}

void PWM_Write(PWM_Channel_t channel, uint8_t value)
{
#if defined(ESP32)
    ledcWrite(channel, value);
#else
    #error "PWM not implemented for this platform"
#endif
}

void PWM_SetFrequency(PWM_Channel_t channel, uint32_t frequency)
{
#if defined(ESP32)
    ledcWriteTone(channel, frequency);
#else
    #error "PWM not implemented for this platform"
#endif
}
