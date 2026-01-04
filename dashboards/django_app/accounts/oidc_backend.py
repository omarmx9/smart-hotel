"""
Custom OIDC Authentication Backend for Authentik Integration

This backend handles authentication via Authentik OIDC and maps
Authentik groups to Django user roles.
"""

from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AuthentikOIDCBackend(OIDCAuthenticationBackend):
    """
    Custom OIDC backend for Authentik that:
    - Maps Authentik groups to user roles (admin, monitor, guest)
    - Syncs user profile information from Authentik claims
    - Handles room assignments for guest users via custom claims
    """
    
    def create_user(self, claims):
        """Create a new user from OIDC claims"""
        user = super().create_user(claims)
        self.update_user_from_claims(user, claims)
        return user
    
    def update_user(self, user, claims):
        """Update existing user from OIDC claims"""
        self.update_user_from_claims(user, claims)
        return user
    
    def update_user_from_claims(self, user, claims):
        """Sync user attributes from Authentik claims"""
        from rooms.models import Room
        
        # Update basic user info
        user.email = claims.get('email', user.email)
        user.first_name = claims.get('given_name', user.first_name)
        user.last_name = claims.get('family_name', user.last_name)
        user.phone_number = claims.get('phone_number', user.phone_number or '')
        
        # Map Authentik groups to roles
        groups = claims.get('groups', [])
        user.role = self._get_role_from_groups(groups)
        
        # Handle superuser/staff status based on role
        if user.role == 'admin':
            user.is_staff = True
        else:
            user.is_staff = False
        
        # Handle room assignment from custom claim (for guests)
        room_number = claims.get('room_number') or claims.get('assigned_room')
        if room_number and user.role == 'guest':
            try:
                room = Room.objects.get(room_number=room_number)
                user.assigned_room = room
            except Room.DoesNotExist:
                logger.warning(f"Room {room_number} not found for user {user.username}")
                user.assigned_room = None
        
        # Handle expiration from custom claim (for guests)
        expires_at = claims.get('expires_at')
        if expires_at:
            from django.utils import timezone
            from datetime import datetime
            try:
                if isinstance(expires_at, str):
                    user.expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                elif isinstance(expires_at, (int, float)):
                    user.expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse expires_at claim: {e}")
        
        user.save()
        return user
    
    def _get_role_from_groups(self, groups):
        """
        Map Authentik groups to user roles.
        
        Expected Authentik groups:
        - 'smart-hotel-admins' or 'hotel_admin' -> admin
        - 'smart-hotel-monitors' or 'hotel_monitor' -> monitor
        - 'smart-hotel-guests' or 'hotel_guest' -> guest
        
        The group names can be customized via settings.
        """
        admin_groups = getattr(settings, 'OIDC_ADMIN_GROUPS', [
            'smart-hotel-admins', 'hotel_admin', 'admins', 'admin'
        ])
        monitor_groups = getattr(settings, 'OIDC_MONITOR_GROUPS', [
            'smart-hotel-monitors', 'hotel_monitor', 'monitors', 'monitor'
        ])
        guest_groups = getattr(settings, 'OIDC_GUEST_GROUPS', [
            'smart-hotel-guests', 'hotel_guest', 'guests', 'guest'
        ])
        
        # Check groups in order of privilege
        for group in groups:
            group_lower = group.lower() if isinstance(group, str) else group
            if group_lower in [g.lower() for g in admin_groups]:
                return 'admin'
        
        for group in groups:
            group_lower = group.lower() if isinstance(group, str) else group
            if group_lower in [g.lower() for g in monitor_groups]:
                return 'monitor'
        
        for group in groups:
            group_lower = group.lower() if isinstance(group, str) else group
            if group_lower in [g.lower() for g in guest_groups]:
                return 'guest'
        
        # Default to guest if no matching group
        return 'guest'
    
    def filter_users_by_claims(self, claims):
        """Find existing user by OIDC subject or email"""
        username = self.get_username(claims)
        if not username:
            return self.UserModel.objects.none()
        
        return self.UserModel.objects.filter(username=username)
    
    def get_username(self, claims):
        """Get username from claims - use preferred_username or sub"""
        return claims.get('preferred_username') or claims.get('sub')
    
    def verify_claims(self, claims):
        """Verify the claims contain required information"""
        verified = super().verify_claims(claims)
        
        # Ensure we have a username
        if verified:
            username = self.get_username(claims)
            if not username:
                logger.error("No username found in OIDC claims")
                return False
        
        return verified
