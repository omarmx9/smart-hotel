from django.db import models
from django.utils import timezone
from datetime import timedelta


class Room(models.Model):
    """Hotel room model with sensor data"""
    
    STATUS_VACANT = 'vacant'
    STATUS_OCCUPIED = 'occupied'
    STATUS_MAINTENANCE = 'maintenance'
    
    STATUS_CHOICES = [
        (STATUS_VACANT, 'Vacant'),
        (STATUS_OCCUPIED, 'Occupied'),
        (STATUS_MAINTENANCE, 'Maintenance'),
    ]
    
    # Climate control modes
    CLIMATE_AUTO = 'auto'
    CLIMATE_MANUAL = 'manual'
    CLIMATE_OFF = 'off'
    
    CLIMATE_CHOICES = [
        (CLIMATE_AUTO, 'Automatic'),
        (CLIMATE_MANUAL, 'Manual'),
        (CLIMATE_OFF, 'Off'),
    ]
    
    # Fan speed options for manual mode
    FAN_LOW = 'low'
    FAN_MEDIUM = 'medium'
    FAN_HIGH = 'high'
    
    FAN_CHOICES = [
        (FAN_LOW, 'Low'),
        (FAN_MEDIUM, 'Medium'),
        (FAN_HIGH, 'High'),
    ]
    
    # Light control modes
    LIGHT_AUTO = 'auto'
    LIGHT_MANUAL = 'manual'
    
    LIGHT_CHOICES = [
        (LIGHT_AUTO, 'Automatic'),
        (LIGHT_MANUAL, 'Manual'),
    ]
    
    # Sensor online timeout in seconds
    SENSOR_OFFLINE_TIMEOUT = 30
    
    room_number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VACANT)
    
    # Sensor readings
    temperature = models.FloatField(default=22.0)
    humidity = models.FloatField(default=50.0)
    luminosity = models.IntegerField(default=0)  # 0=off, 1=one light, 2=two lights (calculated from LED states)
    ldr_percentage = models.IntegerField(default=0)  # Light sensor reading (0-100%)
    light_mode = models.CharField(max_length=20, choices=LIGHT_CHOICES, default=LIGHT_AUTO)
    gas_level = models.IntegerField(default=0)
    
    # LED status (received from ESP32)
    led1_status = models.BooleanField(default=False)
    led2_status = models.BooleanField(default=False)
    
    # Climate control settings
    climate_mode = models.CharField(max_length=20, choices=CLIMATE_CHOICES, default=CLIMATE_AUTO)
    target_temperature = models.FloatField(default=22.0)
    fan_speed = models.CharField(max_length=20, choices=FAN_CHOICES, default=FAN_MEDIUM)
    heating_status = models.BooleanField(default=False)
    
    # Door status (for access control)
    door_open = models.BooleanField(default=False)
    door_opened_at = models.DateTimeField(null=True, blank=True)
    
    # MQTT topic prefix for this room
    mqtt_topic_prefix = models.CharField(max_length=100, blank=True)
    
    # Timestamps for sensor and last update tracking
    sensor_last_update = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['room_number']
    
    def save(self, *args, **kwargs):
        if not self.mqtt_topic_prefix:
            self.mqtt_topic_prefix = f"/hotel/{self.room_number}"
        super().save(*args, **kwargs)
    
    @property
    def is_sensor_online(self):
        """Check if sensor is online based on last update time (30 second timeout)"""
        if not self.sensor_last_update:
            return False
        timeout = timedelta(seconds=self.SENSOR_OFFLINE_TIMEOUT)
        return (timezone.now() - self.sensor_last_update) <= timeout
    
    @property
    def sensor_status(self):
        """Return sensor status as string"""
        return 'online' if self.is_sensor_online else 'offline'
    
    @property
    def seconds_since_update(self):
        """Return seconds since last sensor update"""
        if not self.sensor_last_update:
            return None
        delta = timezone.now() - self.sensor_last_update
        return int(delta.total_seconds())
    
    def update_sensor_timestamp(self):
        """Update the sensor last update timestamp"""
        self.sensor_last_update = timezone.now()
    
    def open_door(self, duration_seconds=5):
        """Open the door for specified duration"""
        self.door_open = True
        self.door_opened_at = timezone.now()
        self.save()
    
    def close_door(self):
        """Close the door"""
        self.door_open = False
        self.door_opened_at = None
        self.save()
    
    def check_door_auto_close(self):
        """Check if door should auto-close (after 5 seconds)"""
        if self.door_open and self.door_opened_at:
            elapsed = (timezone.now() - self.door_opened_at).total_seconds()
            if elapsed >= 5:
                self.close_door()
                return True
        return False
    
    @property
    def luminosity_display(self):
        """Display luminosity as readable text based on LED states"""
        if self.light_mode == self.LIGHT_AUTO:
            return 'Auto'
        # Calculate display from LED states
        if self.led1_status and self.led2_status:
            return '2 Lights'
        elif self.led1_status or self.led2_status:
            return '1 Light'
        else:
            return 'Off'
    
    @property
    def led_count(self):
        """Return the number of LEDs currently on"""
        count = 0
        if self.led1_status:
            count += 1
        if self.led2_status:
            count += 1
        return count
    
    @property
    def temperature_alert(self):
        if self.temperature > 30:
            return 'danger'
        elif self.temperature > 26 or self.temperature < 16:
            return 'warning'
        return 'normal'
    
    @property
    def gas_alert(self):
        if self.gas_level > 600:
            return 'danger'
        elif self.gas_level > 400:
            return 'warning'
        return 'normal'
    
    def to_dict(self):
        # Check if door should auto-close
        self.check_door_auto_close()
        
        return {
            'id': self.id,
            'room_number': self.room_number,
            'floor': self.floor,
            'status': self.status,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'luminosity': self.led_count,  # Calculated from LED states
            'ldr_percentage': self.ldr_percentage,
            'led1_status': self.led1_status,
            'led2_status': self.led2_status,
            'luminosity_display': self.luminosity_display,
            'light_mode': self.light_mode,
            'gas_level': self.gas_level,
            'climate_mode': self.climate_mode,
            'target_temperature': self.target_temperature,
            'fan_speed': self.fan_speed,
            'heating_status': self.heating_status,
            'temperature_alert': self.temperature_alert,
            'gas_alert': self.gas_alert,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            # Sensor online/offline status
            'sensor_online': self.is_sensor_online,
            'sensor_status': self.sensor_status,
            'sensor_last_update': self.sensor_last_update.isoformat() if self.sensor_last_update else None,
            'seconds_since_update': self.seconds_since_update,
            # Door status
            'door_open': self.door_open,
            'door_opened_at': self.door_opened_at.isoformat() if self.door_opened_at else None,
        }
    
    def __str__(self):
        return f"Room {self.room_number}"


class SensorHistory(models.Model):
    """Historical sensor data for charts"""
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='sensor_history')
    temperature = models.FloatField()
    humidity = models.FloatField()
    luminosity = models.IntegerField(default=0)
    gas_level = models.IntegerField(default=0)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'
    
    @classmethod
    def record(cls, room):
        """Record current sensor values for a room"""
        return cls.objects.create(
            room=room,
            temperature=room.temperature,
            humidity=room.humidity,
            luminosity=room.ldr_percentage,  # Store LDR percentage reading
            gas_level=room.gas_level
        )
    
    @classmethod
    def cleanup_old_records(cls, days=7):
        """Remove records older than specified days"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        cls.objects.filter(timestamp__lt=cutoff).delete()


class AccessLog(models.Model):
    """Access log for face ID authentication events"""
    
    ACCESS_SUCCESS = 'success'
    ACCESS_DENIED = 'denied'
    ACCESS_UNKNOWN = 'unknown'
    
    ACCESS_RESULT_CHOICES = [
        (ACCESS_SUCCESS, 'Success'),
        (ACCESS_DENIED, 'Denied'),
        (ACCESS_UNKNOWN, 'Unknown'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='access_logs', null=True, blank=True)
    device_id = models.CharField(max_length=50, blank=True)  # ESP32-CAM device ID
    name = models.CharField(max_length=100)  # Person's name from face recognition
    confidence = models.FloatField(default=0.0)  # Recognition confidence (0.0 - 1.0)
    result = models.CharField(max_length=20, choices=ACCESS_RESULT_CHOICES, default=ACCESS_UNKNOWN)
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Door action taken
    door_opened = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'
    
    def __str__(self):
        return f"{self.name} - {self.result} at {self.room or self.device_id} ({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')})"
    
    def to_dict(self):
        return {
            'id': self.id,
            'room_number': self.room.room_number if self.room else None,
            'device_id': self.device_id,
            'name': self.name,
            'confidence': self.confidence,
            'result': self.result,
            'timestamp': self.timestamp.isoformat(),
            'timestamp_display': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'door_opened': self.door_opened,
        }
    
    @classmethod
    def log_access(cls, room=None, device_id='', name='Unknown', confidence=0.0, result='unknown', door_opened=False):
        """Create a new access log entry"""
        return cls.objects.create(
            room=room,
            device_id=device_id,
            name=name,
            confidence=confidence,
            result=result,
            door_opened=door_opened
        )
    
    @classmethod
    def get_recent_logs(cls, room=None, limit=50):
        """Get recent access logs, optionally filtered by room"""
        qs = cls.objects.all()
        if room:
            qs = qs.filter(room=room)
        return qs[:limit]
    
    @classmethod
    def cleanup_old_records(cls, days=30):
        """Remove records older than specified days"""
        cutoff = timezone.now() - timedelta(days=days)
        cls.objects.filter(timestamp__lt=cutoff).delete()
