"""
WebSocket URL routing for kiosk app.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'api/mrz/stream/ws/$', consumers.MRZStreamConsumer.as_asgi()),
]
