"""
Account views for Smart Hotel Dashboard

Standard Django authentication with PostgreSQL backend.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.views.generic import TemplateView, RedirectView, ListView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.conf import settings

from .models import User


class AdminRequiredMixin(UserPassesTestMixin):
    """Only allow admin users"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role == User.ROLE_ADMIN


class AdminOrMonitorRequiredMixin(UserPassesTestMixin):
    """Only allow admin or monitor users"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in [User.ROLE_ADMIN, User.ROLE_MONITOR]


class LoginView(DjangoLoginView):
    """
    Login view - standard Django authentication.
    """
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        user = self.request.user
        if user.is_guest and user.assigned_room:
            from django.urls import reverse
            return reverse('dashboard:room_detail', kwargs={'room_id': user.assigned_room.id})
        return reverse_lazy('dashboard:index')


class LogoutView(DjangoLogoutView):
    """
    Logout view - standard Django logout.
    """
    next_page = reverse_lazy('accounts:login')


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    User profile display.
    """
    template_name = 'accounts/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


class SettingsView(LoginRequiredMixin, TemplateView):
    """
    User settings page.
    """
    template_name = 'accounts/settings.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        # Password changes via Django admin
        context['can_change_password'] = True
        return context


class StaffManagementView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Staff management overview.
    
    Allows admins to create, view, and manage staff accounts.
    """
    template_name = 'accounts/staff_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Show staff users (admins and monitors) from database
        context['staff_users'] = User.objects.filter(
            role__in=[User.ROLE_ADMIN, User.ROLE_MONITOR]
        ).order_by('-date_joined')
        
        # Django admin URL
        context['admin_url'] = '/admin/'
        
        context['role_choices'] = [
            (User.ROLE_ADMIN, 'Administrator'),
            (User.ROLE_MONITOR, 'Monitor'),
        ]
        
        # Get all rooms for monitor room restrictions
        from rooms.models import Room
        context['all_rooms'] = Room.objects.all().order_by('room_number')
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle staff creation and user actions"""
        from django.contrib import messages
        from django.shortcuts import redirect
        import secrets
        import string
        
        action = request.POST.get('action', 'create')
        
        if action == 'create':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            role = request.POST.get('role', User.ROLE_MONITOR)
            
            if not username:
                messages.error(request, 'Username is required.')
                return redirect('accounts:staff_management')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
                return redirect('accounts:staff_management')
            
            # Generate secure password
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for _ in range(12))
            
            # Create user
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=True,
                created_by=request.user
            )
            user.set_password(password)
            user.save()
            
            # If monitor, assign allowed rooms
            if role == User.ROLE_MONITOR:
                allowed_room_ids = request.POST.getlist('allowed_rooms')
                if allowed_room_ids:
                    from rooms.models import Room
                    rooms = Room.objects.filter(pk__in=allowed_room_ids)
                    user.allowed_rooms.set(rooms)
            
            messages.success(request, f'Staff account created: {username} / {password}')
            
        elif action == 'deactivate':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
                if user == request.user:
                    messages.error(request, 'You cannot deactivate your own account.')
                else:
                    user.is_active = False
                    user.save()
                    # If guest, free up the room
                    if user.assigned_room:
                        from rooms.models import Room
                        user.assigned_room.status = Room.STATUS_VACANT
                        user.assigned_room.save()
                    messages.success(request, f'Account "{user.username}" has been deactivated.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                
        elif action == 'activate':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
                user.is_active = True
                user.save()
                messages.success(request, f'Account "{user.username}" has been activated.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
                if user == request.user:
                    messages.error(request, 'You cannot delete your own account.')
                else:
                    username = user.username
                    # If guest, free up the room
                    if user.assigned_room:
                        from rooms.models import Room
                        user.assigned_room.status = Room.STATUS_VACANT
                        user.assigned_room.save()
                    user.delete()
                    messages.success(request, f'Account "{username}" has been deleted.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                
        elif action == 'reset_password':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
                # Generate secure password
                alphabet = string.ascii_letters + string.digits
                new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
                user.set_password(new_password)
                user.save()
                messages.success(request, f'Password reset for "{user.username}": {new_password}')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
        
        return redirect('accounts:staff_management')
