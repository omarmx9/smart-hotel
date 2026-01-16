from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # User authentication
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # User profile and settings
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    
    # Staff/User management (admin only)
    path('staff/', views.StaffManagementView.as_view(), name='staff_management'),
]
