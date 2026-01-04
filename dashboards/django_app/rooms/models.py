from django.db import models
from django.utils import timezone


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
    
    room_number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VACANT)
    
    # Sensor readings
    temperature = models.FloatField(default=22.0)
    humidity = models.FloatField(default=50.0)
    luminosity = models.IntegerField(default=0)  # 0=off, 1=one light, 2=two lights
    light_mode = models.CharField(max_length=20, choices=LIGHT_CHOICES, default=LIGHT_AUTO)
    gas_level = models.IntegerField(default=0)
    
    # Climate control settings
    climate_mode = models.CharField(max_length=20, choices=CLIMATE_CHOICES, default=CLIMATE_AUTO)
    target_temperature = models.FloatField(default=22.0)
    fan_speed = models.CharField(max_length=20, choices=FAN_CHOICES, default=FAN_MEDIUM)
    heating_status = models.BooleanField(default=False)
    
    # MQTT topic prefix for this room
    mqtt_topic_prefix = models.CharField(max_length=100, blank=True)
    
    last_update = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['room_number']
    
    def save(self, *args, **kwargs):
        if not self.mqtt_topic_prefix:
            self.mqtt_topic_prefix = f"/hotel/{self.room_number}"
        super().save(*args, **kwargs)
    
    @property
    def luminosity_display(self):
        """Display luminosity as readable text"""
        if self.light_mode == self.LIGHT_AUTO:
            return 'Auto'
        elif self.luminosity == 0:
            return 'Off'
        elif self.luminosity == 1:
            return '1 Light'
        else:
            return '2 Lights'
    
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
        return {
            'id': self.id,
            'room_number': self.room_number,
            'floor': self.floor,
            'status': self.status,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'luminosity': self.luminosity,
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
            luminosity=room.luminosity,
            gas_level=room.gas_level
        )
    
    @classmethod
    def cleanup_old_records(cls, days=7):
        """Remove records older than specified days"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        cls.objects.filter(timestamp__lt=cutoff).delete()
