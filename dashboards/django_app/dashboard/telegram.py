"""Telegram integration for sending guest credentials (SMS placeholder)"""

import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def send_telegram_message(message: str, chat_id: str = None) -> bool:
    """
    Send a message via Telegram Bot API.
    This is a placeholder for SMS functionality.
    
    Args:
        message: The message to send
        chat_id: Optional chat ID, defaults to settings.TELEGRAM_CHAT_ID
    
    Returns:
        True if message was sent successfully, False otherwise
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        logger.warning("[TELEGRAM] Bot token or chat ID not configured")
        print(f"[TELEGRAM] Would send message:\n{message}")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"[TELEGRAM] Message sent successfully to {chat_id}")
        return True
    except requests.RequestException as e:
        logger.error(f"[TELEGRAM] Failed to send message: {e}")
        print(f"[TELEGRAM] Failed to send: {e}")
        return False


def send_guest_credentials(room_number: str, username: str, password: str, expires_at: str, login_url: str) -> bool:
    """
    Send guest credentials via Telegram.
    
    Args:
        room_number: The room number
        username: Guest username
        password: Guest password
        expires_at: Expiration datetime string
        login_url: URL for login page
    
    Returns:
        True if sent successfully
    """
    message = f"""
<b>Smart Hotel Guest Access</b>
━━━━━━━━━━━━━━━━━━━━━━
<b>Room:</b> {room_number}
<b>Username:</b> <code>{username}</code>
<b>Password:</b> <code>{password}</code>
<b>Expires:</b> {expires_at}
━━━━━━━━━━━━━━━━━━━━━━
<a href="{login_url}">Click here to login</a>
"""
    return send_telegram_message(message)
