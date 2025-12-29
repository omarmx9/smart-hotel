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
        
        # Subscribe to all room topics
        client.subscribe("hotel/room/+/temperature")
        client.subscribe("hotel/room/+/humidity")
        client.subscribe("hotel/room/+/luminosity")
        client.subscribe("hotel/room/+/gas")
        client.subscribe("hotel/room/+/heating")
        
        logger.info("[MQTT] Subscribed to room topics")
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
        if len(topic_parts) >= 4 and topic_parts[0] == 'hotel' and topic_parts[1] == 'room':
            room_number = topic_parts[2]
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
            elif sensor_type == 'luminosity':
                room.luminosity = int(payload)
            elif sensor_type == 'gas':
                room.gas_level = int(payload)
            elif sensor_type == 'heating':
                room.heating_status = payload.lower() in ['true', '1', 'on']
            
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
    
    topic = f"{room.mqtt_topic_prefix}/control"
    try:
        mqtt_client.publish(topic, str(temperature))
        mqtt_client.publish(f"{room.mqtt_topic_prefix}/target", str(temperature))
        logger.info(f"[MQTT] Published target {temperature}C to {topic}")
        return True
    except Exception as e:
        logger.error(f"[MQTT] Publish error: {e}")
        return False
