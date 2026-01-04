"""
Account views for Smart Hotel Dashboard

With Authentik integration, user management is handled externally.
These views provide user profile display and redirect to OIDC flows.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, RedirectView, ListView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.conf import settings
from mozilla_django_oidc.views import OIDCLogoutView

from .models import User


class AdminRequiredMixin(UserPassesTestMixin):
    """Only allow admin users"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role == User.ROLE_ADMIN


class AdminOrMonitorRequiredMixin(UserPassesTestMixin):
    """Only allow admin or monitor users"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in [User.ROLE_ADMIN, User.ROLE_MONITOR]


class LoginView(RedirectView):
    """
    Login view - redirects to Authentik OIDC login.
    
    If user is already authenticated, redirects to appropriate dashboard.
    """
    
    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            return self._get_success_url()
        # Redirect to OIDC authentication
        return reverse_lazy('oidc_authentication_init')
    
    def _get_success_url(self):
        user = self.request.user
        if user.is_guest and user.assigned_room:
            from django.urls import reverse
            return reverse('dashboard:room_detail', kwargs={'room_id': user.assigned_room.id})
        return reverse_lazy('dashboard:index')


class LogoutView(OIDCLogoutView):
    """
    Logout view - handles OIDC logout via Authentik.
    
    Logs out from both Django session and Authentik.
    """
    
    def get_redirect_url(self):
        return settings.LOGOUT_REDIRECT_URL


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    User profile display.
    
    Shows user information synced from Authentik.
    Profile editing should be done in Authentik.
    """
    template_name = 'accounts/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['authentik_url'] = settings.AUTHENTIK_URL
        context['profile_edit_url'] = f"{settings.AUTHENTIK_URL}/if/user/"
        return context


class SettingsView(LoginRequiredMixin, TemplateView):
    """
    User settings page.
    
    With Authentik, password changes and security settings
    are managed in Authentik's user portal.
    """
    template_name = 'accounts/settings.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['authentik_url'] = settings.AUTHENTIK_URL
        context['settings_url'] = f"{settings.AUTHENTIK_URL}/if/user/#/settings"
        context['security_url'] = f"{settings.AUTHENTIK_URL}/if/user/#/security"
        # Password changes are handled in Authentik
        context['can_change_password'] = False
        context['password_change_url'] = f"{settings.AUTHENTIK_URL}/if/user/#/security"
        return context


class StaffManagementView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Staff management overview.
    
    With Authentik, actual user/staff management is done in Authentik.
    This view provides links and shows current users synced from Authentik.
    """
    template_name = 'accounts/staff_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Show users synced from Authentik
        context['staff_users'] = User.objects.filter(
            role__in=[User.ROLE_ADMIN, User.ROLE_MONITOR]
        ).order_by('-date_joined')
        
        context['guest_users'] = User.objects.filter(
            role=User.ROLE_GUEST,
            is_active=True
        ).select_related('assigned_room')
        
        # Authentik admin URLs
        context['authentik_url'] = settings.AUTHENTIK_URL
        context['authentik_admin_url'] = f"{settings.AUTHENTIK_URL}/if/admin/"
        context['authentik_users_url'] = f"{settings.AUTHENTIK_URL}/if/admin/#/identity/users"
        context['authentik_groups_url'] = f"{settings.AUTHENTIK_URL}/if/admin/#/identity/groups"
        
        context['role_choices'] = [
            (User.ROLE_ADMIN, 'Administrator'),
            (User.ROLE_MONITOR, 'Monitor'),
        ]
        return context
