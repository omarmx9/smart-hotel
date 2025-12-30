#ifndef APP_CFG_H
#define APP_CFG_H

/* =========================
 * Standard Definitions
 * ========================= */
#define STD_ON   1
#define STD_OFF  0


/* =========================
 * Module Enables
 * ========================= */
#define GPIO_ENABLED        STD_ON
#define SENSORH_ENABLED     STD_ON
#define POT_ENABLED         STD_ON
#define UART_ENABLED        STD_ON
#define ALARM_ENABLED       STD_OFF
#define CHATAPP_ENABLED     STD_OFF
#define SPI_ENABLED         STD_OFF
#define I2C_ENABLED         STD_OFF
#define LED_ENABLED         STD_ON
#define LITTLEFS_ENABLED    STD_OFF
#define LM35_ENABLED        STD_ON
#define WIFI_ENABLED        STD_ON
#define MQTT_ENABLED        STD_ON


/* =========================
 * Debug Flags
 * ========================= */
#define GPIO_DEBUG          STD_ON
#define SENSORH_DEBUG       STD_ON
#define POT_DEBUG           STD_OFF
#define UART_DEBUG          STD_ON
#define ALARM_DEBUG         STD_OFF
#define CHATAPP_DEBUG       STD_OFF
#define SPI_DEBUG           STD_OFF
#define I2C_DEBUG           STD_OFF
#define LED_DEBUG           STD_OFF
#define LITTLEFS_DEBUG      STD_OFF
#define LM35_DEBUG          STD_ON
#define WIFI_DEBUG          STD_ON
#define MQTT_DEBUG          STD_ON


/* =========================
 * UART Configuration
 * ========================= */
#define UART_BAUD_RATE      9600
#define UART_FRAME_LENGTH   SERIAL_8N1
#define UART_TX_PIN         17
#define UART_RX_PIN         16


/* =========================
 * SPI Configuration
 * ========================= */
#define SPI_BUS             SPI_VSPI_BUS
#define SPI_SCK_PIN         18
#define SPI_MISO_PIN        19
#define SPI_MOSI_PIN        23
#define SPI_CS_PIN          5
#define SPI_MODE            SPI_MODE0
#define SPI_FREQUENCY       8000000
#define SPI_BIT_ORDER       MSBFIRST


/* =========================
 * I2C Configuration
 * ========================= */
#define I2C_BUS             I2C0_BUS
#define I2C_SDA_PIN         21
#define I2C_SCL_PIN         22
#define I2C_FREQUENCY       1000000


/* =========================
 * POT Configuration
 * ========================= */
#define POT_PIN             34
#define POT_RESOLUTION      12
#define MIN_POT_VALUE       0
#define MAX_POT_VALUE       ((1 << POT_RESOLUTION) - 1)


/* =========================
 * Alarm Configuration
 * ========================= */
#define ALARM_LED_HIGH_PIN          16
#define ALARM_LED_LOW_PIN           17
#define ALARM_LED_DIMMER_PWM_CH     2

#define FIRST_ALARM_STATE           NORMAL_ALARM
#define ALARM_LOW_THRESHOLD_PERCENT 30
#define ALARM_HIGH_THRESHOLD_PERCENT 80

#define MIN_PERCENTAGE              0
#define MAX_PERCENTAGE              100


/* =========================
 * PWM Configuration
 * ========================= */
#define PWM_FREQ            5000
#define PWM_RESOLUTION      8
#define PWM_CHANNEL         0


/* =========================
 * LM35 Temperature Sensor
 * ========================= */
#define LM35_ADC_PIN        33
#define LM35_VREF           3.3f
#define LM35_ADC_MAX        4095.0f


/* =========================
 * Ultrasonic Sensor (US)
 * ========================= */
#define US_TRIG_PIN         5
#define US_ECHO_PIN         18
#define SOUND_SPEED_CM_US   0.0343f
#define US_ECHO_TIMEOUT_US  30000UL


/* =========================
 * LED Configuration
 * ========================= */
#define LED_1_PIN           34
#define LED_2_PIN           35
#define LED_3_PIN           32


/* =========================
 * WiFi Configuration
 * ========================= */
#define WIFI_SSID           "saddevastator-hotspot"
#define WIFI_PASSWORD       "12345678"


/* =========================
 * MQTT Configuration
 * ========================= */
#define MQTT_BROKER         "mqtt.saddevastator.qzz.io"
#define MQTT_PORT           1883
#define MQTT_KEEPALIVE      60
#define MQTT_RECONNECT_MS   5000
/* =========================
 * MQTT Topics
 * ========================= */
#define MQTT_TOPIC_TEMP         "home/thermostat/temperature"
#define MQTT_TOPIC_HUMIDITY     "home/thermostat/humidity"
#define MQTT_TOPIC_TARGET       "home/thermostat/target"
#define MQTT_TOPIC_HEATING      "home/thermostat/heating"
#define MQTT_TOPIC_LUMINOSITY   "home/thermostat/luminosity"
#define MQTT_TOPIC_GAS          "home/thermostat/gas"
#define MQTT_TOPIC_CONTROL      "home/thermostat/control"



/* =========================
 * Thermostat Configuration
 * ========================= */
#define THERMOSTAT_UPDATE_RATE_MS   1000
#define THERMOSTAT_PUBLISH_RATE_MS  5000
#define THERMOSTAT_TEMP_DEADBAND    0.5f

#define TEMP_MIN            15.0f
#define TEMP_MAX            35.0f
#define HUMIDITY_MIN        20.0f
#define HUMIDITY_MAX        90.0f


/* =========================
 * System Configuration
 * ========================= */
#define SERIAL_BAUD_RATE    115200


/* =========================
 * SMS
 * ========================= */
#define SMS_RECIPIENT "+201120076894"

#endif /* APP_CFG_H */