from django.contrib import admin
from .models import Room, SensorHistory


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'floor', 'status', 'temperature', 'humidity', 'gas_level', 'last_update')
    list_filter = ('status', 'floor')
    search_fields = ('room_number',)
    readonly_fields = ('last_update', 'created_at')
    
    fieldsets = (
        ('Room Info', {
            'fields': ('room_number', 'floor', 'status', 'mqtt_topic_prefix')
        }),
        ('Sensor Data', {
            'fields': ('temperature', 'humidity', 'luminosity', 'gas_level')
        }),
        ('Control', {
            'fields': ('target_temperature', 'heating_status')
        }),
        ('Timestamps', {
            'fields': ('last_update', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SensorHistory)
class SensorHistoryAdmin(admin.ModelAdmin):
    list_display = ('room', 'temperature', 'humidity', 'luminosity', 'gas_level', 'timestamp')
    list_filter = ('room', 'timestamp')
    date_hierarchy = 'timestamp'
