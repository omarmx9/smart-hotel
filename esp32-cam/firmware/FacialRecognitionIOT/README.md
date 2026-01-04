# FacialRecognitionIOT

ESP32-CAM Face Recognition with MQTT publishing for smart hotel access control.

## Project Structure

```
FacialRecognitionIOT/
├── FacialRecognitionIOT.ino          # Arduino entry point
├── README.md
└── src/
    ├── app_cfg.h                      # Single configuration file
    ├── FacialRecognition_mgr/
    │   ├── FacialRecognition_mgr.h    # Main orchestrator header
    │   └── FacialRecognition_mgr.cpp  # Main orchestrator implementation
    ├── hal/
    │   ├── hal_camera/
    │   │   ├── hal_camera.h
    │   │   └── hal_camera.cpp
    │   ├── hal_led/
    │   │   ├── hal_led.h
    │   │   └── hal_led.cpp
    │   ├── hal_memory/
    │   │   ├── hal_memory.h
    │   │   └── hal_memory.cpp
    │   └── hal_mqtt/
    │       ├── hal_mqtt.h
    │       └── hal_mqtt.cpp
    ├── drivers/
    │   └── driver_tflite/
    │       ├── driver_tflite.h
    │       └── driver_tflite.cpp
    ├── app/
    │   ├── app_face_recognizer/
    │   │   ├── app_face_recognizer.h
    │   │   └── app_face_recognizer.cpp
    │   ├── app_graphics/
    │   │   ├── app_graphics.h
    │   │   └── app_graphics.cpp
    │   ├── app_image_processor/
    │   │   ├── app_image_processor.h
    │   │   └── app_image_processor.cpp
    │   └── app_mqtt_manager/
    │       ├── app_mqtt_manager.h
    │       └── app_mqtt_manager.cpp
    └── model/
        ├── class_labels.h
        ├── model_config.h
        └── model_data.h
```

## Quick Setup

### 1. Configure WiFi & MQTT

Edit `src/app_cfg.h`:

```cpp
#define WIFI_SSID           "your_wifi_ssid"
#define WIFI_PASSWORD       "your_wifi_password"
#define MQTT_BROKER         "your_mqtt_broker_ip"
#define MQTT_LOCATION       "main_lobby"  // or room_101, entrance, etc.
```

### 2. Arduino IDE Setup

1. Install **ESP32 board support**
2. Select board: **AI Thinker ESP32-CAM**
3. Set partition: **Huge APP (3MB No OTA)**
4. Enable: **PSRAM: Enabled**

### 3. Install Libraries

- **PubSubClient** (MQTT)
- **TensorFlow Lite Micro** (AI inference)

### 4. Upload & Test

1. Open `FacialRecognitionIOT.ino`
2. Upload to ESP32-CAM
3. Open Serial Monitor (115200 baud)
4. Check for: `=== System Ready for Face Recognition ===`

## MQTT Output

**Topic:** `hotel/face_recognition/{location}`

**Payload:**
```json
{
  "person_name": "maha",
  "confidence_score": 0.998,
  "timestamp": "2026-01-04T12:34:56Z",
  "recognized": true,
  "location": "main_lobby"
}
```

## Model Training

The model (`model_data.h`) is trained using:
- MobileNetV2 architecture
- 96x96 RGB input
- INT8 quantization
- 5 class labels: maha, mokhtar, omar, radwan, tarek

To retrain or add classes, use `esp32-cam/ai/train_facial_recognition.py`.

## Hardware

- **Board:** ESP32-CAM AI-Thinker
- **Sensor:** OV2640 (default) or RHYX M21-45
- **Memory:** 4MB PSRAM required
- **LED:** GPIO 33 (flash feedback)

## Configuration Reference

All settings are in `src/app_cfg.h`:

| Setting | Default | Description |
|---------|---------|-------------|
| `WIFI_SSID` | - | WiFi network name |
| `WIFI_PASSWORD` | - | WiFi password |
| `MQTT_BROKER` | `192.168.1.100` | MQTT broker IP |
| `MQTT_PORT` | `1883` | MQTT port |
| `MQTT_LOCATION` | `main_lobby` | Device location |
| `CONFIDENCE_THRESHOLD` | `0.995` | Recognition threshold |
| `INFERENCE_DELAY_MS` | `100` | Delay between frames |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| PSRAM not found | Enable PSRAM in Arduino IDE board settings |
| WiFi timeout | Check SSID/password in app_cfg.h |
| MQTT not connected | Verify broker IP and port 1883 is open |
| Low confidence | Improve lighting or lower threshold |
