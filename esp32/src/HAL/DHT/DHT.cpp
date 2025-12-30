#include <Arduino.h>
#include <DHT.h>
#include "../../App_cfg.h"
#include "DHT.h"

#if DHT22_DEBUG == STD_ON
#define DEBUG_PRINTLN(var) Serial.println(var)
#else
#define DEBUG_PRINTLN(var)
#endif

static double temp = 0.0;

// Declare DHT object globally (outside function)
#if DHT22_ENABLED==STD_ON
DHT dht22(DHT22_PIN, DHT22);
#endif

void DHT22_INIT(void)
{
#if DHT22_ENABLED==STD_ON
  dht22.begin();
#endif
}


float ReadTemperatureSensor() {

  #if DHT22_ENABLED==STD_ON
  float tempc = dht22.readTemperature(); // Returns temperature in Celsius
  
  // Check if reading failed
  if (isnan(tempc)) {
    Serial.println("[ERROR] Failed to read temperatureF!");
    return 0.0;  // Return default value on error
  }
  else{
  Serial.print("[SENSOR] TemperatureF: ");
  Serial.print(tempc);
  Serial.println(" °C");
}
  return tempc;
  #endif
}

float ReadTemperatureSensorF() {
  #if DHT22_ENABLED==STD_ON
  float tempf = dht22.readTemperature(true);  // Returns temperature in Celsius
  
  // Check if reading failed
  if (isnan(tempf)) {
    Serial.println("[ERROR] Failed to read temperature!");
    return 0.0;  // Return default value on error
  }
  else{
  Serial.print("[SENSOR] Temperature: ");
  Serial.print(tempf);
  Serial.println(" °F");
}
  return tempf;
#endif
}


float ReadHumiditySensor() {
  #if DHT22_ENABLED==STD_ON
  float humi = dht22.readHumidity(); // Returns temperature in Celsius
  
  // Check if reading failed
  if (isnan(humi)) {
    Serial.println("[ERROR] Failed to read Humidity!");
    return 0.0;  // Return default value on error
  }
  else{
  Serial.print("[SENSOR] humidity: ");
  Serial.print(humi);
  Serial.println("%");
}
  return humi;
  #endif
}