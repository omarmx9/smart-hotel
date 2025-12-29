"""InfluxDB Client for Smart Hotel Dashboard"""

from influxdb_client import InfluxDBClient
from django.conf import settings
import threading
import logging
import time

logger = logging.getLogger(__name__)

influx_client = None
query_thread = None
running = False


def get_influx_client():
    global influx_client
    return influx_client


def is_connected():
    global influx_client
    if influx_client is None:
        return False
    try:
        influx_client.ping()
        return True
    except Exception:
        return False


def query_sensor_data():
    """Query InfluxDB for sensor data and update room models"""
    global influx_client, running
    
    from rooms.models import Room, SensorHistory
    
    query_api = influx_client.query_api()
    
    # Map of measurements to room fields
    sensor_mappings = {
        'temperature': 'temperature',
        'humidity': 'humidity',
        'luminosity': 'luminosity',
        'gas': 'gas_level',
    }
    
    while running:
        try:
            rooms = Room.objects.all()
            
            for room in rooms:
                for measurement, field in sensor_mappings.items():
                    # Query latest value for this room/sensor
                    query = f'''
                    from(bucket: "{settings.INFLUX_BUCKET}")
                        |> range(start: -5m)
                        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
                        |> filter(fn: (r) => r["room"] == "{room.room_number}")
                        |> last()
                    '''
                    
                    try:
                        tables = query_api.query(query)
                        for table in tables:
                            for record in table.records:
                                value = record.get_value()
                                if value is not None:
                                    if field in ['temperature', 'humidity']:
                                        setattr(room, field, float(value))
                                    else:
                                        setattr(room, field, int(value))
                    except Exception as e:
                        logger.debug(f"[InfluxDB] No data for {room.room_number}/{measurement}: {e}")
                
                # Also check heating status
                heating_query = f'''
                from(bucket: "{settings.INFLUX_BUCKET}")
                    |> range(start: -5m)
                    |> filter(fn: (r) => r["_measurement"] == "heating")
                    |> filter(fn: (r) => r["room"] == "{room.room_number}")
                    |> last()
                '''
                
                try:
                    tables = query_api.query(heating_query)
                    for table in tables:
                        for record in table.records:
                            value = record.get_value()
                            if value is not None:
                                room.heating_status = str(value).lower() in ['true', '1', 'on']
                except Exception as e:
                    logger.debug(f"[InfluxDB] No heating data for {room.room_number}: {e}")
                
                room.save()
            
            # Record history periodically
            for room in rooms:
                SensorHistory.record(room)
            
            logger.debug("[InfluxDB] Updated room sensor data")
            
        except Exception as e:
            logger.error(f"[InfluxDB] Error querying data: {e}")
        
        # Poll every 10 seconds
        time.sleep(10)


def start_influx_client():
    """Start the InfluxDB client and polling thread"""
    global influx_client, query_thread, running
    
    if influx_client is not None:
        logger.info("[InfluxDB] Client already running")
        return
    
    try:
        influx_client = InfluxDBClient(
            url=settings.INFLUX_URL,
            token=settings.INFLUX_TOKEN,
            org=settings.INFLUX_ORG
        )
        
        # Test connection
        if influx_client.ping():
            logger.info(f"[InfluxDB] Connected to {settings.INFLUX_URL}")
            running = True
            
            # Start polling thread
            query_thread = threading.Thread(target=query_sensor_data, daemon=True)
            query_thread.start()
            logger.info("[InfluxDB] Started polling thread")
        else:
            logger.error("[InfluxDB] Failed to connect")
            influx_client = None
            
    except Exception as e:
        logger.error(f"[InfluxDB] Error starting client: {e}")
        influx_client = None


def stop_influx_client():
    """Stop the InfluxDB client"""
    global influx_client, running
    
    running = False
    
    if influx_client is not None:
        influx_client.close()
        influx_client = None
        logger.info("[InfluxDB] Client stopped")


def write_setpoint(room_number: str, setpoint: float):
    """Write temperature setpoint to InfluxDB"""
    global influx_client
    
    if influx_client is None:
        logger.error("[InfluxDB] Client not connected")
        return False
    
    try:
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        
        write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        
        point = Point("setpoint") \
            .tag("room", room_number) \
            .field("value", float(setpoint))
        
        write_api.write(bucket=settings.INFLUX_BUCKET, record=point)
        logger.info(f"[InfluxDB] Set room {room_number} setpoint to {setpoint}")
        return True
        
    except Exception as e:
        logger.error(f"[InfluxDB] Error writing setpoint: {e}")
        return False


def get_room_history(room_number: str, hours: int = 24):
    """Get sensor history for a room from InfluxDB"""
    global influx_client
    
    if influx_client is None:
        return []
    
    try:
        query_api = influx_client.query_api()
        
        query = f'''
        from(bucket: "{settings.INFLUX_BUCKET}")
            |> range(start: -{hours}h)
            |> filter(fn: (r) => r["room"] == "{room_number}")
            |> filter(fn: (r) => r["_measurement"] == "temperature" or r["_measurement"] == "humidity")
            |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
            |> yield(name: "mean")
        '''
        
        tables = query_api.query(query)
        
        history = []
        for table in tables:
            for record in table.records:
                history.append({
                    'time': record.get_time().isoformat(),
                    'measurement': record.get_measurement(),
                    'value': record.get_value()
                })
        
        return history
        
    except Exception as e:
        logger.error(f"[InfluxDB] Error getting history: {e}")
        return []
