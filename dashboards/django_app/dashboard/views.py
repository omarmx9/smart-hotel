from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import json

from rooms.models import Room, SensorHistory
from accounts.models import User
from .telegram import send_telegram_message
from .influx_client import write_setpoint, is_connected as influx_connected


class RoleRequiredMixin(UserPassesTestMixin):
    """Mixin to check user role permissions"""
    allowed_roles = []
    
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_expired:
            return False
        return user.role in self.allowed_roles or user.is_superuser


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.ROLE_ADMIN]


class AdminOrMonitorRequiredMixin(RoleRequiredMixin):
    allowed_roles = [User.ROLE_ADMIN, User.ROLE_MONITOR]


class CanControlMixin(UserPassesTestMixin):
    """Mixin to check if user can control settings"""
    
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated or user.is_expired:
            return False
        return user.can_control


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['rooms'] = user.get_accessible_rooms()
        context['user_role'] = user.role
        context['can_control'] = user.can_control
        context['can_view_all'] = user.can_view_all_rooms
        context['is_admin'] = user.is_admin
        
        return context
    
    def get_template_names(self):
        user = self.request.user
        if user.is_guest and user.assigned_room:
            return ['dashboard/room_detail.html']
        return ['dashboard/index.html']


class RoomDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/room_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room_id = kwargs.get('room_id')
        user = self.request.user
        
        room = get_object_or_404(Room, pk=room_id)
        
        # Check access permission
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            context['access_denied'] = True
            return context
        
        context['room'] = room
        context['can_control'] = user.can_control
        context['history'] = SensorHistory.objects.filter(room=room)[:50]
        
        return context


class RoomListAPIView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        rooms = user.get_accessible_rooms()
        return JsonResponse({
            'rooms': [room.to_dict() for room in rooms],
            'mqtt_connected': True,
            'last_update': timezone.now().isoformat()
        })


class RoomAPIView(LoginRequiredMixin, View):
    def get(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        # Check access
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        history = SensorHistory.objects.filter(room=room).order_by('-timestamp')[:50]
        history_data = [
            {
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'temperature': h.temperature,
                'humidity': h.humidity,
                'luminosity': h.luminosity
            }
            for h in reversed(list(history))
        ]
        
        data = room.to_dict()
        data['history'] = history_data
        data['influx_connected'] = influx_connected()
        
        return JsonResponse(data)


class SetTargetTemperatureView(LoginRequiredMixin, CanControlMixin, View):
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        # Check access for guest
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            target = float(data.get('target', room.target_temperature))
            
            room.target_temperature = target
            room.save()
            
            # Write setpoint to InfluxDB
            write_setpoint(room.room_number, target)
            
            return JsonResponse({'status': 'success', 'target': target})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class RoomHistoryAPIView(LoginRequiredMixin, View):
    def get(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        history = SensorHistory.objects.filter(room=room).order_by('-timestamp')[:100]
        return JsonResponse({
            'history': [
                {
                    'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'temperature': h.temperature,
                    'humidity': h.humidity,
                    'luminosity': h.luminosity,
                    'gas_level': h.gas_level
                }
                for h in reversed(list(history))
            ]
        })


class GuestManagementView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'dashboard/guest_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rooms'] = Room.objects.all()
        context['active_guests'] = User.objects.filter(
            role=User.ROLE_GUEST,
            is_active=True
        ).select_related('assigned_room')
        return context


class GenerateGuestAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            room_id = data.get('room_id')
            phone_number = data.get('phone_number', '')
            expiry_hours = data.get('expiry_hours', settings.GUEST_ACCOUNT_EXPIRY_HOURS)
            
            room = get_object_or_404(Room, pk=room_id)
            
            # Generate credentials
            username, password = User.generate_guest_credentials()
            
            # Create guest user
            expires_at = timezone.now() + timedelta(hours=expiry_hours)
            guest = User.objects.create_user(
                username=username,
                password=password,
                role=User.ROLE_GUEST,
                assigned_room=room,
                expires_at=expires_at,
                phone_number=phone_number,
                created_by=request.user
            )
            
            # Update room status
            room.status = Room.STATUS_OCCUPIED
            room.save()
            
            # Send credentials via Telegram (placeholder for SMS)
            message = (
                f"Smart Hotel Guest Access\n"
                f"------------------------\n"
                f"Room: {room.room_number}\n"
                f"Username: {username}\n"
                f"Password: {password}\n"
                f"Expires: {expires_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"------------------------\n"
                f"Login at: {request.build_absolute_uri('/accounts/login/')}"
            )
            
            telegram_sent = send_telegram_message(message)
            
            return JsonResponse({
                'status': 'success',
                'guest': {
                    'username': username,
                    'password': password,
                    'room': room.room_number,
                    'expires_at': expires_at.isoformat()
                },
                'telegram_sent': telegram_sent
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
