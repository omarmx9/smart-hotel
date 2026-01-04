/**
 * @file hal_memory.cpp
 * @brief Hardware Abstraction Layer - Memory Implementation
 */

#include "hal_memory.h"
#include <Arduino.h>
#include <esp_heap_caps.h>

namespace hal {

bool memoryHasPsram() {
    return psramFound();
}

size_t memoryGetPsramSize() {
    return ESP.getPsramSize();
}

size_t memoryGetFreePsram() {
    return ESP.getFreePsram();
}

uint8_t* memoryAllocPsram(size_t size) {
    return (uint8_t*)heap_caps_malloc(size, MALLOC_CAP_SPIRAM);
}

void memoryFreePsram(void* ptr) {
    if (ptr) {
        heap_caps_free(ptr);
    }
}

void memoryPrintStatus() {
    if (psramFound()) {
        Serial.printf("[HAL] PSRAM: %d total, %d free\n", 
                      ESP.getPsramSize(), ESP.getFreePsram());
    } else {
        Serial.println("[HAL] WARNING: No PSRAM found!");
    }
    Serial.printf("[HAL] Heap: %d free\n", ESP.getFreeHeap());
}

}  // namespace hal
