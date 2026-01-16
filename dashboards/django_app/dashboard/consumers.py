"""WebSocket consumers for real-time dashboard updates"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


class DashboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for dashboard real-time updates"""
    
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        
        self.user = user
        self.room_group = 'dashboard_updates'
        
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()
        
        # Send initial data
        rooms_data = await self.get_accessible_rooms()
        await self.send(text_data=json.dumps({
            'type': 'init',
            'rooms': rooms_data
        }))
    
    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'refresh':
            rooms_data = await self.get_accessible_rooms()
            await self.send(text_data=json.dumps({
                'type': 'update',
                'rooms': rooms_data
            }))
    
    async def room_update(self, event):
        """Handle room update broadcast"""
        await self.send(text_data=json.dumps({
            'type': 'room_update',
            'room': event['room']
        }))
    
    @database_sync_to_async
    def get_accessible_rooms(self):
        from rooms.models import Room
        from accounts.models import User
        
        user = User.objects.get(pk=self.user.pk)
        rooms = user.get_accessible_rooms()
        return [room.to_dict() for room in rooms]


class RoomConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for single room real-time updates"""
    
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.user = user
        
        # Check access permission
        has_access = await self.check_room_access()
        if not has_access:
            await self.close()
            return
        
        self.room_group = f'room_{self.room_id}'
        
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()
        
        # Send initial room data
        room_data = await self.get_room_data()
        await self.send(text_data=json.dumps({
            'type': 'init',
            'room': room_data
        }))
    
    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'set_target' and await self.can_control():
            target = data.get('target')
            if target is not None:
                await self.set_target_temperature(float(target))
                room_data = await self.get_room_data()
                await self.channel_layer.group_send(
                    self.room_group,
                    {
                        'type': 'room_update',
                        'room': room_data
                    }
                )
    
    async def room_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update',
            'room': event['room']
        }))
    
    @database_sync_to_async
    def check_room_access(self):
        from rooms.models import Room
        from accounts.models import User
        
        user = User.objects.get(pk=self.user.pk)
        if user.can_view_all_rooms:
            return True
        if user.is_guest and user.assigned_room and str(user.assigned_room.id) == str(self.room_id):
            return True
        return False
    
    @database_sync_to_async
    def can_control(self):
        from accounts.models import User
        user = User.objects.get(pk=self.user.pk)
        return user.can_control
    
    @database_sync_to_async
    def get_room_data(self):
        from rooms.models import Room, SensorHistory
        room = Room.objects.get(pk=self.room_id)
        data = room.to_dict()
        
        history = SensorHistory.objects.filter(room=room).order_by('-timestamp')[:50]
        data['history'] = [
            {
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'temperature': h.temperature,
                'humidity': h.humidity,
                'luminosity': h.luminosity
            }
            for h in reversed(list(history))
        ]
        return data
    
    @database_sync_to_async
    def set_target_temperature(self, target):
        from rooms.models import Room
        from .mqtt_client import publish_target_temperature
        
        room = Room.objects.get(pk=self.room_id)
        room.target_temperature = target
        room.save()
        publish_target_temperature(room, target)


class AdminConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for admin operations.
    
    Provides read-only access to guest accounts and room assignments.
    """
    
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        
        # Check if user is admin
        is_admin = await self.check_is_admin()
        if not is_admin:
            await self.close()
            return
        
        self.user = user
        self.admin_group = 'admin_channel'
        
        await self.channel_layer.group_add(self.admin_group, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.admin_group, self.channel_name)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'list_guests':
            guests = await self.get_active_guests()
            await self.send(text_data=json.dumps({
                'type': 'guest_list',
                'guests': guests
            }))
    
    @database_sync_to_async
    def check_is_admin(self):
        from accounts.models import User
        user = User.objects.get(pk=self.scope['user'].pk)
        return user.is_admin or user.is_superuser
    
    @database_sync_to_async
    def get_active_guests(self):
        """Get list of active guest users"""
        from accounts.models import User
        guests = User.objects.filter(
            role=User.ROLE_GUEST,
            is_active=True
        ).select_related('assigned_room')
        
        return [
            {
                'id': g.id,
                'username': g.username,
                'room': g.assigned_room.room_number if g.assigned_room else None,
                'expires_at': g.expires_at.isoformat() if g.expires_at else None,
                'is_expired': g.is_expired,
                'phone_number': g.phone_number
            }
            for g in guests
        ]
