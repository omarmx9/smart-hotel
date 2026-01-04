/**
 * @file hal_camera.cpp
 * @brief Hardware Abstraction Layer - Camera Implementation
 */

#include "hal_camera.h"
#include "../../app_cfg.h"
#include <Arduino.h>

namespace hal {

static bool s_cameraReady = false;

esp_err_t cameraInit() {
    camera_config_t config;
    
    // LEDC configuration
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    
    // Pin configuration from app_cfg.h
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    
    // Sensor configuration from app_cfg.h
    config.xclk_freq_hz = XCLK_FREQ_HZ;
    config.pixel_format = INITIAL_PIXEL_FORMAT;
    config.frame_size = INITIAL_FRAME_SIZE;
    config.grab_mode = INITIAL_GRAB_MODE;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = INITIAL_JPEG_QUALITY;
    config.fb_count = INITIAL_FB_COUNT;

    // Initialize camera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[HAL] Camera init failed: 0x%x\n", err);
        return err;
    }

    // Apply sensor tuning
    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_brightness(s, 1);
        s->set_contrast(s, 1);
        s->set_saturation(s, 1);
        s->set_whitebal(s, 1);
        s->set_awb_gain(s, 1);
        s->set_wb_mode(s, 0);
        s->set_exposure_ctrl(s, 1);
        s->set_aec2(s, 1);
        s->set_gain_ctrl(s, 1);
        s->set_vflip(s, 0);
        s->set_hmirror(s, 0);
        s->set_lenc(s, 1);
    }

    s_cameraReady = true;
    Serial.printf("[HAL] Camera initialized: %s\n", SENSOR_NAME);
    return ESP_OK;
}

camera_fb_t* cameraCapture() {
    if (!s_cameraReady) {
        return nullptr;
    }
    return esp_camera_fb_get();
}

void cameraRelease(camera_fb_t* fb) {
    if (fb) {
        esp_camera_fb_return(fb);
    }
}

sensor_t* cameraGetSensor() {
    return esp_camera_sensor_get();
}

bool cameraIsReady() {
    return s_cameraReady;
}

}  // namespace hal
