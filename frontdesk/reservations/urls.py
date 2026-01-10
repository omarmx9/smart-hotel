from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Guests
    path('guests/', views.guest_list, name='guest_list'),
    path('guests/create/', views.guest_create, name='guest_create'),
    path('guests/<int:pk>/', views.guest_detail, name='guest_detail'),
    path('guests/<int:pk>/edit/', views.guest_edit, name='guest_edit'),
    
    # Rooms
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<int:pk>/', views.room_detail, name='room_detail'),
    path('rooms/<int:pk>/edit/', views.room_edit, name='room_edit'),
    path('rooms/<int:pk>/status/', views.room_update_status, name='room_update_status'),
    
    # Reservations
    path('list/', views.reservation_list, name='reservation_list'),
    path('create/', views.reservation_create, name='reservation_create'),
    path('create/<int:guest_id>/', views.reservation_create, name='reservation_create_for_guest'),
    path('<int:pk>/', views.reservation_detail, name='reservation_detail'),
    path('<int:pk>/edit/', views.reservation_edit, name='reservation_edit'),
    path('<int:pk>/cancel/', views.reservation_cancel, name='reservation_cancel'),
    path('<int:pk>/note/', views.reservation_add_note, name='reservation_add_note'),
    
    # Quick reservation for walk-ins
    path('quick/', views.quick_reservation, name='quick_reservation'),
    
    # Check-in/Check-out
    path('<int:pk>/check-in/', views.check_in, name='check_in'),
    path('<int:pk>/check-out/', views.check_out, name='check_out'),
    
    # Arrivals & Departures
    path('arrivals/', views.arrivals, name='arrivals'),
    path('departures/', views.departures, name='departures'),
    path('in-house/', views.in_house, name='in_house'),
]
