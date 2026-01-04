from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Custom user model with role-based access control.
    
    With Authentik integration:
    - User authentication is handled by Authentik OIDC
    - User data is synced from Authentik claims
    - Roles are mapped from Authentik groups
    - This model stores user profile and role locally for quick access
    """
    
    ROLE_ADMIN = 'admin'
    ROLE_MONITOR = 'monitor'
    ROLE_GUEST = 'guest'
    
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_MONITOR, 'Monitor'),
        (ROLE_GUEST, 'Guest'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_GUEST)
    assigned_room = models.ForeignKey(
        'rooms.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_guests'
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users'
    )
    
    # OIDC subject identifier (Authentik user ID)
    oidc_sub = models.CharField(max_length=255, blank=True, null=True, unique=True)
    
    class Meta:
        db_table = 'accounts_user'
    
    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN
    
    @property
    def is_monitor(self):
        return self.role == self.ROLE_MONITOR
    
    @property
    def is_guest(self):
        return self.role == self.ROLE_GUEST
    
    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at
    
    @property
    def can_control(self):
        """Check if user can control room settings"""
        return self.role in [self.ROLE_ADMIN, self.ROLE_GUEST]
    
    @property
    def can_view_all_rooms(self):
        """Check if user can view all rooms"""
        return self.role in [self.ROLE_ADMIN, self.ROLE_MONITOR]
    
    def get_accessible_rooms(self):
        """Get rooms this user can access"""
        from rooms.models import Room
        if self.can_view_all_rooms:
            return Room.objects.all()
        elif self.assigned_room:
            return Room.objects.filter(pk=self.assigned_room.pk)
        return Room.objects.none()
    
    def __str__(self):
        if self.is_guest and self.assigned_room:
            return f"{self.username} ({self.assigned_room.room_number})"
        return f"{self.username} ({self.get_role_display()})"
