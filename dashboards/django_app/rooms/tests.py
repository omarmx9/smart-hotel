"""
Tests for Room model and sensor data.
"""
import pytest
from django.utils import timezone


class TestRoomModel:
    """Test Room model."""

    @pytest.mark.django_db
    def test_create_room(self):
        """Test creating a room."""
        from rooms.models import Room
        
        room = Room.objects.create(
            room_number='101',
            floor=1,
            status=Room.STATUS_VACANT
        )
        assert room.room_number == '101'
        assert room.floor == 1
        assert room.status == Room.STATUS_VACANT

    @pytest.mark.django_db
    def test_room_status_choices(self):
        """Test room status transitions."""
        from rooms.models import Room
        
        room = Room.objects.create(
            room_number='102',
            floor=1,
            status=Room.STATUS_VACANT
        )
        
        # Mark as occupied
        room.status = Room.STATUS_OCCUPIED
        room.save()
        room.refresh_from_db()
        assert room.status == Room.STATUS_OCCUPIED

    @pytest.mark.django_db
    def test_room_sensor_defaults(self):
        """Test room sensor default values."""
        from rooms.models import Room
        
        room = Room.objects.create(
            room_number='103',
            floor=1
        )
        
        # Check sensor defaults
        assert room.temperature == 22.0
        assert room.humidity == 50.0

    @pytest.mark.django_db
    def test_room_string_representation(self):
        """Test room string representation."""
        from rooms.models import Room
        
        room = Room.objects.create(
            room_number='104',
            floor=2
        )
        
        str_repr = str(room)
        assert '104' in str_repr


class TestSensorHistory:
    """Test SensorHistory model."""

    @pytest.mark.django_db
    def test_create_sensor_history(self):
        """Test creating sensor history entry."""
        from rooms.models import Room, SensorHistory
        
        room = Room.objects.create(
            room_number='105',
            floor=1
        )
        
        history = SensorHistory.objects.create(
            room=room,
            temperature=22.5,
            humidity=45.0,
            luminosity=80
        )
        
        assert history.room == room
        assert history.temperature == 22.5
        assert history.humidity == 45.0
        assert history.timestamp is not None

    @pytest.mark.django_db
    def test_sensor_history_ordering(self):
        """Test sensor history is ordered by timestamp."""
        from rooms.models import Room, SensorHistory
        import time
        
        room = Room.objects.create(
            room_number='106',
            floor=1
        )
        
        # Create multiple entries
        SensorHistory.objects.create(room=room, temperature=20.0, humidity=50.0)
        time.sleep(0.1)
        SensorHistory.objects.create(room=room, temperature=21.0, humidity=50.0)
        time.sleep(0.1)
        SensorHistory.objects.create(room=room, temperature=22.0, humidity=50.0)
        
        # Get latest
        histories = SensorHistory.objects.filter(room=room).order_by('-timestamp')
        assert histories.first().temperature == 22.0
