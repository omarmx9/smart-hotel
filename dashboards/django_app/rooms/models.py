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
    
    room_number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VACANT)
    
    # Sensor readings
    temperature = models.FloatField(default=22.0)
    humidity = models.FloatField(default=50.0)
    luminosity = models.IntegerField(default=0)
    gas_level = models.IntegerField(default=0)
    
    # Control settings
    target_temperature = models.FloatField(default=22.0)
    heating_status = models.BooleanField(default=False)
    
    # MQTT topic prefix for this room
    mqtt_topic_prefix = models.CharField(max_length=100, blank=True)
    
    last_update = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['room_number']
    
    def save(self, *args, **kwargs):
        if not self.mqtt_topic_prefix:
            self.mqtt_topic_prefix = f"hotel/room/{self.room_number}"
        super().save(*args, **kwargs)
    
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
            'gas_level': self.gas_level,
            'target_temperature': self.target_temperature,
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
