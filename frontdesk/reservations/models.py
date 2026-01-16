import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings


class Guest(models.Model):
    """
    Hotel guest information.
    Linked to documents via document app.
    """
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    
    # Document info
    passport_number = models.CharField(max_length=50, blank=True)
    nationality = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Kiosk integration - external ID from kiosk system
    kiosk_guest_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    # Dashboard integration - user account ID
    dashboard_user_id = models.PositiveIntegerField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    vip = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_guests'
    )
    
    class Meta:
        db_table = 'reservations_guest'
        ordering = ['last_name', 'first_name']
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def __str__(self):
        return self.full_name


class Room(models.Model):
    """
    Room information (cached from dashboard).
    This is a local cache - the source of truth is the dashboard.
    """
    ROOM_TYPE_SINGLE = 'single'
    ROOM_TYPE_DOUBLE = 'double'
    ROOM_TYPE_SUITE = 'suite'
    ROOM_TYPE_DELUXE = 'deluxe'
    
    ROOM_TYPE_CHOICES = [
        (ROOM_TYPE_SINGLE, 'Single'),
        (ROOM_TYPE_DOUBLE, 'Double'),
        (ROOM_TYPE_SUITE, 'Suite'),
        (ROOM_TYPE_DELUXE, 'Deluxe Suite'),
    ]
    
    STATUS_AVAILABLE = 'available'
    STATUS_OCCUPIED = 'occupied'
    STATUS_MAINTENANCE = 'maintenance'
    STATUS_CLEANING = 'cleaning'
    
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_OCCUPIED, 'Occupied'),
        (STATUS_MAINTENANCE, 'Maintenance'),
        (STATUS_CLEANING, 'Cleaning'),
    ]
    
    room_number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField(default=1)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES, default=ROOM_TYPE_SINGLE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    
    # Capacity
    max_guests = models.PositiveIntegerField(default=2)
    
    # Pricing (per night)
    base_rate = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
    
    # Features
    has_balcony = models.BooleanField(default=False)
    has_sea_view = models.BooleanField(default=False)
    has_kitchen = models.BooleanField(default=False)
    
    # Dashboard integration
    dashboard_room_id = models.PositiveIntegerField(null=True, blank=True)
    
    # Sync timestamp
    last_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'reservations_room'
        ordering = ['room_number']
    
    def __str__(self):
        return f"Room {self.room_number} ({self.get_room_type_display()})"
    
    @property
    def is_available(self):
        return self.status == self.STATUS_AVAILABLE


class Reservation(models.Model):
    """
    Hotel reservation.
    """
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHECKED_IN = 'checked_in'
    STATUS_CHECKED_OUT = 'checked_out'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NO_SHOW = 'no_show'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CHECKED_IN, 'Checked In'),
        (STATUS_CHECKED_OUT, 'Checked Out'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_NO_SHOW, 'No Show'),
    ]
    
    PAYMENT_PENDING = 'pending'
    PAYMENT_PARTIAL = 'partial'
    PAYMENT_PAID = 'paid'
    PAYMENT_REFUNDED = 'refunded'
    
    PAYMENT_CHOICES = [
        (PAYMENT_PENDING, 'Pending'),
        (PAYMENT_PARTIAL, 'Partial'),
        (PAYMENT_PAID, 'Paid'),
        (PAYMENT_REFUNDED, 'Refunded'),
    ]
    
    # Unique reservation number
    reservation_number = models.CharField(max_length=20, unique=True, blank=True)
    
    # Guest and room
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name='reservations')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='reservations', null=True, blank=True)
    
    # Dates
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    # People
    adults = models.PositiveIntegerField(default=1)
    children = models.PositiveIntegerField(default=0)
    
    # Pricing
    rate_per_night = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_PENDING)
    
    # Special requests
    special_requests = models.TextField(blank=True)
    
    # Kiosk integration
    kiosk_reservation_id = models.CharField(max_length=100, blank=True, null=True)
    checked_in_via_kiosk = models.BooleanField(default=False)
    
    # Access card
    access_card_issued = models.BooleanField(default=False)
    access_card_number = models.CharField(max_length=50, blank=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_reservations'
    )
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checkins_processed'
    )
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checkouts_processed'
    )
    
    class Meta:
        db_table = 'reservations_reservation'
        ordering = ['-check_in_date', 'room__room_number']
    
    def save(self, *args, **kwargs):
        if not self.reservation_number:
            # Generate unique reservation number
            prefix = timezone.now().strftime('%y%m')
            unique_id = uuid.uuid4().hex[:6].upper()
            self.reservation_number = f"RES-{prefix}-{unique_id}"
        
        # Calculate total if rate is set
        if self.rate_per_night and self.check_in_date and self.check_out_date:
            nights = (self.check_out_date - self.check_in_date).days
            self.total_amount = self.rate_per_night * nights
        
        super().save(*args, **kwargs)
    
    @property
    def nights(self):
        if self.check_in_date and self.check_out_date:
            return (self.check_out_date - self.check_in_date).days
        return 0
    
    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid
    
    @property
    def is_today_checkin(self):
        return self.check_in_date == timezone.now().date()
    
    @property
    def is_today_checkout(self):
        return self.check_out_date == timezone.now().date()
    
    @property
    def is_overdue_checkin(self):
        return (
            self.status in [self.STATUS_PENDING, self.STATUS_CONFIRMED]
            and self.check_in_date < timezone.now().date()
        )
    
    def __str__(self):
        return f"{self.reservation_number} - {self.guest.full_name}"


class ReservationNote(models.Model):
    """
    Notes attached to reservations.
    """
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='notes')
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reservation_notes'
    )
    
    class Meta:
        db_table = 'reservations_reservationnote'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note on {self.reservation.reservation_number}"
