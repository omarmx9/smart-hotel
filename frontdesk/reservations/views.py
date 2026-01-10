from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta

from .models import Guest, Room, Reservation, ReservationNote
from .forms import (
    GuestForm, GuestSearchForm, RoomForm,
    ReservationForm, QuickReservationForm,
    CheckInForm, CheckOutForm, ReservationNoteForm,
    ReservationSearchForm
)
from employees.views import log_activity
from employees.models import ActivityLog


@login_required
def dashboard(request):
    """Main dashboard for front desk."""
    today = timezone.now().date()
    
    # Today's statistics
    todays_checkins = Reservation.objects.filter(
        check_in_date=today,
        status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]
    ).count()
    
    todays_checkouts = Reservation.objects.filter(
        check_out_date=today,
        status=Reservation.STATUS_CHECKED_IN
    ).count()
    
    current_guests = Reservation.objects.filter(
        status=Reservation.STATUS_CHECKED_IN
    ).count()
    
    available_rooms = Room.objects.filter(status=Room.STATUS_AVAILABLE).count()
    total_rooms = Room.objects.count()
    
    # Upcoming arrivals (today and next 3 days)
    upcoming_arrivals = Reservation.objects.filter(
        check_in_date__gte=today,
        check_in_date__lte=today + timedelta(days=3),
        status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]
    ).select_related('guest', 'room').order_by('check_in_date')[:10]
    
    # Today's departures
    todays_departures = Reservation.objects.filter(
        check_out_date=today,
        status=Reservation.STATUS_CHECKED_IN
    ).select_related('guest', 'room').order_by('room__room_number')
    
    # In-house guests
    in_house = Reservation.objects.filter(
        status=Reservation.STATUS_CHECKED_IN
    ).select_related('guest', 'room').order_by('room__room_number')[:10]
    
    # Recent activity
    recent_activity = ActivityLog.objects.filter(
        action__in=[
            ActivityLog.ACTION_CHECKIN,
            ActivityLog.ACTION_CHECKOUT,
            ActivityLog.ACTION_CREATE_RESERVATION
        ]
    ).select_related('employee')[:10]
    
    context = {
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
        'current_guests': current_guests,
        'available_rooms': available_rooms,
        'total_rooms': total_rooms,
        'occupancy_rate': (current_guests / total_rooms * 100) if total_rooms > 0 else 0,
        'upcoming_arrivals': upcoming_arrivals,
        'todays_departures': todays_departures,
        'in_house': in_house,
        'recent_activity': recent_activity,
    }
    
    return render(request, 'reservations/dashboard.html', context)


# =============================================================================
# GUEST MANAGEMENT
# =============================================================================

@login_required
def guest_list(request):
    """List all guests."""
    guests = Guest.objects.all()
    
    # Search
    query = request.GET.get('query', '')
    if query:
        guests = guests.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(passport_number__icontains=query) |
            Q(phone_number__icontains=query)
        )
    
    guests = guests.order_by('last_name', 'first_name')
    paginator = Paginator(guests, 20)
    page = request.GET.get('page', 1)
    guests = paginator.get_page(page)
    
    form = GuestSearchForm(request.GET)
    
    return render(request, 'reservations/guest_list.html', {
        'guests': guests,
        'form': form,
        'query': query
    })


@login_required
def guest_detail(request, pk):
    """View guest details."""
    guest = get_object_or_404(Guest, pk=pk)
    reservations = guest.reservations.all().order_by('-check_in_date')[:10]
    
    # Get documents for this guest
    from documents.models import GuestDocument
    documents = GuestDocument.objects.filter(guest=guest).order_by('-uploaded_at')
    
    return render(request, 'reservations/guest_detail.html', {
        'guest': guest,
        'reservations': reservations,
        'documents': documents
    })


@login_required
def guest_create(request):
    """Create a new guest."""
    if request.method == 'POST':
        form = GuestForm(request.POST)
        if form.is_valid():
            guest = form.save(commit=False)
            guest.created_by = request.user
            guest.save()
            messages.success(request, f'Guest {guest.full_name} created successfully.')
            
            # Redirect to reservation creation if requested
            if 'create_reservation' in request.POST:
                return redirect('reservations:reservation_create', guest_id=guest.pk)
            return redirect('reservations:guest_detail', pk=guest.pk)
    else:
        form = GuestForm()
    
    return render(request, 'reservations/guest_form.html', {
        'form': form,
        'title': 'Create New Guest'
    })


@login_required
def guest_edit(request, pk):
    """Edit guest details."""
    guest = get_object_or_404(Guest, pk=pk)
    
    if request.method == 'POST':
        form = GuestForm(request.POST, instance=guest)
        if form.is_valid():
            form.save()
            messages.success(request, f'Guest {guest.full_name} updated successfully.')
            return redirect('reservations:guest_detail', pk=guest.pk)
    else:
        form = GuestForm(instance=guest)
    
    return render(request, 'reservations/guest_form.html', {
        'form': form,
        'guest': guest,
        'title': f'Edit Guest: {guest.full_name}'
    })


# =============================================================================
# ROOM MANAGEMENT
# =============================================================================

@login_required
def room_list(request):
    """List all rooms with status."""
    rooms = Room.objects.all()
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        rooms = rooms.filter(status=status)
    
    # Filter by type
    room_type = request.GET.get('type')
    if room_type:
        rooms = rooms.filter(room_type=room_type)
    
    # Filter by floor
    floor = request.GET.get('floor')
    if floor:
        rooms = rooms.filter(floor=floor)
    
    rooms = rooms.order_by('room_number')
    
    # Get floors for filter
    floors = Room.objects.values_list('floor', flat=True).distinct().order_by('floor')
    
    return render(request, 'reservations/room_list.html', {
        'rooms': rooms,
        'floors': floors,
        'status_choices': Room.STATUS_CHOICES,
        'type_choices': Room.ROOM_TYPE_CHOICES
    })


@login_required
def room_detail(request, pk):
    """View room details."""
    room = get_object_or_404(Room, pk=pk)
    
    # Get current and upcoming reservations
    today = timezone.now().date()
    current_reservation = Reservation.objects.filter(
        room=room,
        status=Reservation.STATUS_CHECKED_IN
    ).first()
    
    upcoming_reservations = Reservation.objects.filter(
        room=room,
        check_in_date__gte=today,
        status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]
    ).order_by('check_in_date')[:5]
    
    return render(request, 'reservations/room_detail.html', {
        'room': room,
        'current_reservation': current_reservation,
        'upcoming_reservations': upcoming_reservations
    })


@login_required
def room_create(request):
    """Create a new room."""
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save()
            messages.success(request, f'Room {room.room_number} created successfully.')
            return redirect('reservations:room_list')
    else:
        form = RoomForm()
    
    return render(request, 'reservations/room_form.html', {
        'form': form,
        'title': 'Create New Room'
    })


@login_required
def room_edit(request, pk):
    """Edit room details."""
    room = get_object_or_404(Room, pk=pk)
    
    if request.method == 'POST':
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            messages.success(request, f'Room {room.room_number} updated successfully.')
            return redirect('reservations:room_detail', pk=room.pk)
    else:
        form = RoomForm(instance=room)
    
    return render(request, 'reservations/room_form.html', {
        'form': form,
        'room': room,
        'title': f'Edit Room: {room.room_number}'
    })


@login_required
@require_POST
def room_update_status(request, pk):
    """Update room status via AJAX."""
    room = get_object_or_404(Room, pk=pk)
    new_status = request.POST.get('status')
    
    if new_status in dict(Room.STATUS_CHOICES):
        room.status = new_status
        room.save()
        return JsonResponse({'success': True, 'status': room.get_status_display()})
    
    return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)


# =============================================================================
# RESERVATION MANAGEMENT
# =============================================================================

@login_required
def reservation_list(request):
    """List all reservations."""
    reservations = Reservation.objects.select_related('guest', 'room').all()
    
    # Search
    query = request.GET.get('query', '')
    if query:
        reservations = reservations.filter(
            Q(reservation_number__icontains=query) |
            Q(guest__first_name__icontains=query) |
            Q(guest__last_name__icontains=query) |
            Q(room__room_number__icontains=query)
        )
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        reservations = reservations.filter(status=status)
    
    # Filter by date
    date_from = request.GET.get('date_from')
    if date_from:
        reservations = reservations.filter(check_in_date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        reservations = reservations.filter(check_in_date__lte=date_to)
    
    reservations = reservations.order_by('-check_in_date')
    paginator = Paginator(reservations, 20)
    page = request.GET.get('page', 1)
    reservations = paginator.get_page(page)
    
    form = ReservationSearchForm(request.GET)
    
    return render(request, 'reservations/reservation_list.html', {
        'reservations': reservations,
        'form': form
    })


@login_required
def reservation_detail(request, pk):
    """View reservation details."""
    reservation = get_object_or_404(
        Reservation.objects.select_related('guest', 'room'),
        pk=pk
    )
    notes = reservation.notes.select_related('created_by').all()
    note_form = ReservationNoteForm()
    
    # Get guest documents
    from documents.models import GuestDocument
    documents = GuestDocument.objects.filter(guest=reservation.guest).order_by('-uploaded_at')
    
    return render(request, 'reservations/reservation_detail.html', {
        'reservation': reservation,
        'notes': notes,
        'note_form': note_form,
        'documents': documents
    })


@login_required
def reservation_create(request, guest_id=None):
    """Create a new reservation."""
    initial = {}
    guest = None
    
    if guest_id:
        guest = get_object_or_404(Guest, pk=guest_id)
        initial['guest'] = guest
    
    if request.method == 'POST':
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.created_by = request.user
            
            # Set rate from room if not specified
            if not reservation.rate_per_night and reservation.room:
                reservation.rate_per_night = reservation.room.base_rate
            
            reservation.save()
            
            log_activity(
                request.user,
                ActivityLog.ACTION_CREATE_RESERVATION,
                f'Created reservation {reservation.reservation_number}',
                request=request,
                related_model='Reservation',
                related_id=reservation.pk
            )
            
            messages.success(request, f'Reservation {reservation.reservation_number} created successfully.')
            return redirect('reservations:reservation_detail', pk=reservation.pk)
    else:
        form = ReservationForm(initial=initial)
    
    return render(request, 'reservations/reservation_form.html', {
        'form': form,
        'guest': guest,
        'title': 'Create New Reservation'
    })


@login_required
def reservation_edit(request, pk):
    """Edit reservation details."""
    reservation = get_object_or_404(Reservation, pk=pk)
    
    if reservation.status in [Reservation.STATUS_CHECKED_OUT, Reservation.STATUS_CANCELLED]:
        messages.error(request, 'Cannot edit a completed or cancelled reservation.')
        return redirect('reservations:reservation_detail', pk=pk)
    
    if request.method == 'POST':
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            form.save()
            
            log_activity(
                request.user,
                ActivityLog.ACTION_UPDATE_RESERVATION,
                f'Updated reservation {reservation.reservation_number}',
                request=request,
                related_model='Reservation',
                related_id=reservation.pk
            )
            
            messages.success(request, f'Reservation {reservation.reservation_number} updated successfully.')
            return redirect('reservations:reservation_detail', pk=reservation.pk)
    else:
        form = ReservationForm(instance=reservation)
    
    return render(request, 'reservations/reservation_form.html', {
        'form': form,
        'reservation': reservation,
        'title': f'Edit Reservation: {reservation.reservation_number}'
    })


@login_required
def quick_reservation(request):
    """Quick reservation for walk-in guests."""
    if request.method == 'POST':
        form = QuickReservationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            # Create or get guest
            guest, created = Guest.objects.get_or_create(
                passport_number=data['passport_number'] if data['passport_number'] else None,
                defaults={
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'email': data.get('email', ''),
                    'phone_number': data.get('phone_number', ''),
                    'created_by': request.user
                }
            )
            
            if not created:
                # Update guest info
                guest.first_name = data['first_name']
                guest.last_name = data['last_name']
                if data.get('email'):
                    guest.email = data['email']
                if data.get('phone_number'):
                    guest.phone_number = data['phone_number']
                guest.save()
            
            # Create reservation
            room = data['room']
            reservation = Reservation.objects.create(
                guest=guest,
                room=room,
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                adults=data['adults'],
                children=data['children'],
                rate_per_night=room.base_rate,
                special_requests=data.get('special_requests', ''),
                status=Reservation.STATUS_CONFIRMED,
                created_by=request.user
            )
            
            log_activity(
                request.user,
                ActivityLog.ACTION_CREATE_RESERVATION,
                f'Quick reservation {reservation.reservation_number} for walk-in',
                request=request,
                related_model='Reservation',
                related_id=reservation.pk
            )
            
            messages.success(request, f'Reservation {reservation.reservation_number} created for {guest.full_name}.')
            return redirect('reservations:check_in', pk=reservation.pk)
    else:
        form = QuickReservationForm()
    
    return render(request, 'reservations/quick_reservation.html', {
        'form': form
    })


@login_required
def check_in(request, pk):
    """Check in a reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    
    if reservation.status not in [Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]:
        messages.error(request, 'This reservation cannot be checked in.')
        return redirect('reservations:reservation_detail', pk=pk)
    
    if request.method == 'POST':
        form = CheckInForm(request.POST)
        if form.is_valid():
            # Assign room if changed
            if form.cleaned_data.get('room'):
                reservation.room = form.cleaned_data['room']
            
            if not reservation.room:
                messages.error(request, 'Please assign a room before checking in.')
                return render(request, 'reservations/check_in.html', {
                    'reservation': reservation,
                    'form': form
                })
            
            # Update reservation
            reservation.status = Reservation.STATUS_CHECKED_IN
            reservation.actual_check_in = timezone.now()
            reservation.checked_in_by = request.user
            
            if form.cleaned_data.get('access_card_number'):
                reservation.access_card_number = form.cleaned_data['access_card_number']
                reservation.access_card_issued = True
            
            reservation.save()
            
            # Update room status
            reservation.room.status = Room.STATUS_OCCUPIED
            reservation.room.save()
            
            # Add note if provided
            if form.cleaned_data.get('notes'):
                ReservationNote.objects.create(
                    reservation=reservation,
                    note=f"Check-in note: {form.cleaned_data['notes']}",
                    created_by=request.user
                )
            
            log_activity(
                request.user,
                ActivityLog.ACTION_CHECKIN,
                f'Checked in {reservation.guest.full_name} to Room {reservation.room.room_number}',
                request=request,
                related_model='Reservation',
                related_id=reservation.pk
            )
            
            messages.success(request, f'{reservation.guest.full_name} checked in to Room {reservation.room.room_number}.')
            return redirect('reservations:reservation_detail', pk=pk)
    else:
        form = CheckInForm()
    
    # Get available rooms
    available_rooms = Room.objects.filter(status=Room.STATUS_AVAILABLE)
    
    return render(request, 'reservations/check_in.html', {
        'reservation': reservation,
        'form': form,
        'available_rooms': available_rooms
    })


@login_required
def check_out(request, pk):
    """Check out a reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    
    if reservation.status != Reservation.STATUS_CHECKED_IN:
        messages.error(request, 'This reservation cannot be checked out.')
        return redirect('reservations:reservation_detail', pk=pk)
    
    if request.method == 'POST':
        form = CheckOutForm(request.POST)
        if form.is_valid():
            # Record payment if provided
            if form.cleaned_data.get('payment_amount'):
                reservation.amount_paid += form.cleaned_data['payment_amount']
                if reservation.amount_paid >= reservation.total_amount:
                    reservation.payment_status = Reservation.PAYMENT_PAID
                else:
                    reservation.payment_status = Reservation.PAYMENT_PARTIAL
            
            # Update reservation
            reservation.status = Reservation.STATUS_CHECKED_OUT
            reservation.actual_check_out = timezone.now()
            reservation.checked_out_by = request.user
            reservation.save()
            
            # Update room status to cleaning
            if reservation.room:
                reservation.room.status = Room.STATUS_CLEANING
                reservation.room.save()
            
            # Add note if provided
            if form.cleaned_data.get('notes'):
                ReservationNote.objects.create(
                    reservation=reservation,
                    note=f"Check-out note: {form.cleaned_data['notes']}",
                    created_by=request.user
                )
            
            log_activity(
                request.user,
                ActivityLog.ACTION_CHECKOUT,
                f'Checked out {reservation.guest.full_name} from Room {reservation.room.room_number}',
                request=request,
                related_model='Reservation',
                related_id=reservation.pk
            )
            
            messages.success(request, f'{reservation.guest.full_name} checked out successfully.')
            return redirect('reservations:reservation_detail', pk=pk)
    else:
        form = CheckOutForm(initial={'payment_amount': reservation.balance_due})
    
    return render(request, 'reservations/check_out.html', {
        'reservation': reservation,
        'form': form
    })


@login_required
@require_POST
def reservation_cancel(request, pk):
    """Cancel a reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    
    if reservation.status in [Reservation.STATUS_CHECKED_IN, Reservation.STATUS_CHECKED_OUT]:
        return JsonResponse({'success': False, 'error': 'Cannot cancel this reservation'}, status=400)
    
    reservation.status = Reservation.STATUS_CANCELLED
    reservation.save()
    
    # Free up the room
    if reservation.room:
        reservation.room.status = Room.STATUS_AVAILABLE
        reservation.room.save()
    
    log_activity(
        request.user,
        ActivityLog.ACTION_CANCEL_RESERVATION,
        f'Cancelled reservation {reservation.reservation_number}',
        request=request,
        related_model='Reservation',
        related_id=reservation.pk
    )
    
    messages.success(request, f'Reservation {reservation.reservation_number} cancelled.')
    return JsonResponse({'success': True})


@login_required
@require_POST
def reservation_add_note(request, pk):
    """Add a note to a reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    
    form = ReservationNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.reservation = reservation
        note.created_by = request.user
        note.save()
        messages.success(request, 'Note added successfully.')
    
    return redirect('reservations:reservation_detail', pk=pk)


# =============================================================================
# ARRIVALS & DEPARTURES
# =============================================================================

@login_required
def arrivals(request):
    """View today's and upcoming arrivals."""
    today = timezone.now().date()
    
    date_filter = request.GET.get('date', str(today))
    
    arrivals = Reservation.objects.filter(
        check_in_date=date_filter,
        status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]
    ).select_related('guest', 'room').order_by('room__room_number')
    
    return render(request, 'reservations/arrivals.html', {
        'arrivals': arrivals,
        'date': date_filter,
        'today': today
    })


@login_required
def departures(request):
    """View today's and upcoming departures."""
    today = timezone.now().date()
    
    date_filter = request.GET.get('date', str(today))
    
    departures = Reservation.objects.filter(
        check_out_date=date_filter,
        status=Reservation.STATUS_CHECKED_IN
    ).select_related('guest', 'room').order_by('room__room_number')
    
    return render(request, 'reservations/departures.html', {
        'departures': departures,
        'date': date_filter,
        'today': today
    })


@login_required
def in_house(request):
    """View all in-house guests."""
    in_house = Reservation.objects.filter(
        status=Reservation.STATUS_CHECKED_IN
    ).select_related('guest', 'room').order_by('room__room_number')
    
    return render(request, 'reservations/in_house.html', {
        'reservations': in_house
    })
