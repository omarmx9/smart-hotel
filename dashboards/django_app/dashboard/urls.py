from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('room/<int:room_id>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('api/rooms/', views.RoomListAPIView.as_view(), name='api_rooms'),
    path('api/room/<int:room_id>/', views.RoomAPIView.as_view(), name='api_room'),
    path('api/room/<int:room_id>/set_target/', views.SetTargetTemperatureView.as_view(), name='api_set_target'),
    path('api/room/<int:room_id>/set_climate_mode/', views.SetClimateModeView.as_view(), name='api_set_climate_mode'),
    path('api/room/<int:room_id>/set_fan_speed/', views.SetFanSpeedView.as_view(), name='api_set_fan_speed'),
    path('api/room/<int:room_id>/set_luminosity/', views.SetLuminosityView.as_view(), name='api_set_luminosity'),
    path('api/room/<int:room_id>/set_light_mode/', views.SetLightModeView.as_view(), name='api_set_light_mode'),
    path('api/room/<int:room_id>/set_led/<int:led_number>/', views.SetLEDView.as_view(), name='api_set_led'),
    path('api/room/<int:room_id>/history/', views.RoomHistoryAPIView.as_view(), name='api_room_history'),
    # Guest management
    path('guest-management/', views.GuestManagementView.as_view(), name='guest_management'),
    # Notifications center - admin/monitor only
    path('notifications/', views.NotificationsView.as_view(), name='notifications'),
    path('api/notifications/status/', views.NotificationStatusAPIView.as_view(), name='api_notifications_status'),
    path('api/notifications/send/', views.SendNotificationAPIView.as_view(), name='api_notifications_send'),
    # Kiosk Integration API (for guest account creation/deactivation)
    path('api/guests/create/', views.GuestCreateAPIView.as_view(), name='api_guest_create'),
    path('api/guests/deactivate/', views.GuestDeactivateAPIView.as_view(), name='api_guest_deactivate'),
]
