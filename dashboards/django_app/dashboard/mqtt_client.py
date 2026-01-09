"""MQTT Client for Smart Hotel Dashboard"""

import paho.mqtt.client as mqtt
from django.conf import settings
import threading
import logging
import json

logger = logging.getLogger(__name__)

mqtt_client = None
mqtt_connected = False


def get_mqtt_client():
    global mqtt_client
    return mqtt_client


def is_connected():
    global mqtt_connected
    return mqtt_connected


def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        logger.info("[MQTT] Connected to broker")
        mqtt_connected = True
        
        # ========================================
        # JSON Telemetry (NEW - PREFERRED FORMAT)
        # ========================================
        # Topic: hotel/<room_id>/telemetry/json
        # ESP32 sends complete JSON payload with all sensors
        client.subscribe("hotel/+/telemetry/json")
        
        # ========================================
        # Legacy Telemetry (DEPRECATED - for backward compatibility)
        # ========================================
        # Topic structure: hotel/<room_no>/telemetry/<sensor>
        client.subscribe("hotel/+/telemetry/temperature")
        client.subscribe("hotel/+/telemetry/humidity")
        client.subscribe("hotel/+/telemetry/luminosity")
        client.subscribe("hotel/+/telemetry/ldr_percent")
        client.subscribe("hotel/+/telemetry/gas")
        client.subscribe("hotel/+/telemetry/heating")
        client.subscribe("hotel/+/telemetry/climate_mode")
        client.subscribe("hotel/+/telemetry/fan_speed")
        
        # Subscribe to LED status topics
        # Topic structure: hotel/<room_no>/status/<led>
        client.subscribe("hotel/+/status/led1")
        client.subscribe("hotel/+/status/led2")
        client.subscribe("hotel/+/status/room_mode")
        
        # Subscribe to ESP32-CAM face recognition events
        # Topic structure: hotel/kiosk/<room_id>/FaceRecognition/Authentication
        client.subscribe("hotel/kiosk/+/FaceRecognition/Authentication")
        # Legacy topic structure (backward compatibility)
        client.subscribe("hotel/kiosk/+/face/recognized")
        client.subscribe("hotel/kiosk/+/face/unknown")
        client.subscribe("hotel/kiosk/+/status")
        client.subscribe("hotel/kiosk/+/heartbeat")
        
        logger.info("[MQTT] Subscribed to JSON telemetry topic (hotel/+/telemetry/json)")
        logger.info("[MQTT] Subscribed to legacy telemetry topics (backward compatibility)")
        logger.info("[MQTT] Subscribed to ESP32-CAM face recognition topics")
    else:
        logger.error(f"[MQTT] Connection failed with code {rc}")
        mqtt_connected = False


def on_disconnect(client, userdata, rc):
    global mqtt_connected
    logger.warning("[MQTT] Disconnected from broker")
    mqtt_connected = False


def on_message(client, userdata, msg):
    """Handle incoming MQTT messages and update room data"""
    try:
        topic_parts = msg.topic.split('/')
        
        # Handle ESP32-CAM face recognition topic
        # Topic structure: hotel/kiosk/<room_id>/FaceRecognition/Authentication
        # After split: ['hotel', 'kiosk', '<room_id>', 'FaceRecognition', 'Authentication']
        if (len(topic_parts) >= 5 and 
            topic_parts[0] == 'hotel' and 
            topic_parts[1] == 'kiosk' and
            topic_parts[3] == 'FaceRecognition' and 
            topic_parts[4] == 'Authentication'):
            room_id = topic_parts[2]
            handle_face_recognition_auth(room_id, msg.payload.decode())
            return
        
        # Handle legacy ESP32-CAM face recognition events
        # Topic structure: hotel/kiosk/<device_id>/face/<event>
        if len(topic_parts) >= 4 and topic_parts[0] == 'hotel' and topic_parts[1] == 'kiosk':
            device_id = topic_parts[2]
            
            if len(topic_parts) >= 5 and topic_parts[3] == 'face':
                event_type = topic_parts[4]
                handle_espcam_face_event(device_id, event_type, msg.payload.decode())
            elif topic_parts[3] == 'status':
                handle_espcam_status(device_id, msg.payload.decode())
            elif topic_parts[3] == 'heartbeat':
                handle_espcam_heartbeat(device_id, msg.payload.decode())
            return
        
        # ========================================
        # Handle JSON telemetry (NEW FORMAT)
        # ========================================
        # Topic structure: hotel/<room_id>/telemetry/json
        # Payload: {"room":"Room101","timestamp":...,"sensors":{...},"state":{...}}
        if (len(topic_parts) >= 4 and 
            topic_parts[0] == 'hotel' and 
            topic_parts[2] == 'telemetry' and
            topic_parts[3] == 'json'):
            room_number = topic_parts[1]
            handle_json_telemetry(room_number, msg.payload.decode())
            return
        
        # ========================================
        # Handle legacy room telemetry (DEPRECATED)
        # ========================================
        # Topic structure: hotel/<room_no>/telemetry/<sensor>
        # After split: ['hotel', '<room_no>', 'telemetry', '<sensor>']
        if len(topic_parts) >= 4 and topic_parts[0] == 'hotel' and topic_parts[2] == 'telemetry':
            room_number = topic_parts[1]
            sensor_type = topic_parts[3]
            payload = msg.payload.decode()
            
            # Import here to avoid circular imports
            from rooms.models import Room, SensorHistory
            
            try:
                room = Room.objects.get(room_number=room_number)
            except Room.DoesNotExist:
                logger.warning(f"[MQTT] Room {room_number} not found")
                return
            
            # Update sensor value
            if sensor_type == 'temperature':
                room.temperature = float(payload)
            elif sensor_type == 'humidity':
                room.humidity = float(payload)
            elif sensor_type in ('luminosity', 'ldr_percent'):
                room.ldr_percentage = int(payload)
            elif sensor_type == 'gas':
                room.gas_level = int(payload)
            elif sensor_type == 'heating':
                room.heating_status = payload.lower() in ['true', '1', 'on']
            elif sensor_type == 'climate_mode':
                if payload.lower() in ['auto', 'manual', 'off']:
                    room.climate_mode = payload.lower()
            elif sensor_type == 'fan_speed':
                if payload.lower() in ['low', 'medium', 'high']:
                    room.fan_speed = payload.lower()
            
            room.save()
            
            # Record history periodically (every 10th message)
            if hasattr(on_message, 'counter'):
                on_message.counter += 1
            else:
                on_message.counter = 1
            
            if on_message.counter % 10 == 0:
                SensorHistory.record(room)
            
            logger.debug(f"[MQTT] Legacy {room_number}/{sensor_type}: {payload}")
            return
        
        # Handle LED status messages
        # Topic structure: hotel/<room_no>/status/<led>
        # After split: ['hotel', '<room_no>', 'status', '<led>']
        if len(topic_parts) >= 4 and topic_parts[0] == 'hotel' and topic_parts[2] == 'status':
            room_number = topic_parts[1]
            status_type = topic_parts[3]
            payload = msg.payload.decode()
            
            # Import here to avoid circular imports
            from rooms.models import Room
            
            try:
                room = Room.objects.get(room_number=room_number)
            except Room.DoesNotExist:
                logger.warning(f"[MQTT] Room {room_number} not found")
                return
            
            if status_type == 'led1':
                room.led1_status = payload.upper() == 'ON'
                room.save()
                logger.debug(f"[MQTT] {room_number}/led1: {payload}")
            elif status_type == 'led2':
                room.led2_status = payload.upper() == 'ON'
                room.save()
                logger.debug(f"[MQTT] {room_number}/led2: {payload}")
            elif status_type == 'room_mode':
                mode = payload.lower()
                if mode in ['auto', 'manual', 'off']:
                    room.light_mode = mode
                    room.save()
                    logger.debug(f"[MQTT] {room_number}/room_mode: {payload}")
            return
            
    except Exception as e:
        logger.error(f"[MQTT] Error processing message: {e}")


# ==================== JSON TELEMETRY HANDLER ====================

def handle_json_telemetry(room_number, payload):
    """
    Handle JSON telemetry messages from ESP32 devices.
    
    Topic: hotel/<room_id>/telemetry/json
    
    Payload format:
        {
            "room": "Room101",
            "timestamp": 123456789,
            "sensors": {
                "temperature": 25.5,
                "humidity": 60.0,
                "light_percent": 75,
                "gas_level": 120,
                "target_temp": 24.0
            },
            "state": {
                "thermostat_mode": "AUTO",
                "fan_speed": "LOW",
                "heating": false,
                "room_mode": "MANUAL",
                "led1": "ON",
                "led2": "OFF"
            }
        }
    """
    try:
        data = json.loads(payload)
        
        # Import here to avoid circular imports
        from rooms.models import Room, SensorHistory
        
        try:
            room = Room.objects.get(room_number=room_number)
        except Room.DoesNotExist:
            logger.warning(f"[MQTT JSON] Room {room_number} not found")
            return
        
        # Extract sensor readings
        sensors = data.get('sensors', {})
        state = data.get('state', {})
        
        # Update sensor values
        if 'temperature' in sensors:
            room.temperature = float(sensors['temperature'])
        
        if 'humidity' in sensors:
            room.humidity = float(sensors['humidity'])
        
        if 'light_percent' in sensors:
            room.ldr_percentage = int(sensors['light_percent'])
        
        if 'gas_level' in sensors:
            room.gas_level = int(sensors['gas_level'])
        
        if 'target_temp' in sensors:
            room.target_temperature = float(sensors['target_temp'])
        
        # Update state values
        if 'thermostat_mode' in state:
            mode = state['thermostat_mode'].lower()
            if mode in ['auto', 'manual', 'off']:
                room.climate_mode = mode
        
        if 'fan_speed' in state:
            speed = state['fan_speed'].lower()
            if speed in ['low', 'medium', 'high', 'off']:
                room.fan_speed = speed if speed != 'off' else 'low'
        
        if 'heating' in state:
            room.heating_status = bool(state['heating'])
        
        if 'room_mode' in state:
            mode = state['room_mode'].lower()
            if mode in ['auto', 'manual', 'off']:
                room.light_mode = mode
        
        if 'led1' in state:
            room.led1_status = state['led1'].upper() == 'ON'
        
        if 'led2' in state:
            room.led2_status = state['led2'].upper() == 'ON'
        
        room.save()
        
        # Record history for JSON messages (once per message since it contains all data)
        if hasattr(handle_json_telemetry, 'counter'):
            handle_json_telemetry.counter += 1
        else:
            handle_json_telemetry.counter = 1
        
        # Record history every 6 messages (~1 minute at 10s intervals)
        if handle_json_telemetry.counter % 6 == 0:
            SensorHistory.record(room)
        
        logger.debug(f"[MQTT JSON] {room_number}: T={sensors.get('temperature', 'N/A')}°C, "
                    f"H={sensors.get('humidity', 'N/A')}%, "
                    f"Gas={sensors.get('gas_level', 'N/A')}")
        
    except json.JSONDecodeError as e:
        logger.error(f"[MQTT JSON] Invalid JSON payload from {room_number}: {e}")
    except Exception as e:
        logger.error(f"[MQTT JSON] Error handling telemetry from {room_number}: {e}")


# ==================== ESP32-CAM FACE RECOGNITION HANDLERS ====================

def handle_face_recognition_auth(room_id, payload):
    """
    Handle face recognition authentication events from ESP32-CAM devices.
    
    Topic: hotel/kiosk/<room_id>/FaceRecognition/Authentication
    
    Payload format:
        {
            "name": "person_name",
            "confidence": 0.95,
            "result": "success" | "unknown" | "denied",
            "timestamp": 1234567890
        }
    """
    try:
        data = json.loads(payload)
        name = data.get('name', 'Unknown')
        confidence = data.get('confidence', 0)
        result = data.get('result', 'unknown')
        
        logger.info(f"[FaceRecog] Room {room_id}: {name} - {result} ({confidence*100:.1f}%)")
        
        # Store recognition event
        store_face_recognition_event(room_id, name, confidence, result)
        
        # Handle different results
        if result == 'success':
            # Guest authenticated successfully - could trigger room unlock
            logger.info(f"[FaceRecog] Guest '{name}' authenticated for room {room_id}")
        elif result == 'denied':
            # Access denied - possible security event
            logger.warning(f"[FaceRecog] Access denied for '{name}' at room {room_id}")
            publish_notification(
                f"🚨 Access denied at Room {room_id} for '{name}'",
                notification_type='alert',
                priority='high'
            )
        elif result == 'unknown':
            # Unknown face detected
            logger.debug(f"[FaceRecog] Unknown face at room {room_id}")
            
    except json.JSONDecodeError as e:
        logger.error(f"[FaceRecog] Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"[FaceRecog] Error handling authentication event: {e}")


def handle_espcam_face_event(device_id, event_type, payload):
    """
    Handle legacy face recognition events from ESP32-CAM devices.
    
    Events:
        - recognized: A known face was detected with high confidence
        - unknown: A face was detected but couldn't be identified
    
    Payload format:
        {
            "name": "person_name",      # Only for recognized events
            "confidence": 0.95,
            "timestamp": 1234567890,
            "device": "esp32cam-kiosk-01"
        }
    """
    try:
        data = json.loads(payload)
        
        if event_type == 'recognized':
            name = data.get('name', 'Unknown')
            confidence = data.get('confidence', 0)
            
            logger.info(f"[ESP32-CAM] Face recognized on {device_id}: {name} ({confidence*100:.1f}%)")
            
            # Store recognition event for kiosk integration
            store_face_recognition_event(device_id, name, confidence)
            
            # Optionally notify via Telegram/SMS for VIP guests
            if confidence >= 0.99:
                publish_notification(
                    f"VIP Guest '{name}' detected at kiosk {device_id}",
                    notification_type='system',
                    priority='normal'
                )
        
        elif event_type == 'unknown':
            confidence = data.get('confidence', 0)
            logger.debug(f"[ESP32-CAM] Unknown face on {device_id} (confidence: {confidence*100:.1f}%)")
            
    except json.JSONDecodeError as e:
        logger.error(f"[ESP32-CAM] Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error handling face event: {e}")


def handle_espcam_status(device_id, payload):
    """
    Handle status updates from ESP32-CAM devices.
    
    Payload format:
        {
            "status": "online",
            "uptime": 12345,
            "model_ready": true,
            "free_heap": 123456,
            "wifi_rssi": -45,
            "ip": "192.168.1.100"
        }
    """
    try:
        data = json.loads(payload)
        status = data.get('status', 'unknown')
        uptime = data.get('uptime', 0)
        model_ready = data.get('model_ready', False)
        
        logger.info(f"[ESP32-CAM] {device_id} status: {status}, uptime: {uptime}s, model: {model_ready}")
        
        # Store device status (could be in Redis or database)
        store_espcam_status(device_id, data)
        
    except json.JSONDecodeError as e:
        logger.error(f"[ESP32-CAM] Invalid status JSON: {e}")
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error handling status: {e}")


def handle_espcam_heartbeat(device_id, payload):
    """
    Handle heartbeat from ESP32-CAM devices.
    Used for monitoring device health.
    """
    try:
        data = json.loads(payload)
        logger.debug(f"[ESP32-CAM] Heartbeat from {device_id}: heap={data.get('free_heap', 0)}")
        
        # Update last seen timestamp
        update_espcam_last_seen(device_id)
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error handling heartbeat: {e}")


def store_face_recognition_event(device_id, name, confidence):
    """Store face recognition event for kiosk integration."""
    # This can be extended to:
    # 1. Store in database for analytics
    # 2. Trigger kiosk auto-fill if guest profile exists
    # 3. Update real-time dashboard via WebSocket
    try:
        from django.core.cache import cache
        
        # Store latest recognition for quick lookup
        cache_key = f"espcam_recognition_{device_id}"
        cache.set(cache_key, {
            'name': name,
            'confidence': confidence,
            'timestamp': json.dumps({}),  # Would be actual timestamp
        }, timeout=300)  # 5 minute TTL
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error storing recognition: {e}")


def store_espcam_status(device_id, status_data):
    """Store ESP32-CAM device status."""
    try:
        from django.core.cache import cache
        
        cache_key = f"espcam_status_{device_id}"
        cache.set(cache_key, status_data, timeout=120)  # 2 minute TTL
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error storing status: {e}")


def update_espcam_last_seen(device_id):
    """Update last seen timestamp for device health monitoring."""
    try:
        from django.core.cache import cache
        from datetime import datetime
        
        cache_key = f"espcam_lastseen_{device_id}"
        cache.set(cache_key, datetime.now().isoformat(), timeout=300)
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error updating last seen: {e}")


# ==================== ESP32-CAM CONTROL FUNCTIONS ====================

def send_espcam_command(device_id, command):
    """
    Send control command to ESP32-CAM device.
    
    Commands:
        - status: Request status update
        - restart: Restart device
        - capture: Force capture and recognition
    """
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot send command")
        return False
    
    topic = f"hotel/kiosk/{device_id}/control"
    payload = json.dumps({'command': command})
    
    try:
        mqtt_client.publish(topic, payload, qos=1)
        logger.info(f"[ESP32-CAM] Sent command '{command}' to {device_id}")
        return True
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error sending command: {e}")
        return False


def get_espcam_status(device_id):
    """Get cached status for an ESP32-CAM device."""
    try:
        from django.core.cache import cache
        
        cache_key = f"espcam_status_{device_id}"
        return cache.get(cache_key)
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error getting status: {e}")
        return None


def get_latest_recognition(device_id):
    """Get latest face recognition result for a device."""
    try:
        from django.core.cache import cache
        
        cache_key = f"espcam_recognition_{device_id}"
        return cache.get(cache_key)
        
    except Exception as e:
        logger.error(f"[ESP32-CAM] Error getting recognition: {e}")
        return None


def start_mqtt_client():
    """Start the MQTT client in a background thread"""
    global mqtt_client
    
    if mqtt_client is not None:
        return
    
    def run_mqtt():
        global mqtt_client
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = on_connect
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_message = on_message
        
        try:
            broker = getattr(settings, 'MQTT_BROKER', 'localhost')
            port = getattr(settings, 'MQTT_PORT', 1883)
            
            logger.info(f"[MQTT] Connecting to {broker}:{port}")
            mqtt_client.connect(broker, port, 60)
            mqtt_client.loop_forever()
        except Exception as e:
            logger.error(f"[MQTT] Connection error: {e}")
    
    thread = threading.Thread(target=run_mqtt, daemon=True)
    thread.start()


def publish_target_temperature(room, temperature):
    """Publish target temperature to MQTT broker"""
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    # Topic structure: /hotel/<room_no>/control/<topic>
    topic = f"/hotel/{room.room_number}/control/target_temperature"
    try:
        mqtt_client.publish(topic, str(temperature))
        logger.info(f"[MQTT] Published target {temperature}C to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_climate_mode(room, mode):
    """Publish climate mode to MQTT broker"""
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    topic = f"/hotel/{room.room_number}/control/climate_mode"
    try:
        mqtt_client.publish(topic, mode)
        logger.info(f"[MQTT] Published climate mode {mode} to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_fan_speed(room, speed):
    """Publish fan speed to MQTT broker"""
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    topic = f"/hotel/{room.room_number}/control/fan_speed"
    try:
        mqtt_client.publish(topic, speed)
        logger.info(f"[MQTT] Published fan speed {speed} to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_luminosity(room, level):
    """Publish luminosity level by controlling LED1 and LED2
    
    level 0: Both LEDs off
    level 1: LED1 on, LED2 off
    level 2: Both LEDs on
    """
    led1_state = "ON" if level >= 1 else "OFF"
    led2_state = "ON" if level >= 2 else "OFF"
    
    result1 = publish_led_control(room, 1, led1_state)
    result2 = publish_led_control(room, 2, led2_state)
    
    return result1 and result2


def publish_led_control(room, led_number, state):
    """Publish LED control command to MQTT broker
    
    Args:
        room: Room object
        led_number: 1 or 2
        state: 'ON' or 'OFF'
    """
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    topic = f"hotel/{room.room_number}/control/led{led_number}"
    try:
        mqtt_client.publish(topic, state)
        logger.info(f"[MQTT] Published LED{led_number} {state} to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_light_mode(room, mode):
    """Publish light mode (auto/manual/off) to MQTT broker
    
    Maps to room_mode control topic:
    - 'auto' -> 'AUTO'
    - 'manual' -> 'MANUAL'
    - 'off' -> 'OFF'
    """
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    # Map mode to ESP32 expected format
    mode_map = {'auto': 'AUTO', 'manual': 'MANUAL', 'off': 'OFF'}
    esp_mode = mode_map.get(mode, mode.upper())
    
    topic = f"hotel/{room.room_number}/control/room_mode"
    try:
        mqtt_client.publish(topic, esp_mode)
        logger.info(f"[MQTT] Published room mode {esp_mode} to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_notification(message, notification_type='system', recipient=None, priority='normal', metadata=None):
    """
    Publish notification to Node-RED via MQTT.
    
    Node-RED will handle delivery via Telegram/SMS with fallback logic.
    
    Args:
        message: The notification message text
        notification_type: Type of notification (guest_credentials, alert, system)
        recipient: Dict with optional 'phone' and 'chat_id' fields
        priority: 'high' or 'normal'
        metadata: Optional dict with additional context
    
    Returns:
        bool: True if published successfully
    """
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish notification")
        return False
    
    topic = "hotel/notifications/send"
    payload = {
        'type': notification_type,
        'message': message,
        'priority': priority,
        'recipient': recipient or {},
        'metadata': metadata or {}
    }
    
    try:
        mqtt_client.publish(topic, json.dumps(payload), qos=1)
        logger.info(f"[MQTT] Published notification to {topic}: {notification_type}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Notification publish error: {e}")
        return False


def publish_alert(alert_type, data):
    """
    Publish system alert to Node-RED via MQTT.
    
    Alert types: gas, temperature, system
    
    Args:
        alert_type: The type of alert
        data: Dict with alert data
    
    Returns:
        bool: True if published successfully
    """
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish alert")
        return False
    
    topic = f"hotel/alerts/{alert_type}"
    
    try:
        mqtt_client.publish(topic, json.dumps(data), qos=1)
        logger.info(f"[MQTT] Published alert to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Alert publish error: {e}")
        return False
