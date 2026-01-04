import threading
import time
import datetime
import os
import tempfile
import json
import base64
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
from .mrz_api_client import get_mrz_client, MRZAPIError, convert_mrz_to_kiosk_format

# Check if we should use the MRZ microservice
USE_MRZ_SERVICE = os.environ.get('MRZ_SERVICE_URL') is not None


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

        guest = db.get_or_create_guest(first_name, last_name, passport, dob)
        request.session['guest_id'] = guest['id']
        request.session['access_method'] = ','.join(access_methods)
        request.session['pending_access_methods'] = access_methods

        # Try find reservation by reservation_number or guest
        res_number = data.get('reservation_number', [''])[0]
        reservation = None
        
        if res_number:
            reservation = db.get_reservation_by_number(res_number)

        if not reservation:
            # Try to find by guest
            res_qs = db.get_reservations_by_guest(guest)
            if res_qs:
                reservation = res_qs[0]

        if reservation:
            # Reservation found - store it and go to document signing
            request.session['reservation_id'] = reservation['id']
            return redirect('kiosk:document_signing')

        # No reservation found - go to walk-in page
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
    # simple check-in/check-out choice page
    return render(request, 'kiosk/checkin.html')


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
                first = reg.get('name') or ''
                last = reg.get('surname') or ''
                passport = reg.get('passport_number') or ''
                dob = reg.get('date_of_birth') or None
                guest = db.create_guest(first, last, passport, dob)
                request.session['guest_id'] = guest['id']
                request.session['registration_document'] = {'data': reg, 'accompany': accompany, 'signature_method': signature_method}
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


def document_signing(request):
    """
    Document signing page - LINEAR FLOW (no loops).
    
    Flow:
    1. Guest signs document digitally (canvas signature)
    2. Assign room and apply access methods
    3. Go to face enrollment OR finalize (never back)
    
    If no reservation/guest: redirect to start (reset flow)
    """
    guest_id = request.session.get('guest_id')
    reservation_id = request.session.get('reservation_id')
    
    # GUARD: No guest = start over (don't loop)
    if not guest_id:
        return redirect('kiosk:start')
    
    # Try to get reservation from session or by guest lookup
    reservation = None
    if reservation_id:
        reservation = db.get_reservation(int(reservation_id))
    else:
        guest = db.get_guest(int(guest_id))
        if guest:
            res_qs = db.get_reservations_by_guest(guest)
            if res_qs:
                reservation = res_qs[-1]
                request.session['reservation_id'] = reservation['id']

    # GUARD: No reservation = this shouldn't happen in normal flow
    # Instead of looping back, redirect to start
    if not reservation:
        return redirect('kiosk:start')

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
        
        # FORWARD ONLY: face enrollment OR finalize
        if 'face' in access_methods:
            return redirect('kiosk:enroll_face', reservation_id=reservation['id'])
        return redirect('kiosk:finalize', reservation_id=reservation['id'])

    return render(request, 'kiosk/document_sign.html', {'reservation': reservation})


def choose_access(request, reservation_id):
    """
    Access method selection - LINEAR FLOW (no loops).
    
    This is a FALLBACK page only used if access methods weren't selected during passport scan.
    Flow: choose_access → enroll_face OR finalize
    Never redirects back to earlier steps.
    """
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        # GUARD: Invalid reservation = start over
        return redirect('kiosk:start')
    
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
                import logging
                logging.getLogger(__name__).error(f"RFID token publish error: {e}")

        # FORWARD ONLY: face enrollment OR finalize
        if 'face' in methods:
            return redirect('kiosk:enroll_face', reservation_id=reservation['id'])
        return redirect('kiosk:finalize', reservation_id=reservation['id'])

    return render(request, 'kiosk/choose_access.html', {
        'reservation': reservation,
        'preselected_keycard': 'keycard' in preselected,
        'preselected_face': 'face' in preselected
    })


def walkin(request):
    """
    Walk-in guest page - LINEAR FLOW (no loops).
    
    Shown when no reservation is found after passport verification.
    Guest can choose to create a new reservation.
    
    Flow: walkin → reservation_entry → document_signing → finalize
    If no guest: redirect to start (don't loop)
    """
    guest_id = request.session.get('guest_id')
    
    # GUARD: No guest = start over (don't loop)
    if not guest_id:
        return redirect('kiosk:start')
    
    guest = db.get_guest(int(guest_id))
    if not guest:
        return redirect('kiosk:start')
    
    return render(request, 'kiosk/walkin.html', {'guest': guest})


def reservation_entry(request):
    """
    Create reservation for walk-in guest - LINEAR FLOW (no loops).
    
    Flow: reservation_entry → document_signing → finalize
    Never redirects back to walkin or verify_info.
    If no guest: redirect to start (don't loop)
    """
    guest_id = request.session.get('guest_id')
    
    # GUARD: No guest = start over (don't loop)
    if not guest_id:
        return redirect('kiosk:start')
    
    guest = db.get_guest(int(guest_id))
    if not guest:
        return redirect('kiosk:start')
    
    if request.method == 'POST':
        resnum = request.POST.get('reservation_number', '').strip()
        room_count = int(request.POST.get('room_count') or 1)
        people_count = int(request.POST.get('people_count') or request.POST.get('room_count') or 1)
        checkin = parse_date(request.POST.get('checkin') or '') or timezone.now().date()
        checkout = parse_date(request.POST.get('checkout') or '') or (timezone.now().date() + datetime.timedelta(days=1))
        
        # Auto-generate reservation number if not provided
        if not resnum:
            import secrets
            resnum = f"RES-{timezone.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
        
        res = db.create_reservation(resnum, guest, checkin, checkout, room_count=room_count, people_count=people_count)
        
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


def enroll_face(request, reservation_id):
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('reservation')
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


def finalize(request, reservation_id):
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('reservation')
    access_method = request.session.get('access_method', 'keycard')
    room_payload = request.session.get('room_payload') or {}
    room_number = room_payload.get('room_number') or reservation.get('room_number') or str(100 + (reservation_id % 50))
    rfid_token = room_payload.get('rfid_token')
    
    return render(request, 'kiosk/finalize.html', {
        'reservation': reservation, 
        'access_method': access_method, 
        'room_number': room_number,
        'rfid_token': rfid_token
    })


def submit_keycards(request, reservation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('reservation')

    # mark keycards returned and finalize payment (demo: always finalize)
    db.submit_keycards(reservation)
    db.finalize_payment(reservation, amount=reservation.get('amount_due', 0) or 0)

    return redirect('kiosk:finalize', reservation_id=reservation['id'])


def report_stolen_card(request, reservation_id):
    """
    Report a stolen or lost keycard and issue a new one.
    Revokes the old RFID token and generates a new one.
    """
    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404('reservation')
    
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
    
    GET: Show form pre-filled with data from session or query params
    POST: Generate document preview and proceed to signing
    """
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
        
        # Generate document preview
        result = fill_registration_card(form_data)
        request.session['dw_document_preview'] = result.get('html_preview', '')
        
        # Redirect to signing page
        return redirect('kiosk:dw_sign_document')
    
    return render(request, 'kiosk/dw_registration_card.html', {'initial': initial_data})


def dw_sign_document(request):
    """
    Document signing page - LINEAR FLOW (no loops).
    
    Shows the DW R.C. document preview and allows:
    - Digital signature via canvas
    - Print for physical signature
    
    Flow: dw_sign_document → document_signing → finalize
    Never redirects back to dw_registration_card.
    """
    registration_data = request.session.get('dw_registration_data', {})
    document_preview = request.session.get('dw_document_preview', '')
    signature_method = registration_data.get('signature_method', 'physical')
    
    # GUARD: No registration data = start over (don't loop back)
    if not registration_data:
        return redirect('kiosk:start')
    
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
    
    if request.method == 'POST':
        # Handle signature submission
        signature_data = request.POST.get('signature_data', '')
        # Save digital signature as file if provided
        if signature_data and signature_data.startswith('data:image/png;base64,'):
            try:
                sig_dir = os.path.join(settings.BASE_DIR, 'media', 'signatures')
                os.makedirs(sig_dir, exist_ok=True)
                sig_filename = f"dw_signature_{guest_id or 'unknown'}_{int(time.time())}.png"
                sig_path = os.path.join(sig_dir, sig_filename)
                sig_bytes = base64.b64decode(signature_data.split(',')[1])
                with open(sig_path, 'wb') as f:
                    f.write(sig_bytes)
                registration_data['signature_file'] = sig_filename
                request.session['dw_signature_path'] = sig_path
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to save DW signature: {e}")
        # Update document with signature (base64 or file ref)
        if signature_data:
            registration_data['signature_data'] = signature_data
            request.session['dw_registration_data'] = registration_data
            # Regenerate preview with signature
            result = fill_registration_card(registration_data)
            request.session['dw_document_preview'] = result.get('html_preview', '')
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


@csrf_exempt
def dw_generate_pdf(request):
    """
    Generate a PDF version of the DW R.C. for printing.
    
    Note: This is a simplified HTML-to-print version. 
    For full PDF generation, integrate with weasyprint or similar.
    """
    registration_data = request.session.get('dw_registration_data', {})
    document_preview = request.session.get('dw_document_preview', '')
    
    if not document_preview:
        # Generate if not in session
        result = fill_registration_card(registration_data)
        document_preview = result.get('html_preview', '')
    
    # Return printable HTML page
    html_content = f"""
    <!DOCTYPE html>
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
                body {{ print-color-adjust: exact; }}
            }}
        </style>
    </head>
    <body onload="window.print()">
        {document_preview}
    </body>
    </html>
    """
    
    return HttpResponse(html_content, content_type='text/html')


@csrf_exempt  
def save_passport_extraction(request):
    """
    Save extracted passport data to session for use in registration card.
    Called via AJAX after MRZ extraction completes.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request.session['extracted_passport_data'] = data
            return JsonResponse({'success': True})
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
# GUEST ACCOUNT API (Authentik Integration)
# ============================================================================

@csrf_exempt
def create_guest_account_api(request):
    """
    Create a guest account in Authentik.
    
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
        from .authentik_client import get_authentik_client, AuthentikAPIError
        
        client = get_authentik_client()
        
        if not client.is_configured():
            return JsonResponse({
                'success': False,
                'error': 'Authentik integration not configured'
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
        
        # Create the guest account
        result = client.create_guest_account(
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            room_number=data['room_number'],
            checkout_date=checkout_date,
            passport_number=data.get('passport_number'),
            phone=data.get('phone')
        )
        
        return JsonResponse({
            'success': True,
            **result
        })
        
    except AuthentikAPIError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
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
        from .authentik_client import get_authentik_client, AuthentikAPIError
        
        client = get_authentik_client()
        
        if not client.is_configured():
            return JsonResponse({
                'success': False,
                'error': 'Authentik integration not configured'
            }, status=503)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        username = data.get('username')
        if not username:
            return JsonResponse({'error': 'Missing required field: username'}, status=400)
        
        # Deactivate the account
        success = client.deactivate_guest(username)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Account deactivated'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to deactivate account'
            }, status=500)
        
    except AuthentikAPIError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }, status=500)
