"""
Pytest configuration and fixtures for Kiosk tests.
"""
import os
import pytest
from django.test import Client

# Set up Django settings before importing models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiosk_project.settings')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('DEBUG', '1')


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def session_client():
    """Django test client with session."""
    client = Client()
    # Initialize session
    session = client.session
    session.save()
    return client


@pytest.fixture
def mrz_data():
    """Sample MRZ extracted data."""
    return {
        'first_name': 'JOHN',
        'last_name': 'DOE',
        'passport_number': 'AB1234567',
        'nationality': 'USA',
        'date_of_birth': '1990-01-15',
        'sex': 'M',
        'expiry_date': '2030-01-15',
        'document_type': 'P'
    }


@pytest.fixture
def sample_guest():
    """Sample guest data from emulator."""
    from kiosk import emulator as db
    return db.create_guest(
        first_name='John',
        last_name='Doe',
        passport_number='AB1234567',
        date_of_birth='1990-01-15'
    )


@pytest.fixture
def sample_reservation(sample_guest):
    """Sample reservation data from emulator."""
    from kiosk import emulator as db
    from datetime import date, timedelta
    
    return db.create_reservation(
        reservation_number='RES123456',
        guest=sample_guest,
        checkin=date.today(),
        checkout=date.today() + timedelta(days=3),
        room_count=1,
        people_count=1
    )
