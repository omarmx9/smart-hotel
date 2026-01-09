"""
Tests for Kiosk views and guest flow.
"""
import json
import pytest
from django.urls import reverse, NoReverseMatch


class TestKioskURLs:
    """Test kiosk URL resolution."""

    def test_advertisement_url_resolves(self):
        """Test advertisement URL resolves."""
        try:
            url = reverse('kiosk:advertisement')
            assert url == '/'
        except NoReverseMatch:
            pytest.fail("URL kiosk:advertisement not found")

    def test_language_url_resolves(self):
        """Test language selection URL resolves."""
        try:
            url = reverse('kiosk:choose_language')
            assert '/language/' in url
        except NoReverseMatch:
            pytest.fail("URL kiosk:choose_language not found")

    def test_checkin_url_resolves(self):
        """Test checkin URL resolves."""
        try:
            url = reverse('kiosk:checkin')
            assert '/checkin/' in url
        except NoReverseMatch:
            pytest.fail("URL kiosk:checkin not found")

    def test_error_url_resolves(self):
        """Test error URL resolves."""
        try:
            url = reverse('kiosk:error')
            assert '/error/' in url
        except NoReverseMatch:
            pytest.fail("URL kiosk:error not found")


class TestPassportScan:
    """Test passport scanning functionality."""

    def test_passport_scan_api_requires_post(self, client):
        """Test passport scan API requires POST."""
        response = client.get(reverse('kiosk:upload_scan'))
        assert response.status_code in [400, 405]


class TestGuestFlow:
    """Test guest check-in flow."""

    def test_verify_info_page(self, client):
        """Test verify info page."""
        response = client.get(reverse('kiosk:verify_info'))
        # Should work or return error without session
        assert response.status_code in [200, 302, 400]


class TestEmulator:
    """Test the emulator database module."""

    def test_create_guest(self):
        """Test guest creation in emulator."""
        from kiosk import emulator as db
        
        guest = db.create_guest(
            first_name='Jane',
            last_name='Smith',
            passport_number='XY9876543',
            date_of_birth='1985-06-20'
        )
        
        assert guest['first_name'] == 'Jane'
        assert guest['last_name'] == 'Smith'
        assert guest['passport_number'] == 'XY9876543'
        assert 'id' in guest

    def test_get_or_create_guest(self):
        """Test get_or_create_guest in emulator."""
        from kiosk import emulator as db
        
        guest1 = db.get_or_create_guest(
            first_name='Bob',
            last_name='Wilson',
            passport_number='ZZ1111111'
        )
        
        guest2 = db.get_or_create_guest(
            first_name='Bob',
            last_name='Wilson',
            passport_number='ZZ1111111'
        )
        
        # Should return the same guest
        assert guest1['id'] == guest2['id']

    def test_create_reservation(self):
        """Test reservation creation in emulator."""
        from kiosk import emulator as db
        from datetime import date, timedelta
        
        guest = db.create_guest('Test', 'Guest')
        reservation = db.create_reservation(
            reservation_number='RES999',
            guest=guest,
            checkin=date.today(),
            checkout=date.today() + timedelta(days=2)
        )
        
        assert reservation['reservation_number'] == 'RES999'
        assert reservation['guest_id'] == guest['id']
        assert 'id' in reservation

    def test_get_reservation(self):
        """Test getting reservation from emulator."""
        from kiosk import emulator as db
        from datetime import date, timedelta
        
        guest = db.create_guest('Retrieve', 'Test')
        reservation = db.create_reservation(
            reservation_number='RES888',
            guest=guest,
            checkin=date.today(),
            checkout=date.today() + timedelta(days=1)
        )
        
        retrieved = db.get_reservation(reservation['id'])
        assert retrieved is not None
        assert retrieved['id'] == reservation['id']


class TestMRZParser:
    """Test MRZ parsing functionality."""

    def test_mrz_parser_module_importable(self):
        """Test MRZ parser module is importable."""
        try:
            from kiosk import mrz_parser
            assert True
        except ImportError:
            pytest.skip("mrz_parser dependencies not installed")


class TestMQTTClient:
    """Test MQTT client functionality."""

    def test_generate_rfid_token(self):
        """Test RFID token generation."""
        from kiosk.mqtt_client import generate_rfid_token
        
        token = generate_rfid_token()
        assert len(token) == 16
        assert token.isalnum()

    def test_mqtt_functions_exist(self):
        """Test MQTT client module has required functions."""
        from kiosk import mqtt_client
        
        assert hasattr(mqtt_client, 'generate_rfid_token')
        assert hasattr(mqtt_client, 'publish_rfid_token')

    def test_publish_rfid_token_returns_dict(self):
        """Test RFID token publish returns dict."""
        import os
        os.environ['MQTT_ENABLED'] = 'false'
        
        from kiosk.mqtt_client import publish_rfid_token
        
        result = publish_rfid_token(
            guest_id=1,
            reservation_id=1,
            room_number='101'
        )
        
        assert isinstance(result, dict)
        assert 'token' in result
