from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Employee(AbstractUser):
    """
    Custom user model for front desk employees.
    Passwords are stored in the frontdesk database (separate from dashboard).
    """
    
    ROLE_ADMIN = 'admin'
    ROLE_MANAGER = 'manager'
    ROLE_RECEPTIONIST = 'receptionist'
    
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_RECEPTIONIST, 'Receptionist'),
    ]
    
    SHIFT_MORNING = 'morning'
    SHIFT_AFTERNOON = 'afternoon'
    SHIFT_NIGHT = 'night'
    
    SHIFT_CHOICES = [
        (SHIFT_MORNING, 'Morning (6AM - 2PM)'),
        (SHIFT_AFTERNOON, 'Afternoon (2PM - 10PM)'),
        (SHIFT_NIGHT, 'Night (10PM - 6AM)'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_RECEPTIONIST)
    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default=SHIFT_MORNING)
    
    # Track who created this account
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_employees'
    )
    hire_date = models.DateField(null=True, blank=True)
    
    # Last activity tracking
    last_activity = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'employees_employee'
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        ordering = ['last_name', 'first_name']
    
    def save(self, *args, **kwargs):
        # Auto-generate employee ID if not set
        if not self.employee_id and self.pk:
            self.employee_id = f"EMP{self.pk:05d}"
        super().save(*args, **kwargs)
        # Set employee_id after first save if needed
        if not self.employee_id:
            self.employee_id = f"EMP{self.pk:05d}"
            super().save(update_fields=['employee_id'])
    
    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN
    
    @property
    def is_manager(self):
        return self.role == self.ROLE_MANAGER
    
    @property
    def is_receptionist(self):
        return self.role == self.ROLE_RECEPTIONIST
    
    @property
    def can_manage_employees(self):
        """Only admins can create/edit employee accounts"""
        return self.role == self.ROLE_ADMIN
    
    @property
    def can_manage_reservations(self):
        """All roles can manage reservations"""
        return True
    
    @property
    def can_view_documents(self):
        """All roles can view guest documents"""
        return True
    
    @property
    def can_access_reports(self):
        """Managers and admins can access reports"""
        return self.role in [self.ROLE_ADMIN, self.ROLE_MANAGER]
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


class ActivityLog(models.Model):
    """
    Track employee actions for audit purposes.
    """
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_CREATE_RESERVATION = 'create_reservation'
    ACTION_UPDATE_RESERVATION = 'update_reservation'
    ACTION_CANCEL_RESERVATION = 'cancel_reservation'
    ACTION_CHECKIN = 'checkin'
    ACTION_CHECKOUT = 'checkout'
    ACTION_VIEW_DOCUMENT = 'view_document'
    ACTION_CREATE_EMPLOYEE = 'create_employee'
    ACTION_UPDATE_EMPLOYEE = 'update_employee'
    
    ACTION_CHOICES = [
        (ACTION_LOGIN, 'Login'),
        (ACTION_LOGOUT, 'Logout'),
        (ACTION_CREATE_RESERVATION, 'Create Reservation'),
        (ACTION_UPDATE_RESERVATION, 'Update Reservation'),
        (ACTION_CANCEL_RESERVATION, 'Cancel Reservation'),
        (ACTION_CHECKIN, 'Check In'),
        (ACTION_CHECKOUT, 'Check Out'),
        (ACTION_VIEW_DOCUMENT, 'View Document'),
        (ACTION_CREATE_EMPLOYEE, 'Create Employee'),
        (ACTION_UPDATE_EMPLOYEE, 'Update Employee'),
    ]
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Related object reference (optional)
    related_model = models.CharField(max_length=50, blank=True)
    related_id = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'employees_activitylog'
        ordering = ['-timestamp']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
    
    def __str__(self):
        return f"{self.employee} - {self.get_action_display()} at {self.timestamp}"
