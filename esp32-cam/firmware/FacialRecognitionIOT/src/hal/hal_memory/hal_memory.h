/**
 * @file hal_memory.h
 * @brief Hardware Abstraction Layer - Memory Management
 * 
 * PSRAM allocation and management
 */

#ifndef HAL_MEMORY_H
#define HAL_MEMORY_H

#include <cstddef>
#include <cstdint>

namespace hal {

/**
 * @brief Check if PSRAM is available
 * @return true if PSRAM found
 */
bool memoryHasPsram();

/**
 * @brief Get total PSRAM size
 * @return PSRAM size in bytes
 */
size_t memoryGetPsramSize();

/**
 * @brief Get free PSRAM
 * @return Free PSRAM in bytes
 */
size_t memoryGetFreePsram();

/**
 * @brief Allocate memory from PSRAM
 * @param size Size in bytes
 * @return Pointer to allocated memory, or nullptr on failure
 */
uint8_t* memoryAllocPsram(size_t size);

/**
 * @brief Free PSRAM memory
 * @param ptr Pointer to memory
 */
void memoryFreePsram(void* ptr);

/**
 * @brief Print memory status to serial
 */
void memoryPrintStatus();

}  // namespace hal

#endif // HAL_MEMORY_H
