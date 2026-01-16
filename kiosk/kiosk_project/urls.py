from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('kiosk.urls')),
]

# Serve static files - WhiteNoise handles this in production but we add as fallback
# This ensures /static/i18n/*.json files are always accessible
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
