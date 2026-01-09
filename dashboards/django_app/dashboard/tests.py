"""
Tests for Dashboard views and API endpoints.
"""
import json
import pytest
from django.urls import reverse


class TestDashboardViews:
    """Test dashboard main views."""

    def test_dashboard_requires_login(self, client):
        """Dashboard should redirect to login if not authenticated."""
        response = client.get('/')
        assert response.status_code == 302
        assert 'login' in response.url.lower()

    @pytest.mark.django_db
    def test_dashboard_accessible_when_logged_in(self, authenticated_client):
        """Dashboard should be accessible when logged in."""
        response = authenticated_client.get('/')
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_guest_management_requires_admin(self, client, monitor_user):
        """Guest management should require admin role."""
        client.login(username='testmonitor', password='monitorpass123')
        response = client.get(reverse('dashboard:guest_management'))
        assert response.status_code == 403


class TestRoomAPI:
    """Test room-related API endpoints."""

    @pytest.mark.django_db
    def test_rooms_api_requires_auth(self, client):
        """Rooms API should require authentication."""
        response = client.get(reverse('dashboard:api_rooms'))
        assert response.status_code == 302  # Redirect to login

    @pytest.mark.django_db
    def test_rooms_api_returns_json(self, authenticated_client, sample_room):
        """Rooms API should return JSON list of rooms."""
        response = authenticated_client.get(reverse('dashboard:api_rooms'))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'rooms' in data
        assert len(data['rooms']) >= 1


class TestGuestAPI:
    """Test kiosk integration API endpoints."""

    @pytest.mark.django_db
    def test_guest_create_api_requires_json(self, client):
        """Guest create API should require JSON body."""
        response = client.post(
            reverse('dashboard:api_guest_create'),
            content_type='application/json',
            data='{}'
        )
        # Should fail with 400 (missing fields) not 500
        assert response.status_code == 400

    @pytest.mark.django_db
    def test_guest_create_api_validates_fields(self, client):
        """Guest create API should validate required fields."""
        response = client.post(
            reverse('dashboard:api_guest_create'),
            content_type='application/json',
            data=json.dumps({
                'first_name': 'John',
                # Missing last_name, room_number, checkout_date
            })
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data

    @pytest.mark.django_db
    def test_guest_create_api_creates_user(self, client, sample_room):
        """Guest create API should create a guest user."""
        response = client.post(
            reverse('dashboard:api_guest_create'),
            content_type='application/json',
            data=json.dumps({
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john@example.com',
                'room_number': sample_room.room_number,
                'checkout_date': '2026-01-15T12:00:00'
            })
        )
        assert response.status_code == 201
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'username' in data
        assert 'password' in data
        assert data['room_number'] == sample_room.room_number

    @pytest.mark.django_db
    def test_guest_deactivate_api_requires_identifier(self, client):
        """Guest deactivate API should require username or room_number."""
        response = client.post(
            reverse('dashboard:api_guest_deactivate'),
            content_type='application/json',
            data=json.dumps({})
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data

    @pytest.mark.django_db
    def test_guest_deactivate_api_deactivates_user(self, client, guest_user):
        """Guest deactivate API should deactivate a guest."""
        response = client.post(
            reverse('dashboard:api_guest_deactivate'),
            content_type='application/json',
            data=json.dumps({
                'username': guest_user.username
            })
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True

        # Verify user is deactivated
        from accounts.models import User
        guest_user.refresh_from_db()
        assert guest_user.is_active is False


class TestNotificationAPI:
    """Test notification-related API endpoints."""

    @pytest.mark.django_db
    def test_notification_status_requires_admin(self, client, monitor_user):
        """Notification status should be accessible to admin/monitor."""
        client.login(username='testmonitor', password='monitorpass123')
        response = client.get(reverse('dashboard:api_notifications_status'))
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_notification_send_requires_admin(self, client, guest_user):
        """Notification send should require admin role."""
        client.login(username='testguest', password='guestpass123')
        response = client.post(
            reverse('dashboard:api_notifications_send'),
            content_type='application/json',
            data=json.dumps({'message': 'test'})
        )
        assert response.status_code == 403
