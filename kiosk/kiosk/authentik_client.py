"""
Authentik API Client for Kiosk Guest Account Creation
======================================================

This module provides an API client to interact with Authentik for:
- Creating guest accounts during check-in
- Setting temporary passwords
- Managing guest group membership
- Deactivating accounts on checkout

Environment Variables:
    - AUTHENTIK_URL: Authentik server URL (default: http://authentik-server:9000)
    - KIOSK_API_TOKEN: API token for the kiosk service account
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuthentikAPIError(Exception):
    """Exception raised for Authentik API errors."""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class AuthentikClient:
    """Client for interacting with the Authentik API."""
    
    def __init__(self, base_url: str = None, api_token: str = None):
        """
        Initialize the Authentik client.
        
        Args:
            base_url: Authentik server URL (default from env)
            api_token: API token for authentication (default from env)
        """
        self.base_url = base_url or os.environ.get('AUTHENTIK_URL', 'http://authentik-server:9000')
        self.api_token = api_token or os.environ.get('KIOSK_API_TOKEN', '')
        
        if not self.api_token:
            logger.warning("[Authentik] No API token configured - guest account creation disabled")
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an authenticated request to the Authentik API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (e.g., /api/v3/core/users/)
            **kwargs: Additional arguments passed to requests
            
        Returns:
            JSON response as dictionary
            
        Raises:
            AuthentikAPIError: If the request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                except:
                    error_data = {'detail': response.text}
                
                raise AuthentikAPIError(
                    f"API request failed: {error_data.get('detail', 'Unknown error')}",
                    status_code=response.status_code,
                    response=error_data
                )
            
            if response.status_code == 204:  # No content
                return {}
            
            return response.json()
            
        except requests.RequestException as e:
            raise AuthentikAPIError(f"Connection error: {str(e)}")
    
    def is_configured(self) -> bool:
        """Check if the client is properly configured."""
        return bool(self.api_token)
    
    def health_check(self) -> bool:
        """
        Check if Authentik is reachable and the token is valid.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            self._request('GET', '/api/v3/core/users/me/')
            return True
        except AuthentikAPIError:
            return False
    
    def get_guest_group(self) -> Optional[str]:
        """
        Get the Hotel Guests group ID.
        
        Returns:
            Group UUID or None if not found
        """
        try:
            response = self._request('GET', '/api/v3/core/groups/', params={
                'search': 'Hotel Guests',
                'page_size': 1
            })
            
            results = response.get('results', [])
            if results:
                return results[0].get('pk')
            
            return None
            
        except AuthentikAPIError as e:
            logger.error(f"[Authentik] Failed to get guest group: {e}")
            return None
    
    def create_guest_account(
        self,
        first_name: str,
        last_name: str,
        email: str,
        room_number: str,
        checkout_date: datetime,
        passport_number: str = None,
        phone: str = None
    ) -> Dict[str, Any]:
        """
        Create a new guest account in Authentik.
        
        Args:
            first_name: Guest's first name
            last_name: Guest's last name
            email: Guest's email address
            room_number: Assigned room number
            checkout_date: Expected checkout date
            passport_number: Passport number (optional)
            phone: Phone number (optional)
            
        Returns:
            Created user data including username and temporary password
            
        Raises:
            AuthentikAPIError: If creation fails
        """
        if not self.is_configured():
            raise AuthentikAPIError("Authentik client not configured")
        
        # Generate username from name and room
        username = f"guest_{room_number}_{first_name.lower()}"
        
        # Generate a temporary password
        import secrets
        import string
        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        
        # Get guest group ID
        guest_group = self.get_guest_group()
        
        # Prepare user data
        user_data = {
            'username': username,
            'name': f"{first_name} {last_name}",
            'email': email,
            'is_active': True,
            'type': 'internal',
            'path': 'guests',
            'attributes': {
                'room_number': room_number,
                'checkout_date': checkout_date.isoformat(),
                'guest_type': 'hotel_guest',
                'created_by': 'kiosk'
            }
        }
        
        if passport_number:
            user_data['attributes']['passport_number'] = passport_number
        
        if phone:
            user_data['attributes']['phone'] = phone
        
        if guest_group:
            user_data['groups'] = [guest_group]
        
        try:
            # Create the user
            user = self._request('POST', '/api/v3/core/users/', json=user_data)
            user_id = user.get('pk')
            
            # Set the password
            self._request('POST', f'/api/v3/core/users/{user_id}/set_password/', json={
                'password': password
            })
            
            logger.info(f"[Authentik] Created guest account: {username} for room {room_number}")
            
            return {
                'user_id': user_id,
                'username': username,
                'password': password,
                'email': email,
                'room_number': room_number,
                'checkout_date': checkout_date.isoformat()
            }
            
        except AuthentikAPIError as e:
            logger.error(f"[Authentik] Failed to create guest account: {e}")
            raise
    
    def deactivate_guest(self, username: str) -> bool:
        """
        Deactivate a guest account (on checkout).
        
        Args:
            username: The guest's username
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find the user
            response = self._request('GET', '/api/v3/core/users/', params={
                'username': username,
                'page_size': 1
            })
            
            results = response.get('results', [])
            if not results:
                logger.warning(f"[Authentik] User not found: {username}")
                return False
            
            user_id = results[0].get('pk')
            
            # Deactivate the user
            self._request('PATCH', f'/api/v3/core/users/{user_id}/', json={
                'is_active': False,
                'attributes': {
                    **results[0].get('attributes', {}),
                    'deactivated_at': datetime.now().isoformat(),
                    'deactivated_by': 'kiosk'
                }
            })
            
            logger.info(f"[Authentik] Deactivated guest account: {username}")
            return True
            
        except AuthentikAPIError as e:
            logger.error(f"[Authentik] Failed to deactivate guest: {e}")
            return False
    
    def cleanup_expired_guests(self) -> int:
        """
        Deactivate all guest accounts past their checkout date.
        
        Returns:
            Number of accounts deactivated
        """
        try:
            # Get all active guest users
            response = self._request('GET', '/api/v3/core/users/', params={
                'path': 'guests',
                'is_active': True,
                'page_size': 100
            })
            
            deactivated = 0
            now = datetime.now()
            
            for user in response.get('results', []):
                attrs = user.get('attributes', {})
                checkout_str = attrs.get('checkout_date')
                
                if checkout_str:
                    try:
                        checkout_date = datetime.fromisoformat(checkout_str.replace('Z', '+00:00'))
                        
                        # If checkout date has passed, deactivate
                        if checkout_date.replace(tzinfo=None) < now:
                            if self.deactivate_guest(user.get('username')):
                                deactivated += 1
                    except ValueError:
                        continue
            
            if deactivated > 0:
                logger.info(f"[Authentik] Cleaned up {deactivated} expired guest accounts")
            
            return deactivated
            
        except AuthentikAPIError as e:
            logger.error(f"[Authentik] Failed to cleanup expired guests: {e}")
            return 0


# Singleton instance
_authentik_client = None


def get_authentik_client() -> AuthentikClient:
    """Get the singleton Authentik client instance."""
    global _authentik_client
    if _authentik_client is None:
        _authentik_client = AuthentikClient()
    return _authentik_client
