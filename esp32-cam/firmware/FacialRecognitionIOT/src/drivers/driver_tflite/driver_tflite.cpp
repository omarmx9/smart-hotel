/**
 * @file driver_tflite.cpp
 * @brief TensorFlow Lite Micro Driver Implementation
 */

#include "driver_tflite.h"
#include "../../hal/hal_memory/hal_memory.h"
#include <Arduino.h>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace driver {

// Static storage
static const tflite::Model* s_model = nullptr;
static tflite::MicroInterpreter* s_interpreter = nullptr;
static TfLiteTensor* s_input = nullptr;
static TfLiteTensor* s_output = nullptr;
static uint8_t* s_tensorArena = nullptr;
static bool s_ready = false;

// Op resolver with MobileNetV2 operations (static to persist)
static tflite::MicroMutableOpResolver<15> s_resolver;

bool tfliteInit(const uint8_t* modelData, size_t arenaSize) {
    // Allocate tensor arena in PSRAM
    s_tensorArena = hal::memoryAllocPsram(arenaSize);
    if (!s_tensorArena) {
        Serial.println("[TFLite] Failed to allocate tensor arena!");
        return false;
    }
    Serial.printf("[TFLite] Arena allocated: %d bytes\n", arenaSize);

    // Load model
    s_model = tflite::GetModel(modelData);
    if (s_model->version() != TFLITE_SCHEMA_VERSION) {
        Serial.printf("[TFLite] Model version mismatch: %d vs %d\n",
                      s_model->version(), TFLITE_SCHEMA_VERSION);
        return false;
    }

    // Add required operations for MobileNetV2
    s_resolver.AddConv2D();
    s_resolver.AddDepthwiseConv2D();
    s_resolver.AddFullyConnected();
    s_resolver.AddSoftmax();
    s_resolver.AddReshape();
    s_resolver.AddAveragePool2D();
    s_resolver.AddAdd();
    s_resolver.AddMean();
    s_resolver.AddQuantize();
    s_resolver.AddDequantize();
    s_resolver.AddPad();
    s_resolver.AddRelu6();

    // Create interpreter (static allocation)
    static tflite::MicroInterpreter staticInterpreter(
        s_model, s_resolver, s_tensorArena, arenaSize);
    s_interpreter = &staticInterpreter;

    // Allocate tensors
    if (s_interpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("[TFLite] AllocateTensors failed!");
        return false;
    }

    // Get input/output tensors
    s_input = s_interpreter->input(0);
    s_output = s_interpreter->output(0);

    Serial.printf("[TFLite] Model loaded!\n");
    Serial.printf("[TFLite] Input: [%d, %d, %d, %d] type=%d\n",
                  s_input->dims->data[0], s_input->dims->data[1],
                  s_input->dims->data[2], s_input->dims->data[3],
                  s_input->type);
    Serial.printf("[TFLite] Output classes: %d\n", s_output->dims->data[1]);
    Serial.printf("[TFLite] Arena used: %d bytes\n", s_interpreter->arena_used_bytes());

    s_ready = true;
    return true;
}

bool tfliteInvoke() {
    if (!s_ready || !s_interpreter) {
        return false;
    }
    return s_interpreter->Invoke() == kTfLiteOk;
}

TfLiteTensor* tfliteGetInput() {
    return s_input;
}

TfLiteTensor* tfliteGetOutput() {
    return s_output;
}

size_t tfliteGetArenaUsed() {
    if (s_interpreter) {
        return s_interpreter->arena_used_bytes();
    }
    return 0;
}

bool tfliteIsReady() {
    return s_ready;
}

void tfliteCleanup() {
    if (s_tensorArena) {
        hal::memoryFreePsram(s_tensorArena);
        s_tensorArena = nullptr;
    }
    s_interpreter = nullptr;
    s_model = nullptr;
    s_input = nullptr;
    s_output = nullptr;
    s_ready = false;
}

}  // namespace driver
