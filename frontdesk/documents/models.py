from django.db import models
from django.conf import settings
from reservations.models import Guest


class GuestDocument(models.Model):
    """
    Documents associated with guests (passports, IDs, forms).
    Can be uploaded by staff or synced from kiosk.
    """
    DOC_TYPE_PASSPORT = 'passport'
    DOC_TYPE_ID_CARD = 'id_card'
    DOC_TYPE_DRIVERS_LICENSE = 'drivers_license'
    DOC_TYPE_VISA = 'visa'
    DOC_TYPE_REGISTRATION_FORM = 'registration_form'
    DOC_TYPE_SIGNATURE = 'signature'
    DOC_TYPE_OTHER = 'other'
    
    DOC_TYPE_CHOICES = [
        (DOC_TYPE_PASSPORT, 'Passport'),
        (DOC_TYPE_ID_CARD, 'ID Card'),
        (DOC_TYPE_DRIVERS_LICENSE, "Driver's License"),
        (DOC_TYPE_VISA, 'Visa'),
        (DOC_TYPE_REGISTRATION_FORM, 'Registration Form'),
        (DOC_TYPE_SIGNATURE, 'Signature'),
        (DOC_TYPE_OTHER, 'Other'),
    ]
    
    SOURCE_FRONTDESK = 'frontdesk'
    SOURCE_KIOSK = 'kiosk'
    
    SOURCE_CHOICES = [
        (SOURCE_FRONTDESK, 'Front Desk'),
        (SOURCE_KIOSK, 'Kiosk'),
    ]
    
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
    
    # File can be uploaded locally or referenced from kiosk
    file = models.FileField(upload_to='guest_documents/%Y/%m/', blank=True, null=True)
    
    # For documents stored in kiosk media
    kiosk_file_path = models.CharField(max_length=500, blank=True)
    kiosk_file_url = models.URLField(max_length=500, blank=True)
    
    # Document metadata
    document_number = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    issuing_country = models.CharField(max_length=100, blank=True)
    
    # Source tracking
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_FRONTDESK)
    
    # Verification
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents'
    )
    
    class Meta:
        db_table = 'documents_guestdocument'
        ordering = ['-uploaded_at']
        verbose_name = 'Guest Document'
        verbose_name_plural = 'Guest Documents'
    
    def __str__(self):
        return f"{self.guest.full_name} - {self.get_document_type_display()}"
    
    @property
    def has_file(self):
        return bool(self.file) or bool(self.kiosk_file_url)
    
    @property
    def file_url(self):
        """Get the URL to access the document file."""
        if self.file:
            return self.file.url
        if self.kiosk_file_url:
            return self.kiosk_file_url
        return None
    
    @property
    def is_expired(self):
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False


class DocumentAccessLog(models.Model):
    """
    Log of document access for security/audit purposes.
    """
    document = models.ForeignKey(GuestDocument, on_delete=models.CASCADE, related_name='access_logs')
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='document_accesses'
    )
    action = models.CharField(max_length=20)  # view, download, verify
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'documents_documentaccesslog'
        ordering = ['-timestamp']
        verbose_name = 'Document Access Log'
        verbose_name_plural = 'Document Access Logs'
    
    def __str__(self):
        return f"{self.accessed_by} - {self.action} - {self.document}"
