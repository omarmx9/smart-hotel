#ifndef HAL_LDR_H
#define HAL_LDR_H

void LDR_1_init(void);
void LDR_1_main(void);

uint16_t LDR_1_getRawValue(void);
uint16_t LDR_1_getAveragedValue(void);
uint16_t LDR_1_getLightPercentage(void);
float LDR_1_calculateLux(void);

#endif
