from django.contrib import admin
from .models import Guest, Room, Reservation, ReservationNote


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'phone_number', 'passport_number', 'vip', 'created_at']
    list_filter = ['vip', 'nationality', 'created_at']
    search_fields = ['first_name', 'last_name', 'email', 'passport_number', 'phone_number']
    ordering = ['last_name', 'first_name']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['room_number', 'floor', 'room_type', 'status', 'max_guests', 'base_rate']
    list_filter = ['room_type', 'status', 'floor']
    search_fields = ['room_number']
    ordering = ['room_number']


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        'reservation_number', 'guest', 'room', 
        'check_in_date', 'check_out_date', 'status', 'payment_status'
    ]
    list_filter = ['status', 'payment_status', 'check_in_date']
    search_fields = ['reservation_number', 'guest__first_name', 'guest__last_name', 'room__room_number']
    ordering = ['-check_in_date']
    raw_id_fields = ['guest', 'room']
    date_hierarchy = 'check_in_date'


@admin.register(ReservationNote)
class ReservationNoteAdmin(admin.ModelAdmin):
    list_display = ['reservation', 'created_by', 'created_at']
    ordering = ['-created_at']
