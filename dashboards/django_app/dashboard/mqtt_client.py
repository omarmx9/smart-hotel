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
        
        # Subscribe to all room telemetry topics
        # Topic structure: /hotel/<room_no>/telemetry/<sensor>
        client.subscribe("/hotel/+/telemetry/temperature")
        client.subscribe("/hotel/+/telemetry/humidity")
        client.subscribe("/hotel/+/telemetry/luminosity")
        client.subscribe("/hotel/+/telemetry/gas")
        client.subscribe("/hotel/+/telemetry/heating")
        client.subscribe("/hotel/+/telemetry/climate_mode")
        client.subscribe("/hotel/+/telemetry/fan_speed")
        
        logger.info("[MQTT] Subscribed to room telemetry topics")
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
        # Topic structure: /hotel/<room_no>/telemetry/<sensor>
        # After split: ['', 'hotel', '<room_no>', 'telemetry', '<sensor>']
        if len(topic_parts) >= 5 and topic_parts[1] == 'hotel' and topic_parts[3] == 'telemetry':
            room_number = topic_parts[2]
            sensor_type = topic_parts[4]
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
            elif sensor_type == 'luminosity':
                room.luminosity = int(payload)
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
            
            logger.debug(f"[MQTT] {room_number}/{sensor_type}: {payload}")
            
    except Exception as e:
        logger.error(f"[MQTT] Error processing message: {e}")


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
    """Publish luminosity level to MQTT broker"""
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    topic = f"/hotel/{room.room_number}/control/luminosity"
    try:
        mqtt_client.publish(topic, str(level))
        logger.info(f"[MQTT] Published luminosity {level} to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False


def publish_light_mode(room, mode):
    """Publish light mode (auto/manual) to MQTT broker"""
    global mqtt_client
    
    if mqtt_client is None or not mqtt_connected:
        logger.warning("[MQTT] Client not connected, cannot publish")
        return False
    
    topic = f"/hotel/{room.room_number}/control/light_mode"
    try:
        mqtt_client.publish(topic, mode)
        logger.info(f"[MQTT] Published light mode {mode} to {topic}")
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
