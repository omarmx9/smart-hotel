from django.urls import path, include
from . import views

app_name = 'accounts'

urlpatterns = [
    # OIDC authentication endpoints (handled by mozilla-django-oidc)
    path('oidc/', include('mozilla_django_oidc.urls')),
    
    # Legacy login page - redirects to OIDC
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # User profile and settings (read-only for OIDC users)
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    
    # Staff/User management (admin only) - via Authentik
    path('staff/', views.StaffManagementView.as_view(), name='staff_management'),
]
