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
from .mqtt_client import publish_target_temperature, publish_climate_mode, publish_fan_speed, publish_luminosity, publish_light_mode


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
            
            # Publish to MQTT
            publish_target_temperature(room, target)
            
            # Write setpoint to InfluxDB
            write_setpoint(room.room_number, target)
            
            return JsonResponse({'status': 'success', 'target': target})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class SetClimateModeView(LoginRequiredMixin, CanControlMixin, View):
    """Set climate control mode (auto/manual/off)"""
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            mode = data.get('mode', '').lower()
            
            if mode not in [Room.CLIMATE_AUTO, Room.CLIMATE_MANUAL, Room.CLIMATE_OFF]:
                return JsonResponse({'error': 'Invalid climate mode'}, status=400)
            
            room.climate_mode = mode
            room.save()
            
            # Publish to MQTT
            publish_climate_mode(room, mode)
            
            return JsonResponse({'status': 'success', 'mode': mode})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class SetFanSpeedView(LoginRequiredMixin, CanControlMixin, View):
    """Set fan speed for manual climate mode"""
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            speed = data.get('speed', '').lower()
            
            if speed not in [Room.FAN_LOW, Room.FAN_MEDIUM, Room.FAN_HIGH]:
                return JsonResponse({'error': 'Invalid fan speed'}, status=400)
            
            room.fan_speed = speed
            room.save()
            
            # Publish to MQTT
            publish_fan_speed(room, speed)
            
            return JsonResponse({'status': 'success', 'speed': speed})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class SetLuminosityView(LoginRequiredMixin, CanControlMixin, View):
    """Set luminosity level (0=off, 1=one light, 2=two lights)"""
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            # Accept both 'level' and 'luminosity' for backwards compatibility
            level = int(data.get('luminosity', data.get('level', 0)))
            
            if level not in [0, 1, 2]:
                return JsonResponse({'error': 'Invalid luminosity level (must be 0, 1, or 2)'}, status=400)
            
            room.luminosity = level
            room.save()
            
            # Publish to MQTT
            publish_luminosity(room, level)
            
            return JsonResponse({'status': 'success', 'level': level})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class SetLightModeView(LoginRequiredMixin, CanControlMixin, View):
    """Set light mode (auto/manual)"""
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            mode = data.get('mode', 'auto')
            
            if mode not in ['auto', 'manual']:
                return JsonResponse({'error': 'Invalid light mode (must be auto or manual)'}, status=400)
            
            room.light_mode = mode
            room.save()
            
            # Publish to MQTT
            publish_light_mode(room, mode)
            
            return JsonResponse({'status': 'success', 'mode': mode})
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
    """
    Guest management overview.
    
    With Authentik integration, guest accounts are created in Authentik.
    This view shows synced guests and provides links to Authentik admin.
    """
    template_name = 'dashboard/guest_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rooms'] = Room.objects.all()
        context['active_guests'] = User.objects.filter(
            role=User.ROLE_GUEST,
            is_active=True
        ).select_related('assigned_room')
        
        # Authentik URLs for guest management
        authentik_url = getattr(settings, 'AUTHENTIK_URL', 'https://auth.example.com')
        context['authentik_url'] = authentik_url
        context['authentik_users_url'] = f"{authentik_url}/if/admin/#/identity/users"
        context['authentik_groups_url'] = f"{authentik_url}/if/admin/#/identity/groups"
        
        return context


class NotificationsView(LoginRequiredMixin, AdminOrMonitorRequiredMixin, TemplateView):
    """
    Notifications center for admins and monitors.
    
    Shows notification status, failed deliveries, and allows sending test messages.
    Integrates with Node-RED notification gateway via MQTT.
    """
    template_name = 'dashboard/notifications.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_admin'] = self.request.user.is_admin
        context['nodered_url'] = getattr(settings, 'NODERED_URL', 'http://nodered:1880')
        return context


class NotificationStatusAPIView(LoginRequiredMixin, AdminOrMonitorRequiredMixin, View):
    """Get notification service status from Node-RED"""
    
    def get(self, request):
        import urllib.request
        import urllib.error
        
        nodered_url = getattr(settings, 'NODERED_URL', 'http://nodered:1880')
        
        try:
            req = urllib.request.Request(f"{nodered_url}/api/health", timeout=5)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return JsonResponse({
                    'status': 'connected',
                    'services': data.get('services', {}),
                    'statistics': data.get('statistics', {}),
                    'timestamp': data.get('timestamp')
                })
        except urllib.error.URLError as e:
            return JsonResponse({
                'status': 'disconnected',
                'error': str(e),
                'services': {},
                'statistics': {}
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'error': str(e),
                'services': {},
                'statistics': {}
            })


class SendNotificationAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Send a notification via MQTT to Node-RED"""
    
    def post(self, request):
        from .mqtt_client import publish_notification
        
        try:
            data = json.loads(request.body)
            message = data.get('message', '')
            notification_type = data.get('type', 'system')
            recipient = data.get('recipient', {})
            
            if not message:
                return JsonResponse({'error': 'Message is required'}, status=400)
            
            # Publish to MQTT for Node-RED to handle
            result = publish_notification(
                message=message,
                notification_type=notification_type,
                recipient=recipient
            )
            
            return JsonResponse({
                'status': 'sent',
                'message': 'Notification queued for delivery'
            })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

