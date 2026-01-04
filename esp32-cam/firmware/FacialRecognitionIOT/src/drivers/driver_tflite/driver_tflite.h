/**
 * @file driver_tflite.h
 * @brief TensorFlow Lite Micro Driver
 * 
 * TFLite interpreter initialization, model loading, inference execution
 */

#ifndef DRIVER_TFLITE_H
#define DRIVER_TFLITE_H

#include <cstdint>
#include "tensorflow/lite/micro/micro_interpreter.h"

namespace driver {

/**
 * @brief Initialize TFLite interpreter with model
 * @param modelData Pointer to model data (PROGMEM)
 * @param arenaSize Tensor arena size in bytes
 * @return true on success
 */
bool tfliteInit(const uint8_t* modelData, size_t arenaSize);

/**
 * @brief Run inference
 * @return true on success
 */
bool tfliteInvoke();

/**
 * @brief Get input tensor pointer
 * @return Input tensor or nullptr
 */
TfLiteTensor* tfliteGetInput();

/**
 * @brief Get output tensor pointer
 * @return Output tensor or nullptr
 */
TfLiteTensor* tfliteGetOutput();

/**
 * @brief Get arena used bytes
 * @return Bytes used by interpreter
 */
size_t tfliteGetArenaUsed();

/**
 * @brief Check if TFLite is ready
 * @return true if initialized
 */
bool tfliteIsReady();

/**
 * @brief Cleanup TFLite resources
 */
void tfliteCleanup();

}  // namespace driver

#endif // DRIVER_TFLITE_H
