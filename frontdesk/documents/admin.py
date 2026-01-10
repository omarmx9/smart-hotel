from django.contrib import admin
from .models import GuestDocument, DocumentAccessLog


@admin.register(GuestDocument)
class GuestDocumentAdmin(admin.ModelAdmin):
    list_display = ['guest', 'document_type', 'document_number', 'verified', 'source', 'uploaded_at']
    list_filter = ['document_type', 'verified', 'source']
    search_fields = ['guest__first_name', 'guest__last_name', 'document_number']
    ordering = ['-uploaded_at']
    raw_id_fields = ['guest']


@admin.register(DocumentAccessLog)
class DocumentAccessLogAdmin(admin.ModelAdmin):
    list_display = ['document', 'accessed_by', 'action', 'ip_address', 'timestamp']
    list_filter = ['action', 'timestamp']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']
