"""
URL configuration for Front Desk project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('employees.urls')),
    path('reservations/', include('reservations.urls')),
    path('documents/', include('documents.urls')),
    path('', lambda request: redirect('reservations:dashboard')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
