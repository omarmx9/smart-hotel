from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
import secrets
import string


class User(AbstractUser):
    """Custom user model with role-based access control"""
    
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
    
    @classmethod
    def generate_guest_credentials(cls):
        """Generate random username and password for guest accounts"""
        username = 'guest_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        return username, password
    
    def __str__(self):
        if self.is_guest and self.assigned_room:
            return f"{self.username} ({self.assigned_room.room_number})"
        return f"{self.username} ({self.get_role_display()})"


class PasswordResetToken(models.Model):
    """Token for password reset via Telegram link"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'accounts_password_reset_token'
    
    @classmethod
    def create_for_user(cls, user, hours_valid=1):
        """Create a new password reset token for a user"""
        # Invalidate any existing tokens
        cls.objects.filter(user=user, used=False).update(used=True)
        
        token = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(hours=hours_valid)
        
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
    
    @property
    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"Reset token for {self.user.username}"
