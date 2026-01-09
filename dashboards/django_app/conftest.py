"""
Pytest configuration and fixtures for Dashboard tests.
"""
import os
import pytest
from django.test import Client

# Set up Django settings before importing models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_hotel.settings')


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def authenticated_client(db):
    """Django test client with authenticated admin user."""
    from accounts.models import User
    
    client = Client()
    user = User.objects.create_user(
        username='testadmin',
        password='testpass123',
        email='admin@test.com',
        role=User.ROLE_ADMIN
    )
    client.login(username='testadmin', password='testpass123')
    return client


@pytest.fixture
def guest_user(db):
    """Create a guest user for testing."""
    from accounts.models import User
    from rooms.models import Room
    
    # Create a room first
    room = Room.objects.create(
        room_number='101',
        floor=1,
        status=Room.STATUS_VACANT
    )
    
    user = User.objects.create_user(
        username='testguest',
        password='guestpass123',
        email='guest@test.com',
        role=User.ROLE_GUEST,
        assigned_room=room
    )
    return user


@pytest.fixture
def monitor_user(db):
    """Create a monitor user for testing."""
    from accounts.models import User
    
    user = User.objects.create_user(
        username='testmonitor',
        password='monitorpass123',
        email='monitor@test.com',
        role=User.ROLE_MONITOR
    )
    return user


@pytest.fixture
def sample_room(db):
    """Create a sample room for testing."""
    from rooms.models import Room
    
    return Room.objects.create(
        room_number='102',
        floor=1,
        status=Room.STATUS_VACANT
    )
