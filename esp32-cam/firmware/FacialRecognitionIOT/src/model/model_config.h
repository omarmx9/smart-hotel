/**
 * @file model_config.h
 * @brief Model Input/Output Specifications
 * 
 * Defines the TensorFlow Lite model specifications
 */

#ifndef MODEL_CONFIG_H
#define MODEL_CONFIG_H

#include "../app_cfg.h"

// Model specifications (from model_data.h)
// Input shape: (1, 96, 96, 3)
// Input type: uint8 in range [0, 255]
// Output shape: (1, NUM_CLASSES)
// Output type: uint8 (quantized probabilities)

// Re-export from app_cfg for convenience
#define MODEL_WIDTH     MODEL_INPUT_WIDTH
#define MODEL_HEIGHT    MODEL_INPUT_HEIGHT
#define MODEL_CHANNELS  MODEL_INPUT_CHANNELS

#endif // MODEL_CONFIG_H
