import threading
import time
import datetime
import os
import tempfile
import json
import base64
import logging
from functools import wraps
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse, Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from . import emulator as db
from django.utils.dateparse import parse_date

# MRZ and document modules
from .mrz_parser import get_mrz_parser, extract_passport_data, MRZExtractionError
from .document_filler import get_document_filler, fill_registration_card

# MRZ API client for microservice communication
from .mrz_api_client import (
    get_mrz_client, 
    MRZAPIError, 
    convert_mrz_to_kiosk_format,
    get_document_client,
    MRZDocumentClient
)

# Check if we should use the MRZ microservice
USE_MRZ_SERVICE = os.environ.get('MRZ_SERVICE_URL') is not None

# Logger for kiosk views
logger = logging.getLogger(__name__)

# Front desk phone number (configurable via environment)
FRONT_DESK_PHONE = os.environ.get('FRONT_DESK_PHONE', '0')


# ============================================================================
# ERROR HANDLING UTILITIES
# ============================================================================

class KioskError(Exception):
    """Base exception for kiosk errors that should show the error page."""
    def __init__(self, message, error_code=None):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class DatabaseError(KioskError):
    """Database connection or query error."""
    pass


class SessionError(KioskError):
    """Missing or invalid session data."""
    pass


class ReservationNotFoundError(KioskError):
    """Reservation not found for checkout."""
    pass


def render_error(request, message, error_code=None):
    """
    Render the error page with Call Front Desk option.
    Use this instead of redirecting back to previous steps.
    """
    return render(request, 'kiosk/error.html', {
        'error_message': message,
        'error_code': error_code,
        'front_desk_phone': FRONT_DESK_PHONE,
    })


def handle_kiosk_errors(view_func):
    """
    Decorator to catch database and session errors in kiosk views.
    Displays error page with Call Front Desk option instead of crashing.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except KioskError as e:
            logger.error(f"Kiosk error in {view_func.__name__}: {e.message}")
            return render_error(request, e.message, e.error_code)
        except Http404:
            # Re-raise Http404 to let Django handle it
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in {view_func.__name__}: {e}")
            return render_error(
                request, 
                "An unexpected error occurred. Please contact the front desk for assistance.",
                error_code="UNEXPECTED_ERROR"
            )
    return wrapper


def error_page(request):
    """
    Generic error page with Call Front Desk option.
    Can be accessed directly or via redirect with query params.
    """
    error_message = request.GET.get('message', 'Something went wrong while processing your request.')
    error_code = request.GET.get('code')
    
    return render(request, 'kiosk/error.html', {
        'error_message': error_message,
        'error_code': error_code,
        'front_desk_phone': FRONT_DESK_PHONE,
    })


# ============================================================================
# DASHBOARD INTEGRATION
# ============================================================================

def create_dashboard_guest_account(guest_data, reservation_data, room_number):
    """
    Create a guest account in the Dashboard for room access.
    
    Args:
        guest_data: Dict with guest info (first_name, last_name, email, phone, etc.)
        reservation_data: Dict with reservation info (checkout date)
        room_number: Room number string
    
    Returns:
        dict: Account credentials {'username': ..., 'password': ...} or None on failure
    """
    try:
        import requests
        
        dashboard_url = os.environ.get('DASHBOARD_API_URL', 'http://dashboard:8001')
        api_token = os.environ.get('KIOSK_API_TOKEN', '')
        
        if not dashboard_url:
            logger.warning("Dashboard API URL not configured")
            return None
        
        # Prepare request data
        checkout_date = reservation_data.get('checkout', '')
        if checkout_date and isinstance(checkout_date, str):
            # Ensure ISO format
            if 'T' not in checkout_date:
                checkout_date = f"{checkout_date}T12:00:00"
        
        payload = {
            'first_name': guest_data.get('first_name', ''),
            'last_name': guest_data.get('last_name', ''),
            'email': guest_data.get('email', ''),
            'room_number': str(room_number),
            'checkout_date': checkout_date,
            'passport_number': guest_data.get('passport_number', ''),
            'phone': guest_data.get('phone', '')
        }
        
        headers = {'Content-Type': 'application/json'}
        if api_token:
            headers['Authorization'] = f'Token {api_token}'
        
        response = requests.post(
            f'{dashboard_url}/api/guests/create/',
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"Dashboard guest account created: {result.get('username')}")
            return {
                'username': result.get('username'),
                'password': result.get('password'),
                'room_number': result.get('room_number'),
                'expires_at': result.get('expires_at')
            }
        else:
            logger.error(f"Dashboard API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to create Dashboard guest account: {e}")
        return None


def deactivate_dashboard_guest_account(username=None, room_number=None):
    """
    Deactivate a guest account in the Dashboard on checkout.
    
    Args:
        username: Guest username to deactivate
        room_number: Or room number to find and deactivate guest
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import requests
        
        dashboard_url = os.environ.get('DASHBOARD_API_URL', 'http://dashboard:8001')
        api_token = os.environ.get('KIOSK_API_TOKEN', '')
        
        if not dashboard_url:
            logger.warning("Dashboard API URL not configured")
            return False
        
        payload = {}
        if username:
            payload['username'] = username
        elif room_number:
            payload['room_number'] = str(room_number)
        else:
            return False
        
        headers = {'Content-Type': 'application/json'}
        if api_token:
            headers['Authorization'] = f'Token {api_token}'
        
        response = requests.post(
            f'{dashboard_url}/api/guests/deactivate/',
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"Dashboard guest account deactivated")
            return True
        else:
            logger.error(f"Dashboard API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to deactivate Dashboard guest account: {e}")
        return False


def start(request):
    return render(request, 'kiosk/start.html')


@csrf_exempt
def upload_scan(request):
    if request.method == 'POST':
        # create extraction task
        task = db.create_task(status='processing')
        tid = task['id']

        # Get uploaded file
        uploaded_file = request.FILES.get('scan')
        
        # Save uploaded file temporarily for MRZ processing
        temp_path = None
        image_bytes = None
        if uploaded_file:
            # Create temp directory if needed
            temp_dir = os.path.join(settings.BASE_DIR, 'media', 'temp_scans')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, f"scan_{tid}_{uploaded_file.name}")
            
            # Read image bytes for API call
            image_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset for saving
            
            with open(temp_path, 'wb+') as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)

        def process_task_with_api(tid, image_bytes, filename):
            """Process using MRZ microservice API"""
            try:
                client = get_mrz_client()
                result = client.extract_from_image(image_bytes, filename)
                data = convert_mrz_to_kiosk_format(result.get('data', {}))
                db.set_task_data(tid, data)
            except MRZAPIError as e:
                # API error - fall back to local parser
                process_task_local(tid, temp_path)
            except Exception as e:
                db.set_task_data(tid, {'error': str(e)})

        def process_task_local(tid, image_path):
            """Process using local MRZ parser (fallback/demo mode)"""
            try:
                # Use MRZ parser for extraction
                parser = get_mrz_parser()
                if image_path and os.path.exists(image_path):
                    data = parser.extract_to_kiosk_format(image_path)
                else:
                    # Fallback to mock data if no image
                    data = parser.extract_to_kiosk_format("demo_passport.jpg")
                
                db.set_task_data(tid, data)
            except MRZExtractionError as e:
                # On extraction error, still provide partial/mock data
                data = {
                    'first_name': '',
                    'last_name': '',
                    'passport_number': '',
                    'date_of_birth': '',
                    'error': str(e),
                }
                db.set_task_data(tid, data)
            except Exception as e:
                db.set_task_data(tid, {'error': str(e)})

        # Choose processing method based on configuration
        if USE_MRZ_SERVICE and image_bytes:
            filename = uploaded_file.name if uploaded_file else 'passport.jpg'
            threading.Thread(
                target=process_task_with_api, 
                args=(tid, image_bytes, filename), 
                daemon=True
            ).start()
        else:
            threading.Thread(
                target=process_task_local, 
                args=(tid, temp_path), 
                daemon=True
            ).start()
        
        return JsonResponse({'task_id': tid})
    return JsonResponse({'error': 'POST only'}, status=400)


def extract_status(request, task_id):
    task = db.get_task(task_id)
    if not task:
        raise Http404('task not found')
    return JsonResponse({'status': task.get('status'), 'data': task.get('data')})


@csrf_exempt
@handle_kiosk_errors
def verify_info(request):
    if request.method == 'POST':
        data = dict(request.POST)
        # normalize
        first_name = data.get('first_name', [''])[0]
        last_name = data.get('last_name', [''])[0]
        passport = data.get('passport_number', [''])[0]
        dob = parse_date(data.get('date_of_birth', [''])[0])
        
        # Handle multiselect access methods (access_keycard, access_face)
        access_methods = []
        if data.get('access_keycard', [''])[0]:
            access_methods.append('keycard')
        if data.get('access_face', [''])[0]:
            access_methods.append('face')
        
        # Fallback to legacy single access_method field
        if not access_methods:
            legacy_method = data.get('access_method', ['keycard'])[0]
            if legacy_method:
                access_methods = [m.strip() for m in legacy_method.split(',') if m.strip()]
        
        # Default to keycard if nothing selected
        if not access_methods:
            access_methods = ['keycard']

        # Validate required fields - show error instead of looping
        if not first_name or not last_name:
            return render_error(
                request,
                "We couldn't read your passport information. Please ask the front desk for assistance.",
                error_code="PASSPORT_READ_ERROR"
            )

        try:
            guest = db.get_or_create_guest(first_name, last_name, passport, dob)
        except Exception as e:
            logger.error(f"Database error creating guest: {e}")
            return render_error(
                request,
                "We're experiencing technical difficulties. Please contact the front desk.",
                error_code="DATABASE_ERROR"
            )
        
        request.session['guest_id'] = guest['id']
        request.session['access_method'] = ','.join(access_methods)
        request.session['pending_access_methods'] = access_methods

        # Try find reservation by reservation_number or guest
        res_number = data.get('reservation_number', [''])[0]
        reservation = None
        
        try:
            if res_number:
                reservation = db.get_reservation_by_number(res_number)

            if not reservation:
                # Try to find by guest
                res_qs = db.get_reservations_by_guest(guest)
                if res_qs:
                    reservation = res_qs[0]
        except Exception as e:
            logger.error(f"Database error finding reservation: {e}")
            return render_error(
                request,
                "We're experiencing technical difficulties. Please contact the front desk.",
                error_code="DATABASE_ERROR"
            )

        # Get the flow type from session
        flow_type = request.session.get('flow_type', 'checkin')

        if reservation:
            # Reservation found - store it and go to document signing
            request.session['reservation_id'] = reservation['id']
            
            if flow_type == 'checkout':
                # Checkout flow - go directly to finalize with checkout context
                return redirect('kiosk:finalize', reservation_id=reservation['id'])
            else:
                # Checkin flow - go to document signing
                return redirect('kiosk:document_signing')

        # No reservation found
        if flow_type == 'checkout':
            # WALK-IN TRYING TO CHECKOUT - Show error page
            # This is a critical case: someone who never checked in is trying to check out
            return render_error(
                request,
                "No reservation found for check-out. If you made a reservation, please contact the front desk with your confirmation number. If you're a walk-in guest, please select 'Check In' instead.",
                error_code="NO_RESERVATION_CHECKOUT"
            )
        
        # Checkin flow without reservation - go to walk-in page
        return redirect('kiosk:walkin')

    # GET
    return JsonResponse({'error': 'POST only'}, status=400)


# reservation_api removed — demo no longer exposes API endpoint


def advertisement(request):
    return render(request, 'kiosk/advertisement.html', {'no_translate': True})


def choose_language(request):
    if request.method == 'POST':
        lang = request.POST.get('language', 'en')
        request.session['language'] = lang
        resp = redirect('kiosk:checkin')
        # also set a cookie so client-side JS can read language immediately
        resp.set_cookie('kiosk_language', lang, max_age=30 * 24 * 3600)
        return resp
    return render(request, 'kiosk/language.html', {'no_translate': True})


def checkin(request):
    """
    Check-in/Check-out choice page.
    Sets the flow_type in session to track whether guest is checking in or out.
    """
    if request.method == 'POST':
        flow_type = request.POST.get('flow_type', 'checkin')
        request.session['flow_type'] = flow_type
        # Clear any stale session data from previous flow
        for key in ['guest_id', 'reservation_id', 'access_method', 'room_payload', 'pending_access_methods']:
            request.session.pop(key, None)
        
        # For checkout, we'll verify they have a reservation after passport scan
        # The verify_info view will handle the "walk-in trying to checkout" case
        return redirect('kiosk:start')
    lang = request.session.get('language', 'en')
    return render(request, 'kiosk/checkin.html', {'kiosk_language': lang, 'no_translate': False})


def documentation(request):
    # Read passport fields from query params for demo printing
    data = {
        'first_name': request.GET.get('first_name', ''),
        'last_name': request.GET.get('last_name', ''),
        'passport_number': request.GET.get('passport_number', ''),
        'date_of_birth': request.GET.get('date_of_birth', ''),
    }
    # try to find a reservation for the current session guest (if any)
    reservation = None
    guest_id = request.session.get('guest_id')
    if guest_id:
        res_qs = db.get_reservations_by_guest(int(guest_id))
        if res_qs:
            reservation = res_qs[-1]

    # If POST, handle either passport correction or registration submission/preview/confirm
    if request.method == 'POST':
        # Registration flow detection: presence of 'surname' or people_count indicates registration card
        if request.POST.get('surname') or request.POST.get('people_count'):
            # collect registration fields
            reg = {
                'surname': request.POST.get('surname', '').strip(),
                'name': request.POST.get('name', '').strip(),
                'nationality': request.POST.get('nationality', '').strip(),
                'passport_number': request.POST.get('passport_number', '').strip(),
                'date_of_birth': request.POST.get('date_of_birth', '').strip(),
                'profession': request.POST.get('profession', '').strip(),
                'hometown': request.POST.get('hometown', '').strip(),
                'country': request.POST.get('country', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'phone': request.POST.get('phone', '').strip(),
                'checkin': request.POST.get('checkin', '').strip(),
                'checkout': request.POST.get('checkout', '').strip(),
            }

            try:
                people_count = max(1, int(request.POST.get('people_count') or 1))
            except Exception:
                people_count = 1
            accompany_count = max(0, people_count - 1)

            accompany = []
            for i in range(1, accompany_count + 1):
                nm = request.POST.get(f'accompany_name_{i}', '').strip()
                if nm:
                    accompany.append({'name': nm, 'nationality': request.POST.get(f'accompany_nationality_{i}', '').strip(), 'passport': request.POST.get(f'accompany_passport_{i}', '').strip()})
            signature_method = request.POST.get('signature_method', 'physical')

            # Confirm registration: persist guest and continue to signing
            if request.POST.get('action') == 'confirm_registration':
                # Parse name (may be "FIRST LAST" or just first name)
                full_name = reg.get('name', '').strip()
                surname = reg.get('surname', '').strip()
                if ' ' in full_name and not surname:
                    parts = full_name.split(' ', 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ''
                else:
                    first_name = full_name
                    last_name = surname
                
                # Parse date of birth
                dob_str = reg.get('date_of_birth', '')
                dob = parse_date(dob_str) if dob_str else None
                
                # Persist guest to database
                guest = db.get_or_create_guest(
                    first_name=first_name,
                    last_name=last_name,
                    passport_number=reg.get('passport_number', ''),
                    date_of_birth=dob
                )
                request.session['guest_id'] = guest['id']
                
                # Store registration data in session for document filling
                request.session['registration_data'] = {
                    'guest': reg,
                    'accompany': accompany,
                    'accompany_count': accompany_count,
                    'people_count': people_count,
                    'signature_method': signature_method,
                }
                
                return redirect('kiosk:document_signing')

            # Otherwise render registration preview
            return render(request, 'kiosk/registration_preview.html', {'data': reg, 'accompany': accompany, 'accompany_count': accompany_count, 'signature_method': signature_method})

        # Passport correction path (existing behavior)
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        passport_number = request.POST.get('passport_number', '').strip()
        dob = parse_date(request.POST.get('date_of_birth', '') or '')

        if first_name and last_name:
            guest = db.get_or_create_guest(first_name, last_name, passport_number or '', dob)
            request.session['guest_id'] = guest['id']
            return redirect('kiosk:document_signing')

    return render(request, 'kiosk/documentation.html', {'data': data, 'reservation': reservation})


def registration_form(request):
    """Show a registration card form (based on paper.txt) for guest input."""
    # Prefill from query or session if available
    initial = {
        'surname': request.GET.get('surname', ''),
        'name': request.GET.get('name', ''),
        'nationality': request.GET.get('nationality', ''),
        'passport_number': request.GET.get('passport_number', ''),
        'date_of_birth': request.GET.get('date_of_birth', ''),
        'profession': request.GET.get('profession', ''),
        'hometown': request.GET.get('hometown', ''),
        'country': request.GET.get('country', ''),
        'email': request.GET.get('email', ''),
        'phone': request.GET.get('phone', ''),
        'checkin': request.GET.get('checkin', ''),
        'checkout': request.GET.get('checkout', ''),
        'people_count': request.GET.get('people_count', '1'),
    }
    return render(request, 'kiosk/registration_form.html', {'initial': initial})


def registration_preview(request):
    """Render a well-formatted registration card preview with signature options.

    POST: expects form fields from `registration_form`. If `action=confirm` then
    create guest in emulator and set session, then redirect to reservation entry.
    """
    if request.method != 'POST':
        return redirect('kiosk:registration_form')

    # collect common fields
    data = {
        'surname': request.POST.get('surname', '').strip(),
        'name': request.POST.get('name', '').strip(),
        'nationality': request.POST.get('nationality', '').strip(),
        'passport_number': request.POST.get('passport_number', '').strip(),
        'date_of_birth': request.POST.get('date_of_birth', '').strip(),
        'profession': request.POST.get('profession', '').strip(),
        'hometown': request.POST.get('hometown', '').strip(),
        'country': request.POST.get('country', '').strip(),
        'email': request.POST.get('email', '').strip(),
        'phone': request.POST.get('phone', '').strip(),
        'checkin': request.POST.get('checkin', '').strip(),
        'checkout': request.POST.get('checkout', '').strip(),
    }

    # people_count controls how many accompany lines to render (excluding main guest)
    try:
        people_count = max(1, int(request.POST.get('people_count') or 1))
    except Exception:
        people_count = 1
    accompany_count = max(0, people_count - 1)

    accompany = []
    # Expect accompany entries like accompany_name_1, accompany_nationality_1, accompany_passport_1
    for i in range(1, accompany_count + 1):
        name_k = f'accompany_name_{i}'
        nat_k = f'accompany_nationality_{i}'
        pass_k = f'accompany_passport_{i}'
        nm = request.POST.get(name_k, '').strip()
        if nm:
            accompany.append({'name': nm, 'nationality': request.POST.get(nat_k, '').strip(), 'passport': request.POST.get(pass_k, '').strip()})

    signature_method = request.POST.get('signature_method', 'physical')

    # If this is a confirm submission, persist guest and continue
    if request.POST.get('action') == 'confirm':
        # create guest in emulator (use surname/name order)
        first = data.get('name') or ''
        last = data.get('surname') or ''
        passport = data.get('passport_number') or ''
        dob = data.get('date_of_birth') or None
        guest = db.create_guest(first, last, passport, dob)
        request.session['guest_id'] = guest['id']
        # store the raw registration doc for later reference
        request.session['registration_document'] = {'data': data, 'accompany': accompany, 'signature_method': signature_method}
        return redirect('kiosk:reservation_entry')

    # render preview (not persisted yet)
    return render(request, 'kiosk/registration_preview.html', {'data': data, 'accompany': accompany, 'accompany_count': accompany_count, 'signature_method': signature_method})


@handle_kiosk_errors
def document_signing(request):
    """
    Document signing page - LINEAR FLOW (no loops).
    
    Flow:
    1. Guest signs document digitally (canvas signature)
    2. Assign room and apply access methods
    3. Go to face enrollment OR finalize (never back)
    
    If no reservation/guest: show error page (don't loop)
    """
    guest_id = request.session.get('guest_id')
    reservation_id = request.session.get('reservation_id')
    
    # GUARD: No guest = show error (don't loop)
    if not guest_id:
        return render_error(
            request,
            "Your session has expired. Please start over or contact the front desk for assistance.",
            error_code="SESSION_EXPIRED"
        )
    
    # Try to get reservation from session or by guest lookup
    reservation = None
    try:
        if reservation_id:
            reservation = db.get_reservation(int(reservation_id))
        else:
            guest = db.get_guest(int(guest_id))
            if guest:
                res_qs = db.get_reservations_by_guest(guest)
                if res_qs:
                    reservation = res_qs[-1]
                    request.session['reservation_id'] = reservation['id']
    except Exception as e:
        logger.error(f"Database error in document_signing: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )

    # GUARD: No reservation = show error (don't loop back)
    if not reservation:
        return render_error(
            request,
            "Your reservation information could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )

    if request.method == 'POST':
        # Save digital signature if provided
        signature_data = request.POST.get('signature_data', '')
        if signature_data and signature_data.startswith('data:image/png;base64,'):
            try:
                # Save signature to file
                sig_dir = os.path.join(settings.BASE_DIR, 'media', 'signatures')
                os.makedirs(sig_dir, exist_ok=True)
                sig_filename = f"signature_{reservation['id']}_{int(time.time())}.png"
                sig_path = os.path.join(sig_dir, sig_filename)
                
                # Decode and save
                sig_bytes = base64.b64decode(signature_data.split(',')[1])
                with open(sig_path, 'wb') as f:
                    f.write(sig_bytes)
                
                # Store path in session for later use
                request.session['signature_path'] = sig_path
                request.session['signature_filename'] = sig_filename
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to save signature: {e}")
        
        # Get access methods (pre-selected during passport scan)
        access_methods = request.session.get('pending_access_methods', ['keycard'])
        if not access_methods:
            access_methods = ['keycard']
        
        # Apply access methods
        request.session['access_method'] = ','.join(access_methods)
        
        # Assign room
        room_number = str(100 + (reservation['id'] % 50))
        room_payload = {'room_number': room_number, 'access_methods': access_methods}
        
        # If keycard selected, generate and publish RFID token
        if 'keycard' in access_methods:
            try:
                from .mqtt_client import publish_rfid_token, generate_rfid_token
                token = generate_rfid_token()
                result = publish_rfid_token(
                    guest_id=reservation.get('guest_id'),
                    reservation_id=reservation['id'],
                    room_number=room_number,
                    token=token,
                    checkin=reservation.get('checkin'),
                    checkout=reservation.get('checkout')
                )
                request.session['rfid_token'] = token
                room_payload['rfid_token'] = token
                room_payload['rfid_published'] = result.get('published', False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"RFID token publish error: {e}")
        
        request.session['room_payload'] = room_payload
        request.session.pop('pending_access_methods', None)
        
        # Create guest account in Dashboard for room access
        guest = reservation.get('guest') or {}
        registration_data = request.session.get('registration_data', {})
        guest_info = registration_data.get('guest', {})
        
        # Merge guest info from reservation and registration
        dashboard_guest = {
            'first_name': guest.get('first_name') or guest_info.get('name', '').split()[0] if guest_info.get('name') else '',
            'last_name': guest.get('last_name') or guest_info.get('surname', ''),
            'email': guest_info.get('email', ''),
            'phone': guest_info.get('phone', ''),
            'passport_number': guest.get('passport_number') or guest_info.get('passport_number', ''),
        }
        
        dashboard_credentials = create_dashboard_guest_account(
            guest_data=dashboard_guest,
            reservation_data=reservation,
            room_number=room_number
        )
        
        if dashboard_credentials:
            request.session['dashboard_credentials'] = dashboard_credentials
            room_payload['dashboard_username'] = dashboard_credentials.get('username')
            request.session['room_payload'] = room_payload
        
        # FORWARD ONLY: face enrollment OR finalize
        if 'face' in access_methods:
            return redirect('kiosk:enroll_face', reservation_id=reservation['id'])
        return redirect('kiosk:finalize', reservation_id=reservation['id'])

    return render(request, 'kiosk/document_sign.html', {'reservation': reservation})


@handle_kiosk_errors
def choose_access(request, reservation_id):
    """
    Access method selection - LINEAR FLOW (no loops).
    
    This is a FALLBACK page only used if access methods weren't selected during passport scan.
    Flow: choose_access → enroll_face OR finalize
    Never redirects back to earlier steps.
    """
    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in choose_access: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not reservation:
        # GUARD: Invalid reservation = show error
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )
    
    # Pre-selected methods from session
    preselected = request.session.get('pending_access_methods', [])
    
    if request.method == 'POST':
        # Allow multiple access methods (checkboxes). Default to keycard if none selected.
        methods = []
        if request.POST.get('access_keycard'):
            methods.append('keycard')
        if request.POST.get('access_face'):
            methods.append('face')
        
        # Default to keycard if nothing selected (prevent validation loop)
        if not methods:
            methods = ['keycard']

        request.session['access_method'] = ','.join(methods)
        request.session.pop('pending_access_methods', None)
        
        # Assign room
        room_number = str(100 + (reservation['id'] % 50))
        room_payload = {'room_number': room_number, 'access_methods': methods}
        request.session['room_payload'] = room_payload

        # If keycard selected, generate and publish RFID token
        if 'keycard' in methods:
            try:
                from .mqtt_client import publish_rfid_token, generate_rfid_token
                token = generate_rfid_token()
                result = publish_rfid_token(
                    guest_id=reservation.get('guest_id'),
                    reservation_id=reservation['id'],
                    room_number=room_number,
                    token=token,
                    checkin=reservation.get('checkin'),
                    checkout=reservation.get('checkout')
                )
                request.session['rfid_token'] = token
                room_payload['rfid_token'] = token
                room_payload['rfid_published'] = result.get('published', False)
                request.session['room_payload'] = room_payload
            except Exception as e:
                logger.error(f"RFID token publish error: {e}")
                # Continue without RFID - staff can issue card manually

        # FORWARD ONLY: face enrollment OR finalize
        if 'face' in methods:
            return redirect('kiosk:enroll_face', reservation_id=reservation['id'])
        return redirect('kiosk:finalize', reservation_id=reservation['id'])

    return render(request, 'kiosk/choose_access.html', {
        'reservation': reservation,
        'preselected_keycard': 'keycard' in preselected,
        'preselected_face': 'face' in preselected
    })


@handle_kiosk_errors
def walkin(request):
    """
    Walk-in guest page - LINEAR FLOW (no loops).
    
    Shown when no reservation is found after passport verification.
    Guest can choose to create a new reservation.
    
    Flow: walkin → reservation_entry → document_signing → finalize
    If no guest: show error page (don't loop back to start)
    """
    guest_id = request.session.get('guest_id')
    
    # GUARD: No guest = show error (don't loop)
    if not guest_id:
        return render_error(
            request,
            "Your session has expired. Please start over or contact the front desk for assistance.",
            error_code="SESSION_EXPIRED"
        )
    
    try:
        guest = db.get_guest(int(guest_id))
    except Exception as e:
        logger.error(f"Database error getting guest: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not guest:
        return render_error(
            request,
            "Your guest information could not be found. Please start over or contact the front desk.",
            error_code="GUEST_NOT_FOUND"
        )
    
    return render(request, 'kiosk/walkin.html', {'guest': guest})


@handle_kiosk_errors
def reservation_entry(request):
    """
    Create reservation for walk-in guest - LINEAR FLOW (no loops).
    
    Flow: reservation_entry → document_signing → finalize
    Never redirects back to walkin or verify_info.
    If no guest: show error page (don't loop)
    """
    guest_id = request.session.get('guest_id')
    
    # GUARD: No guest = show error (don't loop)
    if not guest_id:
        return render_error(
            request,
            "Your session has expired. Please start over or contact the front desk for assistance.",
            error_code="SESSION_EXPIRED"
        )
    
    try:
        guest = db.get_guest(int(guest_id))
    except Exception as e:
        logger.error(f"Database error getting guest: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not guest:
        return render_error(
            request,
            "Your guest information could not be found. Please start over or contact the front desk.",
            error_code="GUEST_NOT_FOUND"
        )
    
    if request.method == 'POST':
        resnum = request.POST.get('reservation_number', '').strip()
        
        try:
            room_count = int(request.POST.get('room_count') or 1)
        except ValueError:
            room_count = 1
            
        try:
            people_count = int(request.POST.get('people_count') or request.POST.get('room_count') or 1)
        except ValueError:
            people_count = 1
            
        checkin = parse_date(request.POST.get('checkin') or '') or timezone.now().date()
        checkout = parse_date(request.POST.get('checkout') or '') or (timezone.now().date() + datetime.timedelta(days=1))
        
        # Auto-generate reservation number if not provided
        if not resnum:
            import secrets
            resnum = f"RES-{timezone.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
        
        try:
            res = db.create_reservation(resnum, guest, checkin, checkout, room_count=room_count, people_count=people_count)
        except Exception as e:
            logger.error(f"Database error creating reservation: {e}")
            return render_error(
                request,
                "We couldn't create your reservation. Please contact the front desk.",
                error_code="RESERVATION_CREATE_ERROR"
            )
        
        # Store reservation and ALWAYS go forward to document signing
        request.session['reservation_id'] = res['id']
        return redirect('kiosk:document_signing')

    # Auto-generate suggested reservation number
    import secrets
    suggested_resnum = f"RES-{timezone.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    
    return render(request, 'kiosk/reservation_entry.html', {
        'guest': guest,
        'suggested_resnum': suggested_resnum
    })


@handle_kiosk_errors
def enroll_face(request, reservation_id):
    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in enroll_face: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )
    # Emulate room capacity coming from an external DB/service
    room_payload = request.session.get('room_payload', {})
    room_number = room_payload.get('room_number') or str(100 + (reservation['id'] % 50))
    # simple emulated capacities
    emu_capacities = {
        '101': 2,
        '102': 4,
        '103': 3,
        '104': 2,
    }
    capacity = emu_capacities.get(room_number, max(1, reservation.get('people_count') or 1))

    existing = db.count_face_enrollments_for_reservation(reservation)
    remaining = max(0, capacity - existing)

    if request.method == 'POST':
        count = int(request.POST.get('count') or 0)
        if count <= 0:
            return render(request, 'kiosk/enroll_face.html', {'reservation': reservation, 'capacity': capacity, 'remaining': remaining, 'error': 'Please specify at least one photo to upload.'})
        if count > remaining:
            return render(request, 'kiosk/enroll_face.html', {'reservation': reservation, 'capacity': capacity, 'remaining': remaining, 'error': f'Only {remaining} enrollments remaining for room {room_number}.'})

        # accept uploads (store image names only)
        saved = 0
        for i in range(1, count + 1):
            f = request.FILES.get(f'face_{i}')
            if f:
                db.create_face_enrollment(reservation['guest'], reservation, existing + saved + 1, image_name=getattr(f, 'name', None))
                saved += 1
        return redirect('kiosk:finalize', reservation_id=reservation['id'])

    return render(request, 'kiosk/enroll_face.html', {'reservation': reservation, 'capacity': capacity, 'remaining': remaining})


@handle_kiosk_errors
def finalize(request, reservation_id):
    """
    Final page after check-in or check-out.
    
    Uses different templates based on flow_type:
    - checkin: Shows room directions video and welcome message
    - checkout: Shows card submittal and payment finalization
    """
    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in finalize: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )
    
    flow_type = request.session.get('flow_type', 'checkin')
    access_method = request.session.get('access_method', 'keycard')
    room_payload = request.session.get('room_payload') or {}
    room_number = room_payload.get('room_number') or reservation.get('room_number') or str(100 + (reservation_id % 50))
    rfid_token = room_payload.get('rfid_token')
    
    context = {
        'reservation': reservation, 
        'access_method': access_method, 
        'room_number': room_number,
        'rfid_token': rfid_token,
        'flow_type': flow_type
    }
    
    # Use different templates for check-in vs check-out
    if flow_type == 'checkout':
        lang = request.session.get('language', 'en')
        context['kiosk_language'] = lang
        return render(request, 'kiosk/finalize_checkout.html', context)
    else:
        lang = request.session.get('language', 'en')
        context['kiosk_language'] = lang
        return render(request, 'kiosk/finalize_checkin.html', context)


@handle_kiosk_errors
def submit_keycards(request, reservation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in submit_keycards: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )

    try:
        # mark keycards returned and finalize payment (demo: always finalize)
        db.submit_keycards(reservation)
        db.finalize_payment(reservation, amount=reservation.get('amount_due', 0) or 0)
        
        # Deactivate the guest's Dashboard account
        room_payload = request.session.get('room_payload') or {}
        room_number = room_payload.get('room_number') or reservation.get('room_number') or str(100 + (reservation_id % 50))
        dashboard_username = room_payload.get('dashboard_username')
        
        if dashboard_username:
            deactivate_dashboard_guest_account(username=dashboard_username)
        else:
            # Try by room number
            deactivate_dashboard_guest_account(room_number=room_number)
            
    except Exception as e:
        logger.error(f"Database error finalizing payment: {e}")
        return render_error(
            request,
            "We couldn't process your checkout. Please contact the front desk.",
            error_code="PAYMENT_ERROR"
        )

    return redirect('kiosk:finalize', reservation_id=reservation['id'])


@handle_kiosk_errors
def report_stolen_card(request, reservation_id):
    """
    Report a stolen or lost keycard and issue a new one.
    Revokes the old RFID token and generates a new one.
    """
    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in report_stolen_card: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR"
        )
    
    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND"
        )
    
    room_payload = request.session.get('room_payload') or {}
    room_number = room_payload.get('room_number') or str(100 + (reservation_id % 50))
    old_token = room_payload.get('rfid_token')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', 'stolen')
        
        try:
            from .mqtt_client import revoke_rfid_token, publish_rfid_token, generate_rfid_token
            
            # Revoke old token if exists
            if old_token:
                revoke_rfid_token(old_token, room_number, reason=reason)
            
            # Generate and publish new token
            new_token = generate_rfid_token()
            result = publish_rfid_token(
                guest_id=reservation.get('guest_id'),
                reservation_id=reservation['id'],
                room_number=room_number,
                token=new_token,
                checkin=reservation.get('checkin'),
                checkout=reservation.get('checkout')
            )
            
            # Update session with new token
            room_payload['rfid_token'] = new_token
            room_payload['rfid_published'] = result.get('published', False)
            request.session['room_payload'] = room_payload
            
            return render(request, 'kiosk/report_card_success.html', {
                'reservation': reservation,
                'room_number': room_number,
                'new_token': new_token,
                'reason': reason
            })
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Card report error: {e}")
            return render(request, 'kiosk/report_card.html', {
                'reservation': reservation,
                'room_number': room_number,
                'error': str(e)
            })
    
    return render(request, 'kiosk/report_card.html', {
        'reservation': reservation,
        'room_number': room_number
    })


@csrf_exempt
def revoke_rfid_card_api(request):
    """
    API endpoint to revoke an RFID card token.
    Used by staff dashboard or security systems.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get('token')
        room_number = data.get('room_number')
        reason = data.get('reason', 'revoked')
        
        if not token or not room_number:
            return JsonResponse({'error': 'token and room_number required'}, status=400)
        
        from .mqtt_client import revoke_rfid_token
        result = revoke_rfid_token(token, room_number, reason=reason)
        
        return JsonResponse({
            'success': result.get('success', False),
            'message': 'Token revoked' if result.get('success') else 'Revocation failed',
            'error': result.get('error')
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# DW Registration Card (DW R.C.) Document Views
# ============================================================================

def dw_registration_card(request):
    """
    Display and fill the DW Registration Card with guest data from passport extraction.
    Uses MRZ backend for document processing.
    
    GET: Show form pre-filled with data from session or query params
    POST: Send edited data to MRZ backend and proceed to signing
    """
    import uuid
    
    # Get or create session ID for document workflow
    document_session_id = request.session.get('document_session_id')
    if not document_session_id:
        document_session_id = str(uuid.uuid4())
        request.session['document_session_id'] = document_session_id
    
    # Get extracted data from session or query params
    extracted_data = request.session.get('extracted_passport_data', {})
    
    # Merge with query params (allows pre-filling from /document/ link)
    initial_data = {
        'surname': request.GET.get('surname') or request.GET.get('last_name') or extracted_data.get('last_name', ''),
        'name': request.GET.get('name') or request.GET.get('first_name') or extracted_data.get('first_name', ''),
        'nationality': request.GET.get('nationality') or extracted_data.get('nationality', ''),
        'nationality_code': request.GET.get('nationality_code') or extracted_data.get('nationality_code', ''),
        'passport_number': request.GET.get('passport_number') or extracted_data.get('passport_number', ''),
        'date_of_birth': request.GET.get('date_of_birth') or extracted_data.get('date_of_birth', ''),
        'country': request.GET.get('country') or extracted_data.get('issuer_country', ''),
        'profession': request.GET.get('profession', ''),
        'hometown': request.GET.get('hometown', ''),
        'email': request.GET.get('email', ''),
        'phone': request.GET.get('phone', ''),
        'checkin': request.GET.get('checkin') or str(timezone.now().date()),
        'checkout': request.GET.get('checkout', ''),
        'people_count': request.GET.get('people_count', '1'),
    }
    
    if request.method == 'POST':
        # Collect form data
        form_data = {
            'surname': request.POST.get('surname', '').strip(),
            'name': request.POST.get('name', '').strip(),
            'nationality': request.POST.get('nationality', '').strip(),
            'nationality_code': request.POST.get('nationality_code', '').strip(),
            'passport_number': request.POST.get('passport_number', '').strip(),
            'date_of_birth': request.POST.get('date_of_birth', '').strip(),
            'profession': request.POST.get('profession', '').strip(),
            'hometown': request.POST.get('hometown', '').strip(),
            'country': request.POST.get('country', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'phone': request.POST.get('phone', '').strip(),
            'checkin': request.POST.get('checkin', '').strip(),
            'checkout': request.POST.get('checkout', '').strip(),
        }
        
        # Handle accompanying guests
        try:
            people_count = max(1, int(request.POST.get('people_count') or 1))
        except ValueError:
            people_count = 1
        
        accompanying = []
        for i in range(1, people_count):
            name = request.POST.get(f'accompany_name_{i}', '').strip()
            if name:
                accompanying.append({
                    'name': name,
                    'nationality': request.POST.get(f'accompany_nationality_{i}', '').strip(),
                    'passport': request.POST.get(f'accompany_passport_{i}', '').strip(),
                })
        
        form_data['accompanying_guests'] = accompanying
        form_data['signature_method'] = request.POST.get('signature_method', 'physical')
        
        # Store in session for signing step
        request.session['dw_registration_data'] = form_data
        
        # Try to send to MRZ backend for processing
        document_preview = ''
        if USE_MRZ_SERVICE:
            try:
                doc_client = get_document_client()
                result = doc_client.update_document(
                    session_id=document_session_id,
                    guest_data=form_data,
                    accompanying_guests=accompanying
                )
                document_preview = result.get('document_preview_html', '')
            except MRZAPIError as e:
                logger.warning(f"MRZ document API failed, using local: {e}")
                # Fall back to local processing
                result = fill_registration_card(form_data)
                document_preview = result.get('html_preview', '')
        else:
            # Local processing
            result = fill_registration_card(form_data)
            document_preview = result.get('html_preview', '')
        
        request.session['dw_document_preview'] = document_preview
        
        # Redirect to signing page
        return redirect('kiosk:dw_sign_document')
    
    return render(request, 'kiosk/dw_registration_card.html', {'initial': initial_data})


@handle_kiosk_errors
def dw_sign_document(request):
    """
    Document signing page with legal preview - LINEAR FLOW (no loops).
    
    Shows the DW R.C. document preview from MRZ backend for legal review before signing.
    Supports:
    - Digital signature via canvas (SVG) - stored in database
    - Physical signature - submitted to front desk
    
    Flow: dw_sign_document → document_signing → finalize
    Never redirects back to dw_registration_card.
    """
    import uuid
    
    registration_data = request.session.get('dw_registration_data', {})
    document_preview = request.session.get('dw_document_preview', '')
    signature_method = registration_data.get('signature_method', 'digital')
    document_session_id = request.session.get('document_session_id', str(uuid.uuid4()))
    
    # GUARD: No registration data = show error (don't loop back)
    if not registration_data:
        return render_error(
            request,
            "Your registration session has expired. Please start over or contact the front desk.",
            error_code="SESSION_EXPIRED"
        )
    
    # Get reservation if exists
    reservation = None
    guest_id = request.session.get('guest_id')
    if guest_id:
        guest = db.get_guest(int(guest_id))
        if guest:
            res_qs = db.get_reservations_by_guest(guest)
            if res_qs:
                reservation = res_qs[-1]
                request.session['reservation_id'] = reservation['id']
    
    # Get document preview from MRZ backend for legal review (if not already in session)
    if not document_preview and USE_MRZ_SERVICE:
        try:
            doc_client = get_document_client()
            result = doc_client.get_document_preview(
                session_id=document_session_id,
                guest_data=registration_data
            )
            document_preview = result.get('preview_html', '')
            request.session['dw_document_preview'] = document_preview
        except MRZAPIError as e:
            logger.warning(f"MRZ preview API failed: {e}")
            # Generate local preview
            result = fill_registration_card(registration_data)
            document_preview = result.get('html_preview', '')
    
    if request.method == 'POST':
        # Get signature data - support both PNG (legacy) and SVG formats
        signature_data = request.POST.get('signature_data', '')
        signature_svg = request.POST.get('signature_svg', '')
        active_method = request.POST.get('signature_method', signature_method)
        
        # Prefer SVG if available, fall back to PNG
        signature_to_use = signature_svg or signature_data
        
        if active_method == 'digital':
            # Digital signature flow - send to MRZ backend
            if not signature_to_use:
                return render(request, 'kiosk/dw_sign_document.html', {
                    'registration_data': registration_data,
                    'document_preview': document_preview,
                    'signature_method': signature_method,
                    'reservation': reservation,
                    'error': 'Please draw your signature before continuing.',
                })
            
            # Save signature locally as SVG (preferred) or PNG
            try:
                sig_dir = os.path.join(settings.BASE_DIR, 'media', 'signatures')
                os.makedirs(sig_dir, exist_ok=True)
                
                if signature_svg:
                    # Save as SVG
                    sig_filename = f"signature_{guest_id or 'guest'}_{int(time.time())}.svg"
                    sig_path = os.path.join(sig_dir, sig_filename)
                    with open(sig_path, 'w', encoding='utf-8') as f:
                        f.write(signature_svg)
                    registration_data['signature_format'] = 'svg'
                elif signature_data and signature_data.startswith('data:image/png;base64,'):
                    # Save as PNG (legacy)
                    sig_filename = f"signature_{guest_id or 'guest'}_{int(time.time())}.png"
                    sig_path = os.path.join(sig_dir, sig_filename)
                    sig_bytes = base64.b64decode(signature_data.split(',')[1])
                    with open(sig_path, 'wb') as f:
                        f.write(sig_bytes)
                    registration_data['signature_format'] = 'png'
                else:
                    sig_path = None
                    sig_filename = None
                
                if sig_path:
                    registration_data['signature_file'] = sig_filename
                    request.session['dw_signature_path'] = sig_path
                    
            except Exception as e:
                logger.warning(f"Failed to save signature: {e}")
            
            # Send digital signature to MRZ backend for document finalization
            if USE_MRZ_SERVICE and signature_svg:
                try:
                    doc_client = get_document_client()
                    sign_result = doc_client.sign_document_digital(
                        session_id=document_session_id,
                        guest_data=registration_data,
                        signature_svg=signature_svg
                    )
                    # Store document ID for reference
                    request.session['signed_document_id'] = sign_result.get('document_id')
                    registration_data['document_signed'] = True
                    registration_data['signature_stored_in_db'] = True
                except MRZAPIError as e:
                    logger.warning(f"MRZ sign API failed, continuing with local: {e}")
                    registration_data['signature_stored_in_db'] = False
            
            # Update registration data with signature
            registration_data['signature_data'] = signature_to_use
            registration_data['signature_type'] = 'digital'
            request.session['dw_registration_data'] = registration_data
            
        else:
            # Physical signature flow - submit to front desk
            registration_data['signature_type'] = 'physical'
            request.session['dw_registration_data'] = registration_data
            
            if USE_MRZ_SERVICE:
                try:
                    doc_client = get_document_client()
                    submit_result = doc_client.submit_physical_signature(
                        session_id=document_session_id,
                        guest_data=registration_data,
                        reservation_id=reservation['id'] if reservation else None,
                        room_number=request.session.get('room_payload', {}).get('room_number')
                    )
                    request.session['physical_submission_id'] = submit_result.get('submission_id')
                    registration_data['front_desk_notified'] = submit_result.get('front_desk_notified', False)
                except MRZAPIError as e:
                    logger.warning(f"MRZ physical submission API failed: {e}")
                    registration_data['front_desk_notified'] = False
        
        # Regenerate preview with signature (if digital)
        if active_method == 'digital' and signature_to_use:
            result = fill_registration_card(registration_data)
            request.session['dw_document_preview'] = result.get('html_preview', '')
        
        # Save the final document as HTML file for printing
        try:
            doc_dir = os.path.join(settings.BASE_DIR, 'media', 'filled_documents')
            os.makedirs(doc_dir, exist_ok=True)
            doc_timestamp = int(time.time())
            doc_filename = f"registration_{guest_id or 'guest'}_{doc_timestamp}.html"
            doc_path = os.path.join(doc_dir, doc_filename)
            
            # Generate the complete HTML document
            document_preview = request.session.get('dw_document_preview', '')
            html_content = _generate_printable_html(document_preview, registration_data)
            
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            request.session['saved_document_path'] = doc_path
            request.session['saved_document_filename'] = doc_filename
        except Exception as e:
            logger.warning(f"Failed to save document: {e}")
        
        # Create guest if not exists
        if not guest_id:
            first = registration_data.get('name', '')
            last = registration_data.get('surname', '')
            passport = registration_data.get('passport_number', '')
            dob = registration_data.get('date_of_birth', '')
            guest = db.create_guest(first, last, passport, dob)
            request.session['guest_id'] = guest['id']
            guest_id = guest['id']
        
        # Store completed registration
        request.session['registration_complete'] = True
        
        # FORWARD ONLY: document_signing (which will handle finalize)
        if reservation:
            return redirect('kiosk:document_signing')
        return redirect('kiosk:reservation_entry')
    
    return render(request, 'kiosk/dw_sign_document.html', {
        'registration_data': registration_data,
        'document_preview': document_preview,
        'signature_method': signature_method,
        'reservation': reservation,
    })


def _generate_printable_html(document_preview, registration_data):
    """Generate a complete printable HTML document."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DW Registration Card - Print</title>
    <style>
        @page {{
            size: A4;
            margin: 20mm;
        }}
        body {{
            font-family: 'Arial', sans-serif;
            font-size: 12pt;
            line-height: 1.5;
            color: #333;
        }}
        .registration-card {{
            max-width: 100%;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #333;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24pt;
            color: #1a1a1a;
        }}
        .header .subtitle {{
            color: #666;
            font-size: 11pt;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .section h3 {{
            font-size: 14pt;
            border-bottom: 1px solid #ccc;
            padding-bottom: 5px;
            margin-bottom: 10px;
        }}
        .field-row {{
            display: flex;
            gap: 20px;
            margin-bottom: 10px;
        }}
        .field {{
            flex: 1;
        }}
        .field label {{
            font-weight: bold;
            color: #555;
        }}
        .field .value {{
            display: inline;
        }}
        .accompanying-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .accompanying-table th,
        .accompanying-table td {{
            border: 1px solid #ccc;
            padding: 8px;
            text-align: left;
        }}
        .accompanying-table th {{
            background: #f5f5f5;
        }}
        .signature-section {{
            margin-top: 40px;
        }}
        .signature-line {{
            width: 250px;
            height: 60px;
            border-bottom: 2px solid #333;
            margin: 20px 0;
        }}
        .signature-image {{
            max-width: 250px;
            max-height: 80px;
        }}
        .signature-note {{
            font-size: 10pt;
            color: #666;
        }}
        @media print {{
            body {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            .no-print {{ display: none !important; }}
        }}
        .print-controls {{
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            text-align: center;
        }}
        .print-controls button {{
            padding: 12px 24px;
            font-size: 16px;
            background: #0d6efd;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            margin: 0 8px;
        }}
        .print-controls button:hover {{
            background: #0b5ed7;
        }}
        .print-controls button.secondary {{
            background: #6c757d;
        }}
        .print-controls button.secondary:hover {{
            background: #5c636a;
        }}
    </style>
</head>
<body>
    <div class="print-controls no-print">
        <button onclick="window.print()">🖨️ Print Document</button>
        <button class="secondary" onclick="window.close()">Close</button>
    </div>
    {document_preview}
</body>
</html>"""


@csrf_exempt
def dw_generate_pdf(request):
    """
    Generate/serve the DW R.C. for printing.
    
    If a saved document exists (with signature), serve that file.
    Otherwise, generate a new printable document from session data.
    """
    # Check if there's a saved document with signature
    saved_path = request.session.get('saved_document_path')
    if saved_path and os.path.exists(saved_path):
        # Serve the saved document file
        with open(saved_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HttpResponse(html_content, content_type='text/html')
    
    # Otherwise, generate from session data
    registration_data = request.session.get('dw_registration_data', {})
    document_preview = request.session.get('dw_document_preview', '')
    
    if not document_preview:
        # Generate if not in session
        result = fill_registration_card(registration_data)
        document_preview = result.get('html_preview', '')
    
    # Generate printable HTML with controls
    html_content = _generate_printable_html(document_preview, registration_data)
    
    return HttpResponse(html_content, content_type='text/html')


@csrf_exempt  
def save_passport_extraction(request):
    """
    Save extracted passport data and passport image to database.
    Called via AJAX after MRZ extraction completes.
    
    POST /api/save-passport-data/
    
    Request body (JSON):
        {
            "first_name": "John",
            "last_name": "Doe",
            "passport_number": "AB123456",
            "date_of_birth": "1990-01-15",
            "nationality": "USA",
            "image_base64": "...",           # optional: passport image
            "image_path": "/path/to/image",  # optional: image file path
            "guest_id": 1,                   # optional
            "reservation_id": 123            # optional
        }
    
    Response:
        {
            "success": true,
            "passport_image_stored": true,
            "passport_image_id": "passport_1_20260109_120000"
        }
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Save to session
            request.session['extracted_passport_data'] = data
            
            # Store passport image in database if provided
            passport_image_record = None
            guest_id = data.get('guest_id')
            reservation_id = data.get('reservation_id')
            image_path = data.get('image_path')
            image_base64 = data.get('image_base64')
            
            # Save image file if base64 provided
            if image_base64 and not image_path:
                try:
                    import base64 as b64
                    img_dir = os.path.join(settings.BASE_DIR, 'media', 'passport_scans')
                    os.makedirs(img_dir, exist_ok=True)
                    
                    timestamp = int(time.time())
                    img_filename = f"passport_{timestamp}.jpg"
                    image_path = os.path.join(img_dir, img_filename)
                    
                    # Decode and save image
                    img_data = b64.b64decode(image_base64)
                    with open(image_path, 'wb') as f:
                        f.write(img_data)
                    
                    logger.info(f"Saved passport image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to save passport image file: {e}")
                    image_path = None
            
            # Store passport image record in database
            if image_path or image_base64:
                mrz_data = {
                    'first_name': data.get('first_name'),
                    'last_name': data.get('last_name'),
                    'passport_number': data.get('passport_number'),
                    'date_of_birth': data.get('date_of_birth'),
                    'nationality': data.get('nationality'),
                    'sex': data.get('sex'),
                    'expiry_date': data.get('expiry_date'),
                }
                
                passport_image_record = db.store_passport_image(
                    guest_id=guest_id,
                    reservation_id=reservation_id,
                    image_path=image_path,
                    image_data_base64=image_base64 if not image_path else None,
                    mrz_data=mrz_data
                )
                
                logger.info(f"Stored passport image in database: {passport_image_record.get('passport_image_id')}")
            
            response = {'success': True}
            if passport_image_record:
                response['passport_image_stored'] = True
                response['passport_image_id'] = passport_image_record.get('passport_image_id')
                response['database_record_id'] = passport_image_record.get('id')
            
            return JsonResponse(response)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({'error': 'POST only'}, status=400)


# ============================================================================
# MRZ Service API Proxy Endpoints
# ============================================================================

def mrz_service_health(request):
    """
    Check if the MRZ microservice is healthy.
    Returns JSON with status info.
    """
    if not USE_MRZ_SERVICE:
        return JsonResponse({
            'available': False,
            'mode': 'local',
            'message': 'Running in local mode without MRZ service'
        })
    
    try:
        client = get_mrz_client()
        is_healthy = client.health_check()
        return JsonResponse({
            'available': is_healthy,
            'mode': 'service',
            'service_url': os.environ.get('MRZ_SERVICE_URL', 'not configured')
        })
    except Exception as e:
        return JsonResponse({
            'available': False,
            'mode': 'service',
            'error': str(e)
        })


def mrz_video_feed_url(request):
    """
    Get the URL for the MRZ service video feed.
    The frontend can use this to display the camera stream.
    """
    if not USE_MRZ_SERVICE:
        return JsonResponse({
            'available': False,
            'error': 'MRZ service not configured'
        })
    
    try:
        client = get_mrz_client()
        feed_url = client.get_video_feed_url()
        return JsonResponse({
            'available': True,
            'video_feed_url': feed_url
        })
    except Exception as e:
        return JsonResponse({
            'available': False,
            'error': str(e)
        })


@csrf_exempt
def mrz_detect(request):
    """
    Proxy document detection request to MRZ backend service.
    Used for auto-capture functionality with browser camera.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    if not USE_MRZ_SERVICE:
        # Fallback: simple detection simulation
        return JsonResponse({
            'detected': False,
            'confidence': 0,
            'ready_for_capture': False,
            'mode': 'local'
        })
    
    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL
        
        # Forward the request body to the MRZ backend
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/detect",
            json=request.body and json.loads(request.body) or {},
            timeout=5
        )
        return JsonResponse(response.json())
    except Exception as e:
        return JsonResponse({
            'detected': False,
            'error': str(e)
        })


@csrf_exempt
def mrz_extract(request):
    """
    Proxy MRZ extraction request to MRZ backend service.
    Receives base64 image from browser camera and returns extracted data.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    if not USE_MRZ_SERVICE:
        return JsonResponse({
            'success': False,
            'error': 'MRZ service not configured',
            'mode': 'local'
        })
    
    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL
        
        # Forward the request body to the MRZ backend
        body = json.loads(request.body) if request.body else {}
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/extract",
            json=body,
            timeout=30
        )
        result = response.json()
        
        if result.get('success'):
            # Convert to kiosk format
            kiosk_data = convert_mrz_to_kiosk_format(result.get('data', {}))
            return JsonResponse({
                'success': True,
                'data': result.get('data'),  # Return raw data for display
                'kiosk_data': kiosk_data,    # Also return kiosk format
                'timestamp': result.get('timestamp'),
                'filled_document': result.get('filled_document')
            })
        else:
            return JsonResponse(result, status=422)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def passport_scan(request):
    """
    Passport scanning page with browser-based camera and auto-capture.
    Uses WebRTC to capture from browser, sends to MRZ backend for processing.
    """
    mrz_service_url = '/api/mrz'  # Proxy through Django
    return render(request, 'kiosk/passport_scan.html', {
        'mrz_service_url': mrz_service_url
    })


def face_capture(request, reservation_id):
    """
    Face capture page with browser-based camera and auto-capture on face detection.
    """
    from . import emulator as db
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('Reservation not found')
    
    # Get room capacity for max faces
    room = reservation.get('room')
    max_faces = room.get('capacity', 4) if room else 4
    
    return render(request, 'kiosk/face_capture.html', {
        'reservation': reservation,
        'max_faces': max_faces
    })


@csrf_exempt
def save_faces(request, reservation_id):
    """
    Save captured face images for a reservation.
    Receives JSON array of base64 face images from browser camera.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    from . import emulator as db
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('Reservation not found')
    
    try:
        face_data = request.POST.get('face_data', '[]')
        faces = json.loads(face_data)
        
        # In production, save face images to storage and register with face recognition system
        # For now, just store the count
        enrolled_count = len(faces)
        
        # Update reservation or guest with face enrollment status
        # db.update_reservation_faces(reservation_id, enrolled_count)
        
        return redirect('kiosk:finalize', reservation_id=reservation_id)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ============================================================================
# DOCUMENT MANAGEMENT API (Proxy to MRZ Backend)
# ============================================================================

@csrf_exempt
def document_update_api(request):
    """
    API endpoint to update document with edited guest information.
    Proxies to MRZ backend or handles locally.
    
    POST /api/document/update/
    
    Request body (JSON):
        {
            "session_id": "abc123",
            "guest_data": { ... },
            "accompanying_guests": [ ... ]
        }
    
    Response:
        {
            "success": true,
            "document_preview_html": "<html>...",
            "session_id": "abc123"
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get('session_id', str(__import__('uuid').uuid4()))
        guest_data = data.get('guest_data', {})
        accompanying = data.get('accompanying_guests', [])
        
        if not guest_data:
            return JsonResponse({
                'success': False,
                'error': 'guest_data is required'
            }, status=400)
        
        # Store in Django session
        request.session['document_session_id'] = session_id
        request.session['dw_registration_data'] = guest_data
        
        # Try MRZ backend
        if USE_MRZ_SERVICE:
            try:
                doc_client = get_document_client()
                result = doc_client.update_document(
                    session_id=session_id,
                    guest_data=guest_data,
                    accompanying_guests=accompanying
                )
                request.session['dw_document_preview'] = result.get('document_preview_html', '')
                return JsonResponse(result)
            except MRZAPIError as e:
                logger.warning(f"MRZ document API failed, using local: {e}")
        
        # Local fallback
        result = fill_registration_card(guest_data)
        preview_html = result.get('html_preview', '')
        request.session['dw_document_preview'] = preview_html
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'document_preview_html': preview_html,
            'timestamp': result.get('timestamp')
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Document update API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
def document_preview_api(request):
    """
    API endpoint to get document preview for legal review before signing.
    
    POST /api/document/preview/
    
    Request body (JSON):
        {
            "session_id": "abc123",
            "guest_data": { ... }  # optional if session_id provided
        }
    
    Response:
        {
            "success": true,
            "preview_html": "<html>...",
            "fields": { ... }
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get('session_id')
        guest_data = data.get('guest_data')
        
        # Use session data if guest_data not provided
        if not guest_data and session_id:
            guest_data = request.session.get('dw_registration_data', {})
        
        if not guest_data:
            return JsonResponse({
                'success': False,
                'error': 'guest_data or valid session_id is required'
            }, status=400)
        
        # Try MRZ backend
        if USE_MRZ_SERVICE:
            try:
                doc_client = get_document_client()
                result = doc_client.get_document_preview(
                    session_id=session_id,
                    guest_data=guest_data
                )
                return JsonResponse(result)
            except MRZAPIError as e:
                logger.warning(f"MRZ preview API failed, using local: {e}")
        
        # Local fallback
        result = fill_registration_card(guest_data)
        preview_html = result.get('html_preview', '')
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'preview_html': preview_html,
            'fields': guest_data
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Document preview API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
def document_sign_api(request):
    """
    API endpoint to sign document digitally with SVG signature.
    Signature and signed document are stored in kiosk database.
    
    POST /api/document/sign/
    
    Request body (JSON):
        {
            "session_id": "abc123",
            "guest_data": { ... },
            "signature_svg": "<svg>...</svg>",
            "guest_id": 1,           # optional
            "reservation_id": 123    # optional
        }
    
    Response:
        {
            "success": true,
            "document_id": "doc_123",
            "signature_stored": true,
            "stored_in_database": true
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get('session_id')
        guest_data = data.get('guest_data')
        signature_svg = data.get('signature_svg', '')
        guest_id = data.get('guest_id')
        reservation_id = data.get('reservation_id')
        
        if not guest_data:
            guest_data = request.session.get('dw_registration_data', {})
        
        if not signature_svg:
            return JsonResponse({
                'success': False,
                'error': 'signature_svg is required'
            }, status=400)
        
        # Save signature locally as SVG file
        sig_path = None
        try:
            sig_dir = os.path.join(settings.BASE_DIR, 'media', 'signatures')
            os.makedirs(sig_dir, exist_ok=True)
            
            sig_filename = f"signature_{session_id}_{int(time.time())}.svg"
            sig_path = os.path.join(sig_dir, sig_filename)
            
            with open(sig_path, 'w', encoding='utf-8') as f:
                f.write(signature_svg)
            
            logger.info(f"Saved SVG signature file: {sig_path}")
        except Exception as e:
            logger.warning(f"Failed to save signature file: {e}")
        
        # Generate PDF with signature (optional)
        pdf_path = None
        try:
            result = fill_registration_card(guest_data)
            if result.get('pdf_path'):
                pdf_path = result.get('pdf_path')
        except Exception as e:
            logger.warning(f"Failed to generate PDF: {e}")
        
        # Store signed document in kiosk database
        document_record = db.store_signed_document(
            guest_id=guest_id,
            reservation_id=reservation_id,
            guest_data=guest_data,
            signature_svg=signature_svg,
            signature_path=sig_path,
            pdf_path=pdf_path
        )
        
        document_id = document_record.get('document_id')
        
        # Update session
        request.session['signed_document_id'] = document_id
        guest_data['signature_data'] = signature_svg
        guest_data['signature_type'] = 'digital'
        guest_data['signature_format'] = 'svg'
        guest_data['document_signed'] = True
        guest_data['signature_stored_in_db'] = True
        request.session['dw_registration_data'] = guest_data
        
        logger.info(f"Stored signed document in database: {document_id}")
        
        return JsonResponse({
            'success': True,
            'document_id': document_id,
            'signature_path': sig_path,
            'pdf_path': pdf_path,
            'signature_stored': True,
            'stored_in_database': True,
            'database_record_id': document_record.get('id')
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Document sign API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
def document_submit_physical_api(request):
    """
    API endpoint to submit document for physical signature at front desk.
    Notifies front desk and creates pending document record.
    
    POST /api/document/submit-physical/
    
    Request body (JSON):
        {
            "session_id": "abc123",
            "guest_data": { ... },
            "reservation_id": 123,
            "room_number": "101"
        }
    
    Response:
        {
            "success": true,
            "submission_id": "sub_123",
            "status": "pending_signature",
            "front_desk_notified": true
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get('session_id')
        guest_data = data.get('guest_data')
        reservation_id = data.get('reservation_id')
        room_number = data.get('room_number')
        
        if not guest_data:
            guest_data = request.session.get('dw_registration_data', {})
        
        # Try MRZ backend
        if USE_MRZ_SERVICE:
            try:
                doc_client = get_document_client()
                result = doc_client.submit_physical_signature(
                    session_id=session_id,
                    guest_data=guest_data,
                    reservation_id=reservation_id,
                    room_number=room_number
                )
                
                # Update session
                request.session['physical_submission_id'] = result.get('submission_id')
                guest_data['signature_type'] = 'physical'
                guest_data['front_desk_notified'] = result.get('front_desk_notified', False)
                request.session['dw_registration_data'] = guest_data
                
                return JsonResponse(result)
            except MRZAPIError as e:
                logger.warning(f"MRZ physical submission API failed, using local: {e}")
        
        # Local fallback
        submission_id = f"sub_local_{session_id}_{int(time.time())}"
        
        # TODO: In production, notify front desk via MQTT or other mechanism
        
        # Update session
        request.session['physical_submission_id'] = submission_id
        guest_data['signature_type'] = 'physical'
        guest_data['front_desk_notified'] = False  # Local mode doesn't notify
        request.session['dw_registration_data'] = guest_data
        
        return JsonResponse({
            'success': True,
            'submission_id': submission_id,
            'status': 'pending_signature',
            'front_desk_notified': False,
            'message': 'Please proceed to front desk to complete your registration.',
            'storage': 'local'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Document physical submission API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ============================================================================
# GUEST ACCOUNT API (Dashboard Integration)
# ============================================================================

@csrf_exempt
def create_guest_account_api(request):
    """
    Create a guest account in the Dashboard.
    
    POST /api/guest/create/
    
    Request body (JSON):
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@email.com",
            "room_number": "101",
            "checkout_date": "2026-01-10",
            "passport_number": "AB123456",  # optional
            "phone": "+1234567890"          # optional
        }
    
    Response:
        {
            "success": true,
            "username": "guest_101_john",
            "password": "temp_password_123",
            "room_number": "101",
            "checkout_date": "2026-01-10T12:00:00"
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        import requests
        
        dashboard_url = os.environ.get('DASHBOARD_API_URL', 'http://dashboard:8001')
        api_token = os.environ.get('KIOSK_API_TOKEN', '')
        
        if not dashboard_url:
            return JsonResponse({
                'success': False,
                'error': 'Dashboard API not configured'
            }, status=503)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email', 'room_number', 'checkout_date']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)
        
        # Parse checkout date
        checkout_str = data['checkout_date']
        try:
            if 'T' in checkout_str:
                checkout_date = datetime.datetime.fromisoformat(checkout_str.replace('Z', '+00:00'))
            else:
                checkout_date = datetime.datetime.strptime(checkout_str, '%Y-%m-%d')
                # Default checkout time is noon
                checkout_date = checkout_date.replace(hour=12, minute=0)
        except ValueError:
            return JsonResponse({'error': 'Invalid checkout_date format. Use YYYY-MM-DD'}, status=400)
        
        # Create the guest account via Dashboard API
        headers = {'Authorization': f'Token {api_token}'} if api_token else {}
        response = requests.post(
            f'{dashboard_url}/api/guests/create/',
            json={
                'first_name': data['first_name'],
                'last_name': data['last_name'],
                'email': data['email'],
                'room_number': data['room_number'],
                'checkout_date': checkout_date.isoformat(),
                'passport_number': data.get('passport_number'),
                'phone': data.get('phone')
            },
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 201:
            result = response.json()
            return JsonResponse({
                'success': True,
                **result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': response.json().get('error', 'Failed to create account')
            }, status=response.status_code)
        
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Dashboard API error: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }, status=500)


@csrf_exempt
def deactivate_guest_account_api(request):
    """
    Deactivate a guest account on checkout.
    
    POST /api/guest/deactivate/
    
    Request body (JSON):
        {
            "username": "guest_101_john"
        }
    
    Response:
        {
            "success": true,
            "message": "Account deactivated"
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        import requests
        
        dashboard_url = os.environ.get('DASHBOARD_API_URL', 'http://dashboard:8001')
        api_token = os.environ.get('KIOSK_API_TOKEN', '')
        
        if not dashboard_url:
            return JsonResponse({
                'success': False,
                'error': 'Dashboard API not configured'
            }, status=503)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        username = data.get('username')
        if not username:
            return JsonResponse({'error': 'Missing required field: username'}, status=400)
        
        # Deactivate the account via Dashboard API
        headers = {'Authorization': f'Token {api_token}'} if api_token else {}
        response = requests.post(
            f'{dashboard_url}/api/guests/deactivate/',
            json={'username': username},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JsonResponse({
                'success': True,
                'message': 'Account deactivated'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': response.json().get('error', 'Failed to deactivate account')
            }, status=response.status_code)
        
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Dashboard API error: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }, status=500)


# ============================================================================
# DOCUMENT AND PASSPORT IMAGE RETRIEVAL API
# ============================================================================

def list_signed_documents_api(request):
    """
    List signed documents, optionally filtered by guest or reservation.
    
    GET /api/document/list/?guest_id=1&reservation_id=123
    
    Response:
        {
            "success": true,
            "documents": [
                {
                    "document_id": "doc_1_20260109_120000",
                    "guest_id": 1,
                    "reservation_id": 123,
                    "signed_at": "20260109_120000",
                    "status": "signed"
                }
            ]
        }
    """
    try:
        guest_id = request.GET.get('guest_id')
        reservation_id = request.GET.get('reservation_id')
        
        if reservation_id:
            documents = db.get_signed_documents_by_reservation(int(reservation_id))
        elif guest_id:
            documents = db.get_signed_documents_by_guest(int(guest_id))
        else:
            # Return all documents (for admin purposes)
            documents = list(db.signed_documents.values())
        
        # Remove large fields for listing
        doc_list = []
        for doc in documents:
            doc_list.append({
                'id': doc.get('id'),
                'document_id': doc.get('document_id'),
                'guest_id': doc.get('guest_id'),
                'reservation_id': doc.get('reservation_id'),
                'signed_at': doc.get('signed_at'),
                'status': doc.get('status'),
                'signature_type': doc.get('signature_type'),
                'has_pdf': bool(doc.get('pdf_path')),
            })
        
        return JsonResponse({
            'success': True,
            'documents': doc_list,
            'count': len(doc_list)
        })
        
    except Exception as e:
        logger.error(f"List signed documents API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_signed_document_api(request, document_id):
    """
    Get a specific signed document by document_id.
    
    GET /api/document/<document_id>/
    
    Response:
        {
            "success": true,
            "document": {
                "document_id": "doc_1_20260109_120000",
                "guest_id": 1,
                "guest_data": { ... },
                "signature_svg": "<svg>...</svg>",
                "signed_at": "20260109_120000"
            }
        }
    """
    try:
        document = db.get_signed_document_by_document_id(document_id)
        
        if not document:
            return JsonResponse({
                'success': False,
                'error': 'Document not found'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'document': document
        })
        
    except Exception as e:
        logger.error(f"Get signed document API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def list_passport_images_api(request):
    """
    List passport images, optionally filtered by guest or reservation.
    
    GET /api/passport/list/?guest_id=1&reservation_id=123
    
    Response:
        {
            "success": true,
            "passport_images": [
                {
                    "passport_image_id": "passport_1_20260109_120000",
                    "guest_id": 1,
                    "reservation_id": 123,
                    "captured_at": "20260109_120000"
                }
            ]
        }
    """
    try:
        guest_id = request.GET.get('guest_id')
        reservation_id = request.GET.get('reservation_id')
        
        if reservation_id:
            images = db.get_passport_images_by_reservation(int(reservation_id))
        elif guest_id:
            images = db.get_passport_images_by_guest(int(guest_id))
        else:
            # Return all images (for admin purposes)
            images = list(db.passport_images.values())
        
        # Remove large fields for listing
        img_list = []
        for img in images:
            img_list.append({
                'id': img.get('id'),
                'passport_image_id': img.get('passport_image_id'),
                'guest_id': img.get('guest_id'),
                'reservation_id': img.get('reservation_id'),
                'captured_at': img.get('captured_at'),
                'status': img.get('status'),
                'has_mrz_data': bool(img.get('mrz_data')),
            })
        
        return JsonResponse({
            'success': True,
            'passport_images': img_list,
            'count': len(img_list)
        })
        
    except Exception as e:
        logger.error(f"List passport images API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_passport_image_api(request, passport_image_id):
    """
    Get a specific passport image by passport_image_id.
    
    GET /api/passport/<passport_image_id>/
    
    Response:
        {
            "success": true,
            "passport_image": {
                "passport_image_id": "passport_1_20260109_120000",
                "guest_id": 1,
                "image_path": "/path/to/image.jpg",
                "mrz_data": { ... },
                "captured_at": "20260109_120000"
            }
        }
    """
    try:
        # Search by passport_image_id
        passport_image = None
        for img in db.passport_images.values():
            if img.get('passport_image_id') == passport_image_id:
                passport_image = img
                break
        
        if not passport_image:
            return JsonResponse({
                'success': False,
                'error': 'Passport image not found'
            }, status=404)
        
        # Remove base64 data for response (can be large)
        response_data = dict(passport_image)
        response_data.pop('image_data_base64', None)
        
        return JsonResponse({
            'success': True,
            'passport_image': response_data
        })
        
    except Exception as e:
        logger.error(f"Get passport image API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
