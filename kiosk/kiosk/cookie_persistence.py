"""
Cookie-based persistence for kiosk session data.

This module provides utilities to store critical session data in cookies,
ensuring data survives server restarts and container recreation.
"""

import json
import base64
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# Cookie configuration
COOKIE_MAX_AGE = 24 * 60 * 60  # 24 hours
COOKIE_PREFIX = "kiosk_"

# Keys to persist in cookies
PERSISTENT_KEYS = [
    "guest_id",
    "reservation_id",
    "flow_type",
    "language",
    "access_method",
    "pending_access_methods",
    "extracted_passport_data",
    "registration_data",
    "dw_registration_data",
    "room_payload",
    "rfid_token",
    "document_session_id",
]


def _encode_value(value):
    """Encode a Python value to a cookie-safe string."""
    try:
        json_str = json.dumps(value)
        return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    except (TypeError, ValueError) as e:
        logger.warning(f"Failed to encode cookie value: {e}")
        return None


def _decode_value(encoded):
    """Decode a cookie string back to a Python value."""
    try:
        json_str = base64.b64decode(encoded.encode('utf-8')).decode('utf-8')
        return json.loads(json_str)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to decode cookie value: {e}")
        return None


def get_cookie_name(key):
    """Get the cookie name for a session key."""
    return f"{COOKIE_PREFIX}{key}"


def restore_session_from_cookies(request):
    """
    Restore session data from cookies if session is empty or missing keys.
    Call this at the beginning of views that need persistent data.
    """
    restored_count = 0
    for key in PERSISTENT_KEYS:
        cookie_name = get_cookie_name(key)
        cookie_value = request.COOKIES.get(cookie_name)
        
        if cookie_value and key not in request.session:
            decoded = _decode_value(cookie_value)
            if decoded is not None:
                request.session[key] = decoded
                restored_count += 1
                logger.debug(f"Restored session key '{key}' from cookie")
    
    if restored_count > 0:
        logger.info(f"Restored {restored_count} session keys from cookies")
    
    return restored_count


def save_to_cookie(response, key, value):
    """
    Save a session value to a cookie for persistence.
    Call this when setting important session values.
    """
    if key not in PERSISTENT_KEYS:
        return
    
    cookie_name = get_cookie_name(key)
    encoded = _encode_value(value)
    
    if encoded:
        response.set_cookie(
            cookie_name,
            encoded,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=False,  # Set to True in production with HTTPS
        )
        logger.debug(f"Saved session key '{key}' to cookie")


def clear_cookie(response, key):
    """Clear a persistent cookie."""
    cookie_name = get_cookie_name(key)
    response.delete_cookie(cookie_name)


def clear_all_cookies(response):
    """Clear all persistent cookies (for session reset)."""
    for key in PERSISTENT_KEYS:
        clear_cookie(response, key)
    logger.info("Cleared all persistent cookies")


def sync_session_to_cookies(request, response):
    """
    Sync all persistent session values to cookies.
    Call this at the end of views that modify session data.
    """
    for key in PERSISTENT_KEYS:
        if key in request.session:
            save_to_cookie(response, key, request.session[key])


class PersistentResponse:
    """
    Wrapper to handle response with cookie persistence.
    Use this to ensure session data is saved to cookies.
    """
    def __init__(self, request, response):
        self.request = request
        self.response = response
    
    def sync_cookies(self):
        """Sync session data to cookies."""
        sync_session_to_cookies(self.request, self.response)
        return self.response


def with_cookie_persistence(view_func):
    """
    Decorator that automatically restores session from cookies
    and syncs session back to cookies after the view executes.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Restore session from cookies before processing
        restore_session_from_cookies(request)
        
        # Call the view
        response = view_func(request, *args, **kwargs)
        
        # Sync session to cookies after processing
        if hasattr(response, 'set_cookie'):
            sync_session_to_cookies(request, response)
        
        return response
    
    return wrapper


def set_session_with_cookie(request, response, key, value):
    """
    Set a session value and also save it to a cookie.
    Use this instead of request.session[key] = value for persistent data.
    """
    request.session[key] = value
    if key in PERSISTENT_KEYS:
        save_to_cookie(response, key, value)
