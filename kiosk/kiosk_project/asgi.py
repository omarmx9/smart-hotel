"""
ASGI config for kiosk_project.
Supports both HTTP and WebSocket connections.
WebSocket is used for real-time video streaming to MRZ backend.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiosk_project.settings')

# Initialize Django ASGI application early to ensure settings are loaded
django_asgi_app = get_asgi_application()

# Import WebSocket routing after Django is initialized
from kiosk.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
