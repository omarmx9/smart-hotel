from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('room/<int:room_id>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('api/rooms/', views.RoomListAPIView.as_view(), name='api_rooms'),
    path('api/room/<int:room_id>/', views.RoomAPIView.as_view(), name='api_room'),
    path('api/room/<int:room_id>/set_target/', views.SetTargetTemperatureView.as_view(), name='api_set_target'),
    path('api/room/<int:room_id>/history/', views.RoomHistoryAPIView.as_view(), name='api_room_history'),
    path('guest-management/', views.GuestManagementView.as_view(), name='guest_management'),
    path('api/generate-guest/', views.GenerateGuestAPIView.as_view(), name='api_generate_guest'),
]
