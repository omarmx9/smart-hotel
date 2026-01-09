"""
Tests for User model and authentication.
"""
import pytest
from django.utils import timezone
from datetime import timedelta


class TestUserModel:
    """Test custom User model."""

    @pytest.mark.django_db
    def test_create_admin_user(self):
        """Test creating an admin user."""
        from accounts.models import User
        
        user = User.objects.create_user(
            username='admin',
            password='adminpass',
            email='admin@test.com',
            role=User.ROLE_ADMIN
        )
        assert user.role == User.ROLE_ADMIN
        assert user.is_admin is True
        assert user.can_control is True
        assert user.can_view_all_rooms is True

    @pytest.mark.django_db
    def test_create_monitor_user(self):
        """Test creating a monitor user."""
        from accounts.models import User
        
        user = User.objects.create_user(
            username='monitor',
            password='monitorpass',
            email='monitor@test.com',
            role=User.ROLE_MONITOR
        )
        assert user.role == User.ROLE_MONITOR
        assert user.is_admin is False
        assert user.can_control is False
        assert user.can_view_all_rooms is True

    @pytest.mark.django_db
    def test_create_guest_user(self):
        """Test creating a guest user."""
        from accounts.models import User
        
        user = User.objects.create_user(
            username='guest',
            password='guestpass',
            email='guest@test.com',
            role=User.ROLE_GUEST
        )
        assert user.role == User.ROLE_GUEST
        assert user.is_admin is False
        assert user.is_guest is True
        assert user.can_view_all_rooms is False

    @pytest.mark.django_db
    def test_guest_expiration(self):
        """Test guest account expiration."""
        from accounts.models import User
        
        # Create expired guest
        user = User.objects.create_user(
            username='expiredguest',
            password='guestpass',
            email='expired@test.com',
            role=User.ROLE_GUEST,
            expires_at=timezone.now() - timedelta(days=1)
        )
        assert user.is_expired is True

        # Create non-expired guest
        user2 = User.objects.create_user(
            username='activequest',
            password='guestpass',
            email='active@test.com',
            role=User.ROLE_GUEST,
            expires_at=timezone.now() + timedelta(days=1)
        )
        assert user2.is_expired is False

    @pytest.mark.django_db
    def test_guest_room_access(self):
        """Test guest can only access assigned room."""
        from accounts.models import User
        from rooms.models import Room
        
        room1 = Room.objects.create(room_number='101', floor=1)
        room2 = Room.objects.create(room_number='102', floor=1)
        
        guest = User.objects.create_user(
            username='guest',
            password='guestpass',
            email='guest@test.com',
            role=User.ROLE_GUEST,
            assigned_room=room1
        )
        
        accessible_rooms = guest.get_accessible_rooms()
        assert room1 in accessible_rooms
        assert room2 not in accessible_rooms


class TestAuthentication:
    """Test authentication flows."""

    @pytest.mark.django_db
    def test_login_page_accessible(self, client):
        """Test login page is accessible."""
        from django.urls import reverse
        
        response = client.get(reverse('accounts:login'))
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_login_with_valid_credentials(self, client):
        """Test login with valid credentials."""
        from accounts.models import User
        from django.urls import reverse
        
        User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@test.com'
        )
        
        response = client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        # Should redirect after successful login
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_login_with_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        from django.urls import reverse
        
        response = client.post(reverse('accounts:login'), {
            'username': 'nonexistent',
            'password': 'wrongpass'
        })
        # Should stay on login page with error
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_expired_user_is_marked_expired(self, client):
        """Test expired users are correctly marked as expired."""
        from accounts.models import User
        
        user = User.objects.create_user(
            username='expireduser',
            password='testpass123',
            email='expired@test.com',
            role=User.ROLE_GUEST,
            expires_at=timezone.now() - timedelta(days=1)
        )
        
        # User should be marked as expired
        assert user.is_expired is True
        
        # Non-expired user should not be marked as expired
        user2 = User.objects.create_user(
            username='activeuser',
            password='testpass123',
            email='active@test.com',
            role=User.ROLE_GUEST,
            expires_at=timezone.now() + timedelta(days=1)
        )
        assert user2.is_expired is False
