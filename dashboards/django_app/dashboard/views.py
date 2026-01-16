from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from django.conf import settings
import json

from rooms.models import Room, SensorHistory
from accounts.models import User
from .telegram import send_telegram_message
from .influx_client import write_setpoint, is_connected as influx_connected
from .mqtt_client import publish_target_temperature, publish_climate_mode, publish_fan_speed, publish_luminosity, publish_light_mode, publish_led_control


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
        accessible_rooms = user.get_accessible_rooms()
        if room not in accessible_rooms:
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
        
        # Check access using get_accessible_rooms
        accessible_rooms = user.get_accessible_rooms()
        if room not in accessible_rooms:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        history = SensorHistory.objects.filter(room=room).order_by('-timestamp')[:50]
        history_data = [
            {
                'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'temperature': h.temperature,
                'humidity': h.humidity,
                'ldr_percentage': h.luminosity  # Using luminosity field for LDR percentage
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
    """Set luminosity level (0=off, 1=one light, 2=two lights) or control individual LEDs"""
    def post(self, request, room_id):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        try:
            data = json.loads(request.body)
            
            # Check if controlling individual LEDs
            if 'led1' in data or 'led2' in data:
                # Individual LED control
                if 'led1' in data:
                    led1_state = 'ON' if data['led1'] else 'OFF'
                    room.led1_status = data['led1']
                    publish_led_control(room, 1, led1_state)
                
                if 'led2' in data:
                    led2_state = 'ON' if data['led2'] else 'OFF'
                    room.led2_status = data['led2']
                    publish_led_control(room, 2, led2_state)
                
                room.save()
                return JsonResponse({
                    'status': 'success',
                    'led1': room.led1_status,
                    'led2': room.led2_status
                })
            else:
                # Legacy luminosity level control (0, 1, 2)
                # Accept both 'level' and 'luminosity' for backwards compatibility
                level = int(data.get('luminosity', data.get('level', 0)))
                
                if level not in [0, 1, 2]:
                    return JsonResponse({'error': 'Invalid luminosity level (must be 0, 1, or 2)'}, status=400)
                
                # Map luminosity level to LED states
                room.led1_status = level >= 1
                room.led2_status = level >= 2
                room.save()
                
                # Publish to MQTT (this will send individual LED commands)
                publish_luminosity(room, level)
                
                return JsonResponse({
                    'status': 'success',
                    'level': level,
                    'led1': room.led1_status,
                    'led2': room.led2_status
                })
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'error': str(e)}, status=400)


class SetLEDView(LoginRequiredMixin, CanControlMixin, View):
    """Control individual LEDs (LED1 or LED2)"""
    def post(self, request, room_id, led_number):
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        if user.is_guest and (not user.assigned_room or user.assigned_room.id != room.id):
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        if led_number not in [1, 2]:
            return JsonResponse({'error': 'Invalid LED number (must be 1 or 2)'}, status=400)
        
        try:
            data = json.loads(request.body)
            state = data.get('state', False)
            
            # Update room model
            if led_number == 1:
                room.led1_status = state
            else:
                room.led2_status = state
            room.save()
            
            # Publish to MQTT
            led_state = 'ON' if state else 'OFF'
            publish_led_control(room, led_number, led_state)
            
            return JsonResponse({
                'status': 'success',
                'led': led_number,
                'state': state
            })
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
    
    Allows admins to create, view, and manage guest accounts.
    Guests can also be created automatically during kiosk check-in.
    """
    template_name = 'dashboard/guest_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rooms'] = Room.objects.all()
        context['active_guests'] = User.objects.filter(
            role=User.ROLE_GUEST,
            is_active=True
        ).select_related('assigned_room')
        # Use 'vacant' status - matches Room.STATUS_VACANT
        context['available_rooms'] = Room.objects.filter(status=Room.STATUS_VACANT)
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle guest creation and actions"""
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.utils import timezone
        from datetime import datetime
        import secrets
        import string
        
        action = request.POST.get('action', 'create')
        
        # Handle deactivate/delete/reset_password actions
        if action in ['deactivate', 'delete', 'reset_password']:
            return self.handle_guest_action(request)
        
        # Handle create
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        room_id = request.POST.get('room_id')
        expires_at_str = request.POST.get('expires_at', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        if not first_name or not last_name:
            messages.error(request, 'First name and last name are required.')
            return redirect('dashboard:guest_management')
        
        # Parse expiration datetime
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Make timezone-aware if needed
                if expires_at.tzinfo is None:
                    expires_at = timezone.make_aware(expires_at)
            except ValueError:
                messages.error(request, 'Invalid expiration date format.')
                return redirect('dashboard:guest_management')
        
        # Generate username
        base_username = f"guest_{first_name.lower()}_{last_name.lower()}"
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        
        # Generate secure password
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        # Create user
        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=User.ROLE_GUEST,
            phone_number=phone_number,
            expires_at=expires_at,
            created_by=request.user,
            is_active=True
        )
        user.set_password(password)
        
        # Assign room if specified
        if room_id:
            try:
                room = Room.objects.get(pk=room_id)
                user.assigned_room = room
                room.status = 'occupied'
                room.save()
            except Room.DoesNotExist:
                pass
        
        user.save()
        
        messages.success(
            request, 
            f'Guest account created: {username} / {password}'
        )
        return redirect('dashboard:guest_management')
    
    def handle_guest_action(self, request):
        """Handle deactivate/delete actions for guests"""
        from django.contrib import messages
        from django.shortcuts import redirect
        
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        
        if action == 'deactivate':
            try:
                user = User.objects.get(pk=user_id, role=User.ROLE_GUEST)
                user.is_active = False
                user.save()
                # Free up the room
                if user.assigned_room:
                    user.assigned_room.status = Room.STATUS_VACANT
                    user.assigned_room.save()
                messages.success(request, f'Guest "{user.username}" has been deactivated.')
            except User.DoesNotExist:
                messages.error(request, 'Guest not found.')
                
        elif action == 'delete':
            try:
                user = User.objects.get(pk=user_id, role=User.ROLE_GUEST)
                username = user.username
                # Free up the room
                if user.assigned_room:
                    user.assigned_room.status = Room.STATUS_VACANT
                    user.assigned_room.save()
                user.delete()
                messages.success(request, f'Guest "{username}" has been deleted.')
            except User.DoesNotExist:
                messages.error(request, 'Guest not found.')
                
        elif action == 'reset_password':
            import secrets
            import string
            try:
                user = User.objects.get(pk=user_id, role=User.ROLE_GUEST)
                # Generate secure password
                alphabet = string.ascii_letters + string.digits
                new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
                user.set_password(new_password)
                user.save()
                messages.success(request, f'Password reset for "{user.username}": {new_password}')
            except User.DoesNotExist:
                messages.error(request, 'Guest not found.')
        
        return redirect('dashboard:guest_management')


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


# ============================================================================
# KIOSK INTEGRATION API
# ============================================================================

class KioskAPITokenMixin:
    """Mixin to authenticate kiosk API requests via token."""
    
    def verify_kiosk_token(self, request):
        """Verify the API token from the kiosk."""
        import os
        expected_token = os.environ.get('KIOSK_API_TOKEN', '')
        if not expected_token:
            # No token configured - allow all requests (dev mode)
            return True
        
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Token '):
            token = auth_header[6:]
            return token == expected_token
        return False


@method_decorator(csrf_exempt, name='dispatch')
class GuestCreateAPIView(KioskAPITokenMixin, View):
    """
    API endpoint for kiosk to create guest accounts.
    
    POST /api/guests/create/
    
    Request body (JSON):
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "room_number": "101",
            "checkout_date": "2026-01-10T12:00:00",
            "passport_number": "AB123456",  # optional
            "phone": "+1234567890"  # optional
        }
    
    Response:
        {
            "success": true,
            "username": "guest_101_john",
            "password": "generated_password",
            "room_number": "101",
            "expires_at": "2026-01-10T12:00:00Z"
        }
    """
    
    def post(self, request):
        import secrets
        import string
        from datetime import datetime
        
        # Verify API token
        if not self.verify_kiosk_token(request):
            return JsonResponse({'error': 'Invalid API token'}, status=401)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Validate required fields
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        room_number = data.get('room_number', '').strip()
        checkout_date_str = data.get('checkout_date', '').strip()
        
        if not first_name or not last_name:
            return JsonResponse({'error': 'first_name and last_name are required'}, status=400)
        if not room_number:
            return JsonResponse({'error': 'room_number is required'}, status=400)
        if not checkout_date_str:
            return JsonResponse({'error': 'checkout_date is required'}, status=400)
        
        # Parse checkout date
        try:
            if 'T' in checkout_date_str:
                checkout_date = datetime.fromisoformat(checkout_date_str.replace('Z', '+00:00'))
            else:
                checkout_date = datetime.strptime(checkout_date_str, '%Y-%m-%d')
                checkout_date = checkout_date.replace(hour=12, minute=0)
            # Make timezone-aware if needed
            if checkout_date.tzinfo is None:
                checkout_date = timezone.make_aware(checkout_date)
        except ValueError:
            return JsonResponse({'error': 'Invalid checkout_date format'}, status=400)
        
        # Find the room
        try:
            room = Room.objects.get(room_number=room_number)
        except Room.DoesNotExist:
            return JsonResponse({'error': f'Room {room_number} not found'}, status=404)
        
        # Generate username and password
        username = f"guest_{room_number}_{first_name.lower()[:10]}"
        # Ensure unique username
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        # Create the user
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=data.get('email', ''),
            role=User.ROLE_GUEST,
            assigned_room=room,
            expires_at=checkout_date,
            phone_number=data.get('phone', '')
        )
        
        # Mark room as occupied
        room.status = 'occupied'
        room.save()
        
        return JsonResponse({
            'success': True,
            'username': username,
            'password': password,
            'room_number': room_number,
            'expires_at': checkout_date.isoformat()
        }, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class GuestDeactivateAPIView(KioskAPITokenMixin, View):
    """
    API endpoint for kiosk to deactivate guest accounts on checkout.
    
    POST /api/guests/deactivate/
    
    Request body (JSON):
        {
            "username": "guest_101_john"
        }
        
        OR
        
        {
            "room_number": "101"
        }
    
    Response:
        {
            "success": true,
            "message": "Account deactivated"
        }
    """
    
    def post(self, request):
        # Verify API token
        if not self.verify_kiosk_token(request):
            return JsonResponse({'error': 'Invalid API token'}, status=401)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        username = data.get('username', '').strip()
        room_number = data.get('room_number', '').strip()
        
        if not username and not room_number:
            return JsonResponse({'error': 'username or room_number required'}, status=400)
        
        try:
            if username:
                user = User.objects.get(username=username, role=User.ROLE_GUEST)
            else:
                room = Room.objects.get(room_number=room_number)
                user = User.objects.filter(
                    role=User.ROLE_GUEST,
                    assigned_room=room,
                    is_active=True
                ).first()
                if not user:
                    return JsonResponse({'error': f'No active guest in room {room_number}'}, status=404)
            
            # Deactivate the user
            user.is_active = False
            user.save()
            
            # Free the room
            if user.assigned_room:
                user.assigned_room.status = Room.STATUS_VACANT
                user.assigned_room.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Guest {user.username} deactivated'
            })
            
        except User.DoesNotExist:
            return JsonResponse({'error': f'Guest {username} not found'}, status=404)
        except Room.DoesNotExist:
            return JsonResponse({'error': f'Room {room_number} not found'}, status=404)


# ============================================================================
# ACCESS LOG API
# ============================================================================

class AccessLogListAPIView(LoginRequiredMixin, AdminOrMonitorRequiredMixin, View):
    """API to list all access logs for admin/monitor users"""
    
    def get(self, request):
        from rooms.models import AccessLog
        
        limit = int(request.GET.get('limit', 50))
        logs = AccessLog.get_recent_logs(limit=limit)
        
        return JsonResponse({
            'success': True,
            'access_logs': [log.to_dict() for log in logs],
            'count': len(logs)
        })


class RoomAccessLogAPIView(LoginRequiredMixin, View):
    """API to list access logs for a specific room"""
    
    def get(self, request, room_id):
        from rooms.models import AccessLog
        
        user = request.user
        room = get_object_or_404(Room, pk=room_id)
        
        # Check access permission
        accessible_rooms = user.get_accessible_rooms()
        if room not in accessible_rooms:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        limit = int(request.GET.get('limit', 50))
        logs = AccessLog.get_recent_logs(room=room, limit=limit)
        
        return JsonResponse({
            'success': True,
            'room_number': room.room_number,
            'access_logs': [log.to_dict() for log in logs],
            'count': len(logs)
        })

