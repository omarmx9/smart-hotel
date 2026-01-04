"""
MQTT Client for Kiosk application.
Publishes RFID access tokens and other messages to the hotel MQTT broker.
"""
import os
import json
import secrets
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# MQTT Configuration from environment
MQTT_HOST = os.environ.get('MQTT_HOST', 'mosquitto')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
MQTT_USER = os.environ.get('MQTT_USER', '')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', '')
MQTT_ENABLED = os.environ.get('MQTT_ENABLED', 'true').lower() in ('1', 'true', 'yes')

# Topic definitions
RFID_PROGRAM_TOPIC = 'hotel/kiosk/rfid/program'
ACCESS_EVENTS_TOPIC = 'hotel/kiosk/access/events'


def generate_rfid_token():
    """
    Generate a secure random RFID access token.
    Returns a 16-character hex token.
    """
    return secrets.token_hex(8).upper()


def get_mqtt_client():
    """
    Get a configured MQTT client instance.
    Returns None if MQTT is not available or disabled.
    """
    if not MQTT_ENABLED:
        logger.info("MQTT is disabled")
        return None
    
    try:
        import paho.mqtt.client as mqtt
        
        client = mqtt.Client(client_id=f"kiosk-{secrets.token_hex(4)}")
        
        if MQTT_USER and MQTT_PASSWORD:
            client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        
        return client
    except ImportError:
        logger.warning("paho-mqtt not installed, MQTT publishing disabled")
        return None
    except Exception as e:
        logger.error(f"Failed to create MQTT client: {e}")
        return None


def publish_rfid_token(guest_id, reservation_id, room_number, token=None, checkin=None, checkout=None):
    """
    Publish an RFID programming request to the MQTT broker.
    The RFID writer device subscribes to this topic and programs keycards.
    
    Args:
        guest_id: The guest's ID
        reservation_id: The reservation ID
        room_number: The assigned room number
        token: Optional pre-generated token. If None, a new one is generated.
        checkin: Check-in date (for access validity)
        checkout: Check-out date (for access expiry)
    
    Returns:
        dict with 'success', 'token', and optional 'error' keys
    """
    if token is None:
        token = generate_rfid_token()
    
    payload = {
        'action': 'program',
        'token': token,
        'guest_id': guest_id,
        'reservation_id': reservation_id,
        'room_number': room_number,
        'checkin': str(checkin) if checkin else None,
        'checkout': str(checkout) if checkout else None,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    client = get_mqtt_client()
    if not client:
        logger.warning("MQTT not available, token generated but not published")
        return {
            'success': True,
            'token': token,
            'published': False,
            'message': 'MQTT not available'
        }
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        result = client.publish(RFID_PROGRAM_TOPIC, json.dumps(payload), qos=1)
        client.disconnect()
        
        if result.rc == 0:
            logger.info(f"Published RFID token for room {room_number}: {token[:4]}****")
            return {
                'success': True,
                'token': token,
                'published': True
            }
        else:
            logger.error(f"MQTT publish failed with rc={result.rc}")
            return {
                'success': True,
                'token': token,
                'published': False,
                'error': f'Publish failed with code {result.rc}'
            }
    except Exception as e:
        logger.error(f"MQTT publish error: {e}")
        return {
            'success': True,
            'token': token,
            'published': False,
            'error': str(e)
        }


def publish_access_event(event_type, guest_id=None, reservation_id=None, room_number=None, access_methods=None):
    """
    Publish an access event (e.g., check-in, access method selection).
    
    Args:
        event_type: Type of event (e.g., 'checkin', 'access_selected', 'checkout')
        guest_id: Optional guest ID
        reservation_id: Optional reservation ID
        room_number: Optional room number
        access_methods: List of selected access methods
    """
    payload = {
        'event': event_type,
        'guest_id': guest_id,
        'reservation_id': reservation_id,
        'room_number': room_number,
        'access_methods': access_methods or [],
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    client = get_mqtt_client()
    if not client:
        return {'success': False, 'error': 'MQTT not available'}
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        result = client.publish(ACCESS_EVENTS_TOPIC, json.dumps(payload), qos=0)
        client.disconnect()
        
        return {'success': result.rc == 0}
    except Exception as e:
        logger.error(f"MQTT event publish error: {e}")
        return {'success': False, 'error': str(e)}


def revoke_rfid_token(token, room_number, reason='checkout'):
    """
    Publish an RFID revocation request (e.g., when card is reported stolen).
    
    Args:
        token: The token to revoke
        room_number: The room number
        reason: Reason for revocation ('checkout', 'stolen', 'lost', 'expired')
    
    Returns:
        dict with 'success' and optional 'error' keys
    """
    payload = {
        'action': 'revoke',
        'token': token,
        'room_number': room_number,
        'reason': reason,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    client = get_mqtt_client()
    if not client:
        return {'success': False, 'error': 'MQTT not available'}
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        result = client.publish(RFID_PROGRAM_TOPIC, json.dumps(payload), qos=1)
        client.disconnect()
        
        return {'success': result.rc == 0}
    except Exception as e:
        logger.error(f"MQTT revoke error: {e}")
        return {'success': False, 'error': str(e)}
