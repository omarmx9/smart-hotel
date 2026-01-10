import requests
import logging
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import GuestDocument, DocumentAccessLog
from .forms import DocumentUploadForm, DocumentSearchForm
from reservations.models import Guest
from employees.views import log_activity, get_client_ip
from employees.models import ActivityLog

logger = logging.getLogger(__name__)


def log_document_access(document, user, action, request=None):
    """Log document access for audit."""
    ip_address = get_client_ip(request) if request else None
    DocumentAccessLog.objects.create(
        document=document,
        accessed_by=user,
        action=action,
        ip_address=ip_address
    )


@login_required
def document_list(request):
    """List all guest documents."""
    documents = GuestDocument.objects.select_related('guest', 'uploaded_by').all()
    
    # Search
    query = request.GET.get('query', '')
    if query:
        documents = documents.filter(
            Q(guest__first_name__icontains=query) |
            Q(guest__last_name__icontains=query) |
            Q(document_number__icontains=query)
        )
    
    # Filter by type
    doc_type = request.GET.get('document_type')
    if doc_type:
        documents = documents.filter(document_type=doc_type)
    
    # Filter by verified status
    verified = request.GET.get('verified')
    if verified == 'true':
        documents = documents.filter(verified=True)
    elif verified == 'false':
        documents = documents.filter(verified=False)
    
    documents = documents.order_by('-uploaded_at')
    paginator = Paginator(documents, 20)
    page = request.GET.get('page', 1)
    documents = paginator.get_page(page)
    
    form = DocumentSearchForm(request.GET)
    
    return render(request, 'documents/document_list.html', {
        'documents': documents,
        'form': form
    })


@login_required
def document_detail(request, pk):
    """View document details."""
    document = get_object_or_404(
        GuestDocument.objects.select_related('guest', 'uploaded_by', 'verified_by'),
        pk=pk
    )
    
    # Log access
    log_document_access(document, request.user, 'view', request)
    log_activity(
        request.user,
        ActivityLog.ACTION_VIEW_DOCUMENT,
        f'Viewed {document.get_document_type_display()} for {document.guest.full_name}',
        request=request,
        related_model='GuestDocument',
        related_id=document.pk
    )
    
    access_logs = document.access_logs.select_related('accessed_by').all()[:20]
    
    return render(request, 'documents/document_detail.html', {
        'document': document,
        'access_logs': access_logs
    })


@login_required
def document_upload(request, guest_id):
    """Upload a document for a guest."""
    guest = get_object_or_404(Guest, pk=guest_id)
    
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.guest = guest
            document.uploaded_by = request.user
            document.source = GuestDocument.SOURCE_FRONTDESK
            document.save()
            
            messages.success(request, f'Document uploaded for {guest.full_name}.')
            return redirect('reservations:guest_detail', pk=guest_id)
    else:
        form = DocumentUploadForm()
    
    return render(request, 'documents/document_upload.html', {
        'form': form,
        'guest': guest
    })


@login_required
@require_POST
def document_verify(request, pk):
    """Mark a document as verified."""
    document = get_object_or_404(GuestDocument, pk=pk)
    
    document.verified = True
    document.verified_by = request.user
    document.verified_at = timezone.now()
    document.save()
    
    log_document_access(document, request.user, 'verify', request)
    
    return JsonResponse({
        'success': True,
        'verified_by': request.user.get_full_name(),
        'verified_at': document.verified_at.isoformat()
    })


@login_required
def document_download(request, pk):
    """Download/view a document file."""
    document = get_object_or_404(GuestDocument, pk=pk)
    
    log_document_access(document, request.user, 'download', request)
    
    if document.file:
        # Serve local file
        response = HttpResponse(document.file.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.file.name}"'
        return response
    elif document.kiosk_file_url:
        # Redirect to kiosk file
        return redirect(document.kiosk_file_url)
    
    raise Http404("Document file not found")


@login_required
def guest_documents(request, guest_id):
    """View all documents for a specific guest."""
    guest = get_object_or_404(Guest, pk=guest_id)
    documents = GuestDocument.objects.filter(guest=guest).order_by('-uploaded_at')
    
    return render(request, 'documents/guest_documents.html', {
        'guest': guest,
        'documents': documents
    })


@login_required
def sync_from_kiosk(request, guest_id):
    """
    Sync documents from kiosk for a guest.
    This fetches documents that were uploaded via the kiosk system.
    """
    guest = get_object_or_404(Guest, pk=guest_id)
    
    if not guest.kiosk_guest_id:
        messages.warning(request, 'This guest has no kiosk record to sync from.')
        return redirect('reservations:guest_detail', pk=guest_id)
    
    kiosk_api_url = settings.KIOSK_API_URL
    kiosk_media_url = settings.KIOSK_MEDIA_URL
    
    try:
        # Call kiosk API to get guest documents
        # This is a placeholder - implement based on kiosk API
        response = requests.get(
            f"{kiosk_api_url}guests/{guest.kiosk_guest_id}/documents/",
            timeout=10
        )
        
        if response.status_code == 200:
            kiosk_documents = response.json()
            
            synced_count = 0
            for doc in kiosk_documents:
                # Check if document already exists
                existing = GuestDocument.objects.filter(
                    guest=guest,
                    kiosk_file_path=doc.get('file_path', '')
                ).exists()
                
                if not existing and doc.get('file_path'):
                    GuestDocument.objects.create(
                        guest=guest,
                        document_type=doc.get('type', GuestDocument.DOC_TYPE_OTHER),
                        kiosk_file_path=doc.get('file_path', ''),
                        kiosk_file_url=f"{kiosk_media_url}{doc.get('file_path', '')}",
                        document_number=doc.get('document_number', ''),
                        source=GuestDocument.SOURCE_KIOSK,
                        uploaded_by=request.user
                    )
                    synced_count += 1
            
            if synced_count > 0:
                messages.success(request, f'Synced {synced_count} document(s) from kiosk.')
            else:
                messages.info(request, 'No new documents found in kiosk.')
        else:
            messages.error(request, 'Failed to fetch documents from kiosk.')
            
    except requests.RequestException as e:
        logger.error(f"Kiosk sync error: {e}")
        messages.error(request, 'Could not connect to kiosk service.')
    
    return redirect('reservations:guest_detail', pk=guest_id)


@login_required
def passports_today(request):
    """
    View passport scans for today's check-ins and in-house guests.
    Quick access for verification.
    """
    today = timezone.now().date()
    
    # Get today's arrivals and in-house guests
    from reservations.models import Reservation
    
    reservations = Reservation.objects.filter(
        Q(check_in_date=today, status__in=['pending', 'confirmed']) |
        Q(status='checked_in')
    ).select_related('guest')
    
    guest_ids = reservations.values_list('guest_id', flat=True)
    
    # Get passport documents for these guests
    passports = GuestDocument.objects.filter(
        guest_id__in=guest_ids,
        document_type=GuestDocument.DOC_TYPE_PASSPORT
    ).select_related('guest').order_by('-uploaded_at')
    
    return render(request, 'documents/passports_today.html', {
        'passports': passports,
        'today': today
    })
