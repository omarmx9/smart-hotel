"""
WSGI config for Smart Hotel Dashboard
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_hotel.settings')

application = get_wsgi_application()
