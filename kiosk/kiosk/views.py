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
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.urls import reverse
from . import emulator as db
from django.utils.dateparse import parse_date

# Cookie persistence for session data
from .cookie_persistence import (
    restore_session_from_cookies,
    sync_session_to_cookies,
    with_cookie_persistence,
    clear_all_cookies,
)

# MRZ and document modules
from .mrz_parser import get_mrz_parser, extract_passport_data, MRZExtractionError

# MRZ API client for microservice communication
from .mrz_api_client import (
    get_mrz_client,
    MRZAPIError,
    convert_mrz_to_kiosk_format,
    get_document_client,
    MRZDocumentClient,
)

# Check if we should use the MRZ microservice
USE_MRZ_SERVICE = os.environ.get("MRZ_SERVICE_URL") is not None

# Logger for kiosk views
logger = logging.getLogger(__name__)

# Front desk phone number (configurable via environment)
FRONT_DESK_PHONE = os.environ.get("FRONT_DESK_PHONE", "0")


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


def redirect_see_other(to, *args, **kwargs):
    """
    Redirect with HTTP 303 (See Other) status.
    This ensures the browser uses GET for the redirect target,
    even when the original request was POST.
    """
    if args or kwargs:
        url = reverse(to, args=args, kwargs=kwargs)
    else:
        try:
            url = reverse(to)
        except Exception:
            url = to
    response = HttpResponseRedirect(url)
    response.status_code = 303
    return response


def render_error(request, message, error_code=None):
    """
    Render the error page with Call Front Desk option.
    Use this instead of redirecting back to previous steps.
    """
    return render(
        request,
        "kiosk/error.html",
        {
            "error_message": message,
            "error_code": error_code,
            "front_desk_phone": FRONT_DESK_PHONE,
        },
    )


def handle_kiosk_errors(view_func):
    """
    Decorator to catch database and session errors in kiosk views.
    Displays error page with Call Front Desk option instead of crashing.
    Also handles cookie persistence for session data.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            # Restore session from cookies before processing
            restore_session_from_cookies(request)
            
            response = view_func(request, *args, **kwargs)
            
            # Sync session to cookies after processing
            if hasattr(response, 'set_cookie'):
                sync_session_to_cookies(request, response)
            
            return response
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
                error_code="UNEXPECTED_ERROR",
            )

    return wrapper


def error_page(request):
    """
    Generic error page with Call Front Desk option.
    Can be accessed directly or via redirect with query params.
    """
    error_message = request.GET.get("message", "Something went wrong while processing your request.")
    error_code = request.GET.get("code")

    return render(
        request,
        "kiosk/error.html",
        {
            "error_message": error_message,
            "error_code": error_code,
            "front_desk_phone": FRONT_DESK_PHONE,
        },
    )


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

        dashboard_url = os.environ.get("DASHBOARD_API_URL", "http://dashboard:8001")
        api_token = os.environ.get("KIOSK_API_TOKEN", "")

        if not dashboard_url:
            logger.warning("Dashboard API URL not configured")
            return None

        # Prepare request data
        checkout_date = reservation_data.get("checkout", "")
        if checkout_date and isinstance(checkout_date, str):
            # Ensure ISO format
            if "T" not in checkout_date:
                checkout_date = f"{checkout_date}T12:00:00"

        payload = {
            "first_name": guest_data.get("first_name", ""),
            "last_name": guest_data.get("last_name", ""),
            "email": guest_data.get("email", ""),
            "room_number": str(room_number),
            "checkout_date": checkout_date,
            "passport_number": guest_data.get("passport_number", ""),
            "phone": guest_data.get("phone", ""),
        }

        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"

        response = requests.post(f"{dashboard_url}/api/guests/create/", json=payload, headers=headers, timeout=10)

        if response.status_code == 201:
            result = response.json()
            logger.info(f"Dashboard guest account created: {result.get('username')}")
            return {
                "username": result.get("username"),
                "password": result.get("password"),
                "room_number": result.get("room_number"),
                "expires_at": result.get("expires_at"),
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

        dashboard_url = os.environ.get("DASHBOARD_API_URL", "http://dashboard:8001")
        api_token = os.environ.get("KIOSK_API_TOKEN", "")

        if not dashboard_url:
            logger.warning("Dashboard API URL not configured")
            return False

        payload = {}
        if username:
            payload["username"] = username
        elif room_number:
            payload["room_number"] = str(room_number)
        else:
            return False

        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"

        response = requests.post(f"{dashboard_url}/api/guests/deactivate/", json=payload, headers=headers, timeout=10)

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
    return render(request, "kiosk/start.html")


@csrf_exempt
def upload_scan(request):
    if request.method == "POST":
        # create extraction task
        task = db.create_task(status="processing")
        tid = task["id"]

        # Get uploaded file
        uploaded_file = request.FILES.get("scan")

        # Save uploaded file temporarily for MRZ processing
        temp_path = None
        image_bytes = None
        if uploaded_file:
            # Create temp directory if needed
            temp_dir = os.path.join(settings.BASE_DIR, "media", "temp_scans")
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, f"scan_{tid}_{uploaded_file.name}")

            # Read image bytes for API call
            image_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset for saving

            with open(temp_path, "wb+") as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)

        def process_task_with_api(tid, image_bytes, filename):
            """Process using MRZ microservice API"""
            try:
                client = get_mrz_client()
                result = client.extract_from_image(image_bytes, filename)
                data = convert_mrz_to_kiosk_format(result.get("data", {}))
                db.set_task_data(tid, data)
            except MRZAPIError as e:
                # API error - fall back to local parser
                process_task_local(tid, temp_path)
            except Exception as e:
                db.set_task_data(tid, {"error": str(e)})

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
                    "first_name": "",
                    "last_name": "",
                    "passport_number": "",
                    "date_of_birth": "",
                    "error": str(e),
                }
                db.set_task_data(tid, data)
            except Exception as e:
                db.set_task_data(tid, {"error": str(e)})

        # Choose processing method based on configuration
        if USE_MRZ_SERVICE and image_bytes:
            filename = uploaded_file.name if uploaded_file else "passport.jpg"
            threading.Thread(target=process_task_with_api, args=(tid, image_bytes, filename), daemon=True).start()
        else:
            threading.Thread(target=process_task_local, args=(tid, temp_path), daemon=True).start()

        return JsonResponse({"task_id": tid})
    return JsonResponse({"error": "POST only"}, status=400)


def extract_status(request, task_id):
    task = db.get_task(task_id)
    if not task:
        raise Http404("task not found")
    return JsonResponse({"status": task.get("status"), "data": task.get("data")})


@csrf_exempt
@handle_kiosk_errors
def verify_info(request):
    """
    Verify guest info and redirect to next step.
    
    Flow: dw_registration_card → verify_info → reservation_entry
    
    Gets data from session (dw_registration_data) which was set by dw_registration_card.
    Creates/finds guest in database and looks up existing reservation.
    """
    if request.method == "POST" or request.session.get("dw_registration_data"):
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                  request.headers.get('Accept', '').startswith('application/json')
        
        # Get data from session (set by dw_registration_card) or POST
        reg_data = request.session.get("dw_registration_data", {})
        
        if reg_data:
            # Data from dw_registration_card (via session)
            first_name = reg_data.get("name", "") or reg_data.get("given_name", "")
            last_name = reg_data.get("surname", "")
            passport = reg_data.get("passport_number", "")
            dob = parse_date(reg_data.get("date_of_birth", ""))
            nationality = reg_data.get("nationality", "")
            nationality_code = reg_data.get("nationality_code", "") or nationality
            issuer_code = reg_data.get("issuer_code", "")
            sex = reg_data.get("sex", "")
            expiry_date = reg_data.get("expiry_date", "")
            document_session_id = request.session.get("document_session_id", "")
            
            logger.info("VERIFY_INFO: Using data from dw_registration_data session")
        else:
            # Legacy: Data from direct POST (passport_scan)
            data = dict(request.POST)
            
            # DEBUG: Log all POST data received
            logger.info("=" * 60)
            logger.info("VERIFY_INFO: Received POST data (legacy):")
            for key, value in data.items():
                logger.info(f"  {key}: {value}")
            logger.info("=" * 60)
            
            first_name = data.get("first_name", [""])[0]
            last_name = data.get("last_name", [""])[0]
            passport = data.get("passport_number", [""])[0]
            dob = parse_date(data.get("date_of_birth", [""])[0])
            nationality = data.get("nationality", [""])[0]
            nationality_code = data.get("nationality_code", [""])[0] or nationality
            issuer_code = data.get("issuer_code", [""])[0]
            sex = data.get("sex", [""])[0]
            expiry_date = data.get("expiry_date", [""])[0]
            document_session_id = data.get("document_session_id", [""])[0]
        
        # DEBUG: Log extracted fields
        logger.info("VERIFY_INFO: Extracted fields:")
        logger.info(f"  first_name: '{first_name}'")
        logger.info(f"  last_name: '{last_name}'")
        logger.info(f"  nationality_code: '{nationality_code}'")
        logger.info(f"  issuer_code: '{issuer_code}'")
        
        # Store document_session_id for later use
        if document_session_id:
            request.session["document_session_id"] = document_session_id

        # NOTE: Access method selection is handled AFTER signing in select_access_method view
        # We don't process access methods here anymore to avoid duplicate selection

        # Validate required fields
        if not first_name or not last_name:
            if is_ajax:
                return JsonResponse({
                    "success": False,
                    "error": "We couldn't read your passport information. Please ask the front desk for assistance.",
                    "error_code": "PASSPORT_READ_ERROR",
                }, status=400)
            return render_error(
                request,
                "We couldn't read your passport information. Please ask the front desk for assistance.",
                error_code="PASSPORT_READ_ERROR",
            )

        try:
            guest = db.get_or_create_guest(first_name, last_name, passport, dob)
            request.session["guest_id"] = guest["id"]
            logger.info(f"Guest created/found in database: {guest['id']}")
        except Exception as e:
            # FIX 7: Database errors should show error page, not continue silently
            logger.error(f"Database error creating guest: {e}")
            if is_ajax:
                return JsonResponse({
                    "success": False,
                    "error": "We're experiencing database issues. Please contact the front desk.",
                    "error_code": "DATABASE_ERROR",
                }, status=500)
            return render_error(
                request,
                "We're experiencing database issues. Please contact the front desk for assistance.",
                error_code="DATABASE_ERROR",
            )

        # Try find reservation by reservation_number or guest
        # Get reservation number from session data or POST data
        if reg_data:
            res_number = reg_data.get("reservation_number", "")
        else:
            res_number = data.get("reservation_number", [""])[0] if 'data' in dir() else ""
        reservation = None

        if guest:  # Only look up reservation if guest was created
            try:
                if res_number:
                    reservation = db.get_reservation_by_number(res_number)
                    logger.info(f"Reservation found by number: {res_number}")

                if not reservation:
                    # Try to find by guest
                    res_qs = db.get_reservations_by_guest(guest)
                    if res_qs:
                        reservation = res_qs[0]
                        logger.info(f"Reservation found for guest: {guest['id']}")
            except Exception as e:
                logger.warning(f"Database error finding reservation: {e}. Will continue to document filling.")
                reservation = None  # Mark as failed but continue

        # Store reservation if found
        if reservation and guest:
            request.session["reservation_id"] = reservation["id"]

        # Get the flow type from session
        flow_type = request.session.get("flow_type", "checkin")

        # FIX 2 & 6: Handle checkout flow properly
        if flow_type == "checkout":
            if reservation and guest:
                # Valid checkout: has reservation - still go through document signing for audit trail
                # Mark as checkout mode so document signing knows to skip certain steps
                request.session["checkout_mode"] = True
                request.session["checkout_reservation_id"] = reservation["id"]
                logger.info(f"Checkout flow: proceeding to document signing for reservation {reservation['id']}")
            else:
                # FIX 6: Walk-in trying to checkout without reservation - show clear error
                logger.warning(f"Walk-in checkout attempt: guest={guest is not None}, reservation={reservation is not None}")
                if is_ajax:
                    return JsonResponse({
                        "success": False,
                        "error": "Only guests with a reservation can check out. Please contact the front desk.",
                        "error_code": "CHECKOUT_NO_RESERVATION",
                    }, status=400)
                return render_error(
                    request,
                    "Only guests with a reservation can check out. If you need to check out, please contact the front desk for assistance.",
                    error_code="CHECKOUT_NO_RESERVATION",
                )

        # For checkin with pre-booked reservation, show reservation details first
        # For checkin without reservation (walk-in), go to reservation_entry
        # For checkout, always go to document signing (already handled above)
        if flow_type == "checkin":
            if reservation and guest:
                # Pre-booked guest - show reservation confirmation page
                logger.info(f"Checkin with pre-booked reservation: redirecting to reservation details")
                redirect_url = reverse("kiosk:reservation_entry")
                if is_ajax:
                    return JsonResponse({"success": True, "redirect": redirect_url})
                return redirect(redirect_url)
            else:
                # Walk-in guest - go to reservation entry to create new reservation
                logger.info(f"Checkin without reservation: redirecting to reservation entry for walk-in")
                redirect_url = reverse("kiosk:reservation_entry")
                if is_ajax:
                    return JsonResponse({"success": True, "redirect": redirect_url})
                return redirect(redirect_url)
        
        # Checkout already handled above
        # Fallback to document filling (shouldn't reach here in normal flow)
        logger.info(f"Redirecting to document filling for PDF generation (flow_type={flow_type})")
        redirect_url = reverse("kiosk:dw_registration_card")
        if is_ajax:
            return JsonResponse({"success": True, "redirect": redirect_url})
        return redirect(redirect_url)

    # GET
    return JsonResponse({"error": "POST only"}, status=400)


# reservation_api removed — demo no longer exposes API endpoint


def advertisement(request):
    return render(request, "kiosk/advertisement.html", {"no_translate": True})


def choose_language(request):
    if request.method == "POST":
        lang = request.POST.get("language", "en")
        request.session["language"] = lang
        resp = redirect("kiosk:checkin")
        # also set a cookie so client-side JS can read language immediately
        resp.set_cookie("kiosk_language", lang, max_age=30 * 24 * 3600)
        return resp
    return render(request, "kiosk/language.html", {"no_translate": True})


def checkin(request):
    """
    Check-in/Check-out choice page.
    Sets the flow_type in session to track whether guest is checking in or out.
    """
    if request.method == "POST":
        flow_type = request.POST.get("flow_type", "checkin")
        request.session["flow_type"] = flow_type
        # Clear any stale session data from previous flow
        keys_to_clear = [
            "guest_id", "reservation_id", "access_method", "room_payload", 
            "pending_access_methods", "dw_registration_data", "registration_data",
            "document_session_id", "mrz_pdf_filename", "registration_complete",
            "dw_signature_path", "signed_document_id"
        ]
        for key in keys_to_clear:
            request.session.pop(key, None)

        # For checkout, we'll verify they have a reservation after passport scan
        # The verify_info view will handle the "walk-in trying to checkout" case
        response = redirect("kiosk:start")
        # Also clear corresponding cookies
        from .cookie_persistence import clear_cookie
        for key in keys_to_clear:
            clear_cookie(response, key)
        return response
    lang = request.session.get("language", "en")
    return render(request, "kiosk/checkin.html", {"kiosk_language": lang, "no_translate": False})


def documentation(request):
    # Read passport fields from query params for demo printing
    data = {
        "first_name": request.GET.get("first_name", ""),
        "last_name": request.GET.get("last_name", ""),
        "passport_number": request.GET.get("passport_number", ""),
        "date_of_birth": request.GET.get("date_of_birth", ""),
    }
    # try to find a reservation for the current session guest (if any)
    reservation = None
    guest_id = request.session.get("guest_id")
    if guest_id:
        res_qs = db.get_reservations_by_guest(int(guest_id))
        if res_qs:
            reservation = res_qs[-1]

    # If POST, handle either passport correction or registration submission/preview/confirm
    if request.method == "POST":
        # Registration flow detection: presence of 'surname' or people_count indicates registration card
        if request.POST.get("surname") or request.POST.get("people_count"):
            # collect registration fields
            reg = {
                "surname": request.POST.get("surname", "").strip(),
                "name": request.POST.get("name", "").strip(),
                "nationality": request.POST.get("nationality", "").strip(),
                "passport_number": request.POST.get("passport_number", "").strip(),
                "date_of_birth": request.POST.get("date_of_birth", "").strip(),
                "profession": request.POST.get("profession", "").strip(),
                "hometown": request.POST.get("hometown", "").strip(),
                "country": request.POST.get("country", "").strip(),
                "email": request.POST.get("email", "").strip(),
                "phone": request.POST.get("phone", "").strip(),
                "checkin": request.POST.get("checkin", "").strip(),
                "checkout": request.POST.get("checkout", "").strip(),
            }

            try:
                people_count = max(1, int(request.POST.get("people_count") or 1))
            except Exception:
                people_count = 1
            accompany_count = max(0, people_count - 1)

            accompany = []
            for i in range(1, accompany_count + 1):
                nm = request.POST.get(f"accompany_name_{i}", "").strip()
                if nm:
                    accompany.append(
                        {
                            "name": nm,
                            "nationality": request.POST.get(f"accompany_nationality_{i}", "").strip(),
                            "passport": request.POST.get(f"accompany_passport_{i}", "").strip(),
                        }
                    )
            signature_method = request.POST.get("signature_method", "physical")

            # Confirm registration: persist guest and continue to signing
            if request.POST.get("action") == "confirm_registration":
                # Parse name (may be "FIRST LAST" or just first name)
                full_name = reg.get("name", "").strip()
                surname = reg.get("surname", "").strip()
                if " " in full_name and not surname:
                    parts = full_name.split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                else:
                    first_name = full_name
                    last_name = surname

                # Parse date of birth
                dob_str = reg.get("date_of_birth", "")
                dob = parse_date(dob_str) if dob_str else None

                # Persist guest to database
                guest = db.get_or_create_guest(
                    first_name=first_name,
                    last_name=last_name,
                    passport_number=reg.get("passport_number", ""),
                    date_of_birth=dob,
                )
                request.session["guest_id"] = guest["id"]

                # Store registration data in session for document filling
                request.session["registration_data"] = {
                    "guest": reg,
                    "accompany": accompany,
                    "accompany_count": accompany_count,
                    "people_count": people_count,
                    "signature_method": signature_method,
                }

                return redirect("kiosk:pdf_sign_document")

            # Otherwise render registration preview
            return render(
                request,
                "kiosk/registration_preview.html",
                {
                    "data": reg,
                    "accompany": accompany,
                    "accompany_count": accompany_count,
                    "signature_method": signature_method,
                },
            )

        # Passport correction path (existing behavior)
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        passport_number = request.POST.get("passport_number", "").strip()
        dob = parse_date(request.POST.get("date_of_birth", "") or "")

        if first_name and last_name:
            guest = db.get_or_create_guest(first_name, last_name, passport_number or "", dob)
            request.session["guest_id"] = guest["id"]
            return redirect("kiosk:pdf_sign_document")

    return render(request, "kiosk/documentation.html", {"data": data, "reservation": reservation})


def registration_form(request):
    """Show a registration card form (based on paper.txt) for guest input."""
    # Prefill from query or session if available
    initial = {
        "surname": request.GET.get("surname", ""),
        "name": request.GET.get("name", ""),
        "nationality": request.GET.get("nationality", ""),
        "passport_number": request.GET.get("passport_number", ""),
        "date_of_birth": request.GET.get("date_of_birth", ""),
        "profession": request.GET.get("profession", ""),
        "hometown": request.GET.get("hometown", ""),
        "country": request.GET.get("country", ""),
        "email": request.GET.get("email", ""),
        "phone": request.GET.get("phone", ""),
        "checkin": request.GET.get("checkin", ""),
        "checkout": request.GET.get("checkout", ""),
        "people_count": request.GET.get("people_count", "1"),
    }
    return render(request, "kiosk/registration_form.html", {"initial": initial})


def registration_preview(request):
    """Render a well-formatted registration card preview with signature options.

    POST: expects form fields from `registration_form`. If `action=confirm` then
    create guest in emulator and set session, then redirect to reservation entry.
    """
    if request.method != "POST":
        return redirect("kiosk:registration_form")

    # collect common fields
    data = {
        "surname": request.POST.get("surname", "").strip(),
        "name": request.POST.get("name", "").strip(),
        "nationality": request.POST.get("nationality", "").strip(),
        "passport_number": request.POST.get("passport_number", "").strip(),
        "date_of_birth": request.POST.get("date_of_birth", "").strip(),
        "profession": request.POST.get("profession", "").strip(),
        "hometown": request.POST.get("hometown", "").strip(),
        "country": request.POST.get("country", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
        "checkin": request.POST.get("checkin", "").strip(),
        "checkout": request.POST.get("checkout", "").strip(),
    }

    # people_count controls how many accompany lines to render (excluding main guest)
    try:
        people_count = max(1, int(request.POST.get("people_count") or 1))
    except Exception:
        people_count = 1
    accompany_count = max(0, people_count - 1)

    accompany = []
    # Expect accompany entries like accompany_name_1, accompany_nationality_1, accompany_passport_1
    for i in range(1, accompany_count + 1):
        name_k = f"accompany_name_{i}"
        nat_k = f"accompany_nationality_{i}"
        pass_k = f"accompany_passport_{i}"
        nm = request.POST.get(name_k, "").strip()
        if nm:
            accompany.append(
                {
                    "name": nm,
                    "nationality": request.POST.get(nat_k, "").strip(),
                    "passport": request.POST.get(pass_k, "").strip(),
                }
            )

    signature_method = request.POST.get("signature_method", "physical")

    # If this is a confirm submission, persist guest and continue
    if request.POST.get("action") == "confirm":
        # create guest in emulator (use surname/name order)
        first = data.get("name") or ""
        last = data.get("surname") or ""
        passport = data.get("passport_number") or ""
        dob = data.get("date_of_birth") or None
        guest = db.create_guest(first, last, passport, dob)
        request.session["guest_id"] = guest["id"]
        # store the raw registration doc for later reference
        request.session["registration_document"] = {
            "data": data,
            "accompany": accompany,
            "signature_method": signature_method,
        }
        return redirect("kiosk:reservation_entry")

    # render preview (not persisted yet)
    return render(
        request,
        "kiosk/registration_preview.html",
        {
            "data": data,
            "accompany": accompany,
            "accompany_count": accompany_count,
            "signature_method": signature_method,
        },
    )


def redirect_to_pdf_sign(request):
    """
    Redirect helper for all legacy document routes.
    All old document/registration routes now redirect to the unified PDF signing page.
    """
    return redirect("kiosk:pdf_sign_document")


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
            error_code="DATABASE_ERROR",
        )

    if not reservation:
        # GUARD: Invalid reservation = show error
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND",
        )

    # Pre-selected methods from session
    preselected = request.session.get("pending_access_methods", [])

    if request.method == "POST":
        # Allow multiple access methods (checkboxes). Default to keycard if none selected.
        methods = []
        if request.POST.get("access_keycard"):
            methods.append("keycard")
        if request.POST.get("access_face"):
            methods.append("face")

        # Default to keycard if nothing selected (prevent validation loop)
        if not methods:
            methods = ["keycard"]

        request.session["access_method"] = ",".join(methods)
        request.session.pop("pending_access_methods", None)

        # Assign room
        room_number = str(100 + (reservation["id"] % 50))
        room_payload = {"room_number": room_number, "access_methods": methods}
        request.session["room_payload"] = room_payload

        # If keycard selected, generate and publish RFID token
        if "keycard" in methods:
            try:
                from .mqtt_client import publish_rfid_token, generate_rfid_token

                token = generate_rfid_token()
                result = publish_rfid_token(
                    guest_id=reservation.get("guest_id"),
                    reservation_id=reservation["id"],
                    room_number=room_number,
                    token=token,
                    checkin=reservation.get("checkin"),
                    checkout=reservation.get("checkout"),
                )
                request.session["rfid_token"] = token
                room_payload["rfid_token"] = token
                room_payload["rfid_published"] = result.get("published", False)
                request.session["room_payload"] = room_payload
            except Exception as e:
                logger.error(f"RFID token publish error: {e}")
                # Continue without RFID - staff can issue card manually

        # FORWARD ONLY: face enrollment OR finalize
        if "face" in methods:
            return redirect("kiosk:enroll_face", reservation_id=reservation["id"])
        return redirect("kiosk:finalize", reservation_id=reservation["id"])

    return render(
        request,
        "kiosk/choose_access.html",
        {
            "reservation": reservation,
            "preselected_keycard": "keycard" in preselected,
            "preselected_face": "face" in preselected,
        },
    )


@csrf_exempt
@handle_kiosk_errors
def walkin(request):
    """
    Walk-in guest page - allows registration without prior reservation.

    Shown when no reservation is found after passport verification,
    or when guest data is not found (e.g., after container restart).
    Guest can enter their information manually and create a new reservation.
    
    Pre-fills form with MRZ data from passport scan if available.

    Flow: walkin → reservation_entry → document_signing → finalize
    """
    guest_id = request.session.get("guest_id")
    guest = None

    # Try to get existing guest if we have an ID
    if guest_id:
        try:
            guest = db.get_guest(int(guest_id))
        except Exception as e:
            logger.warning(f"Could not fetch guest {guest_id}: {e}")
            guest = None

    # Get extracted passport data from MRZ scan (if available)
    extracted_data = request.session.get("extracted_passport_data", {})
    
    # Build prefill data from MRZ extraction (always provide all keys)
    # Support both MRZ field names (given_name, nationality_code) and legacy names
    prefill_data = {
        "first_name": "",
        "last_name": "",
        "passport_number": "",
        "date_of_birth": "",
        "nationality": "",
        "sex": "",
    }
    if extracted_data:
        prefill_data = {
            "first_name": extracted_data.get("given_name", "") or extracted_data.get("first_name", "") or extracted_data.get("given_names", ""),
            "last_name": extracted_data.get("surname", "") or extracted_data.get("last_name", ""),
            "passport_number": extracted_data.get("passport_number", "") or extracted_data.get("document_number", ""),
            "date_of_birth": extracted_data.get("date_of_birth", "") or extracted_data.get("birth_date", ""),
            "nationality": extracted_data.get("nationality_code", "") or extracted_data.get("nationality", ""),
            "sex": extracted_data.get("sex", "") or extracted_data.get("gender", ""),
        }
        logger.info(f"Pre-filling walkin form with MRZ data: {prefill_data.get('first_name')} {prefill_data.get('last_name')}")

    # Handle POST - create/update guest from form data
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        passport_number = request.POST.get("passport_number", "").strip()
        date_of_birth = parse_date(request.POST.get("date_of_birth", ""))
        nationality = request.POST.get("nationality", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()

        # Validate required fields
        if not first_name or not last_name:
            return render(
                request,
                "kiosk/walkin.html",
                {
                    "guest": guest,
                    "needs_registration": True,
                    "error": "Please enter your first and last name.",
                    "form_data": request.POST,
                    "prefill_data": prefill_data,
                },
            )

        try:
            # Create or update guest
            guest = db.get_or_create_guest(first_name, last_name, passport_number, date_of_birth)
            
            # Update guest with additional info if available
            if hasattr(db, 'update_guest'):
                db.update_guest(guest['id'], {
                    'nationality': nationality,
                    'email': email,
                    'phone': phone,
                })

            request.session["guest_id"] = guest["id"]
            logger.info(f"Walk-in guest registered: {first_name} {last_name} (ID: {guest['id']})")

            # Redirect to reservation entry
            return redirect("kiosk:reservation_entry")

        except Exception as e:
            logger.error(f"Error creating walk-in guest: {e}")
            return render(
                request,
                "kiosk/walkin.html",
                {
                    "guest": None,
                    "needs_registration": True,
                    "error": "Could not create guest record. Please try again or contact the front desk.",
                    "form_data": request.POST,
                    "prefill_data": prefill_data,
                },
            )

    # GET request - show form
    # If we have a guest, show their info with option to proceed
    # If no guest, show registration form (with MRZ prefill if available)
    needs_registration = guest is None

    return render(
        request,
        "kiosk/walkin.html",
        {
            "guest": guest,
            "needs_registration": needs_registration,
            "prefill_data": prefill_data,
        },
    )


@handle_kiosk_errors
def reservation_entry(request):
    """
    Create reservation for walk-in guest - LINEAR FLOW (no loops).

    Flow: reservation_entry → document_signing → finalize
    Never redirects back to walkin or verify_info.
    If no guest: show error page (don't loop)
    """
    guest_id = request.session.get("guest_id")

    # GUARD: No guest = show error (don't loop)
    if not guest_id:
        return render_error(
            request,
            "Your session has expired. Please start over or contact the front desk for assistance.",
            error_code="SESSION_EXPIRED",
        )

    try:
        guest = db.get_guest(int(guest_id))
    except Exception as e:
        logger.error(f"Database error getting guest: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR",
        )

    if not guest:
        return render_error(
            request,
            "Your guest information could not be found. Please start over or contact the front desk.",
            error_code="GUEST_NOT_FOUND",
        )

    if request.method == "POST":
        resnum = request.POST.get("reservation_number", "").strip()

        try:
            room_count = int(request.POST.get("room_count") or 1)
        except ValueError:
            room_count = 1

        try:
            people_count = int(request.POST.get("people_count") or request.POST.get("room_count") or 1)
        except ValueError:
            people_count = 1

        checkin = parse_date(request.POST.get("checkin") or "") or timezone.now().date()
        checkout = parse_date(request.POST.get("checkout") or "") or (
            timezone.now().date() + datetime.timedelta(days=1)
        )

        # Check if this is a pre-booked guest
        existing_reservation = None
        try:
            res_qs = db.get_reservations_by_guest(guest)
            if res_qs:
                existing_reservation = res_qs[0]
        except Exception as e:
            logger.warning(f"Error checking for existing reservation: {e}")

        # If pre-booked, use existing reservation; otherwise create new one
        if existing_reservation:
            # Pre-booked guest - use their existing reservation
            res = existing_reservation
            request.session["reservation_id"] = existing_reservation["id"]
            logger.info(f"Using pre-booked reservation for guest: {existing_reservation.get('confirmation_number')}")
            checkin = parse_date(existing_reservation.get("checkin")) or checkin
            checkout = parse_date(existing_reservation.get("checkout")) or checkout
        else:
            # Walk-in guest - create new reservation
            # Auto-generate reservation number if not provided
            if not resnum:
                import secrets
                resnum = f"RES-{timezone.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

            try:
                res = db.create_reservation(
                    resnum, guest, checkin, checkout, room_count=room_count, people_count=people_count
                )
            except Exception as e:
                logger.error(f"Database error creating reservation: {e}")
                return render_error(
                    request,
                    "We couldn't create your reservation. Please contact the front desk.",
                    error_code="RESERVATION_CREATE_ERROR",
                )

            # Store reservation ID
            request.session["reservation_id"] = res["id"]
            logger.info(f"Created new walk-in reservation: {resnum}")

        # Update registration data with checkout date
        registration_data = request.session.get("dw_registration_data", {})
        registration_data["checkout"] = checkout.strftime("%Y-%m-%d") if checkout else ""
        registration_data["checkin"] = checkin.strftime("%Y-%m-%d") if checkin else ""
        request.session["dw_registration_data"] = registration_data

        # Generate PDF via MRZ backend (AFTER registration data is complete)
        import uuid
        document_session_id = request.session.get("document_session_id")
        if not document_session_id:
            document_session_id = str(uuid.uuid4())
            request.session["document_session_id"] = document_session_id

        try:
            doc_client = get_document_client()
            result = doc_client.update_document(
                session_id=document_session_id,
                guest_data=registration_data,
                accompanying_guests=registration_data.get("accompanying_guests", [])
            )
            if result.get("filled_document"):
                request.session["mrz_pdf_filename"] = result["filled_document"].get("filename")
                logger.info(f"PDF generated via MRZ backend: {result['filled_document'].get('filename')}")
            else:
                raise MRZAPIError("No PDF generated by MRZ backend")
        except Exception as e:
            logger.error(f"MRZ document API failed: {e}")
            return render_error(
                request,
                "Failed to generate registration document. Please try again or contact the front desk.",
                error_code="PDF_GENERATION_FAILED",
            )

        # Forward to PDF signing page
        return redirect("kiosk:pdf_sign_document")

    # Check if guest already has a pre-booked reservation
    existing_reservation = None
    reservation_type = "walk_in"  # Default to walk-in
    
    try:
        res_qs = db.get_reservations_by_guest(guest)
        if res_qs:
            existing_reservation = res_qs[0]
            reservation_type = "pre_booked"
            # Store in session for later use
            request.session["reservation_id"] = existing_reservation["id"]
            logger.info(f"Found pre-booked reservation for guest: {existing_reservation.get('confirmation_number')}")
    except Exception as e:
        logger.warning(f"Error checking for existing reservation: {e}")

    # Auto-generate suggested reservation number for walk-ins
    import secrets
    suggested_resnum = f"RES-{timezone.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

    return render(request, "kiosk/reservation_entry.html", {
        "guest": guest, 
        "suggested_resnum": suggested_resnum,
        "existing_reservation": existing_reservation,
        "reservation_type": reservation_type,
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
            error_code="DATABASE_ERROR",
        )

    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND",
        )
    # Emulate room capacity coming from an external DB/service
    room_payload = request.session.get("room_payload", {})
    room_number = room_payload.get("room_number") or str(100 + (reservation["id"] % 50))
    # simple emulated capacities
    emu_capacities = {
        "101": 2,
        "102": 4,
        "103": 3,
        "104": 2,
    }
    capacity = emu_capacities.get(room_number, max(1, reservation.get("people_count") or 1))

    existing = db.count_face_enrollments_for_reservation(reservation)
    remaining = max(0, capacity - existing)

    if request.method == "POST":
        count = int(request.POST.get("count") or 0)
        if count <= 0:
            return render(
                request,
                "kiosk/enroll_face.html",
                {
                    "reservation": reservation,
                    "capacity": capacity,
                    "remaining": remaining,
                    "error": "Please specify at least one photo to upload.",
                },
            )
        if count > remaining:
            return render(
                request,
                "kiosk/enroll_face.html",
                {
                    "reservation": reservation,
                    "capacity": capacity,
                    "remaining": remaining,
                    "error": f"Only {remaining} enrollments remaining for room {room_number}.",
                },
            )

        # accept uploads (store image names only)
        saved = 0
        for i in range(1, count + 1):
            f = request.FILES.get(f"face_{i}")
            if f:
                db.create_face_enrollment(
                    reservation["guest"], reservation, existing + saved + 1, image_name=getattr(f, "name", None)
                )
                saved += 1
        return redirect("kiosk:finalize", reservation_id=reservation["id"])

    return render(
        request, "kiosk/enroll_face.html", {"reservation": reservation, "capacity": capacity, "remaining": remaining}
    )


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
            error_code="DATABASE_ERROR",
        )

    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND",
        )

    flow_type = request.session.get("flow_type", "checkin")
    access_method = request.session.get("access_method", "keycard")
    room_payload = request.session.get("room_payload") or {}
    room_number = room_payload.get("room_number") or reservation.get("room_number") or str(100 + (reservation_id % 50))
    rfid_token = room_payload.get("rfid_token")

    context = {
        "reservation": reservation,
        "access_method": access_method,
        "room_number": room_number,
        "rfid_token": rfid_token,
        "flow_type": flow_type,
    }

    # Use different templates for check-in vs check-out
    if flow_type == "checkout":
        lang = request.session.get("language", "en")
        context["kiosk_language"] = lang
        return render(request, "kiosk/finalize_checkout.html", context)
    else:
        lang = request.session.get("language", "en")
        context["kiosk_language"] = lang
        return render(request, "kiosk/finalize_checkin.html", context)


@handle_kiosk_errors
def submit_keycards(request, reservation_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        reservation = db.get_reservation(reservation_id)
    except Exception as e:
        logger.error(f"Database error in submit_keycards: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR",
        )

    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND",
        )

    try:
        # mark keycards returned and finalize payment (demo: always finalize)
        db.submit_keycards(reservation)
        db.finalize_payment(reservation, amount=reservation.get("amount_due", 0) or 0)

        # Deactivate the guest's Dashboard account
        room_payload = request.session.get("room_payload") or {}
        room_number = (
            room_payload.get("room_number") or reservation.get("room_number") or str(100 + (reservation_id % 50))
        )
        dashboard_username = room_payload.get("dashboard_username")

        if dashboard_username:
            deactivate_dashboard_guest_account(username=dashboard_username)
        else:
            # Try by room number
            deactivate_dashboard_guest_account(room_number=room_number)

        # FIX 5: Revoke RFID token on checkout to prevent unauthorized room access
        rfid_token = room_payload.get("rfid_token")
        if rfid_token:
            try:
                from .mqtt_client import revoke_rfid_token
                revoke_rfid_token(rfid_token, room_number, reason="checkout")
                logger.info(f"Revoked RFID token for room {room_number} on checkout")
            except Exception as rfid_error:
                # Log but don't fail checkout - security team can revoke manually if needed
                logger.error(f"Failed to revoke RFID token on checkout: {rfid_error}")

    except Exception as e:
        logger.error(f"Database error finalizing payment: {e}")
        return render_error(
            request, "We couldn't process your checkout. Please contact the front desk.", error_code="PAYMENT_ERROR"
        )

    return redirect("kiosk:finalize", reservation_id=reservation["id"])


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
            error_code="DATABASE_ERROR",
        )

    if not reservation:
        return render_error(
            request,
            "Your reservation could not be found. Please contact the front desk for assistance.",
            error_code="RESERVATION_NOT_FOUND",
        )

    room_payload = request.session.get("room_payload") or {}
    room_number = room_payload.get("room_number") or str(100 + (reservation_id % 50))
    old_token = room_payload.get("rfid_token")

    if request.method == "POST":
        reason = request.POST.get("reason", "stolen")

        try:
            from .mqtt_client import revoke_rfid_token, publish_rfid_token, generate_rfid_token

            # Revoke old token if exists
            if old_token:
                revoke_rfid_token(old_token, room_number, reason=reason)

            # Generate and publish new token
            new_token = generate_rfid_token()
            result = publish_rfid_token(
                guest_id=reservation.get("guest_id"),
                reservation_id=reservation["id"],
                room_number=room_number,
                token=new_token,
                checkin=reservation.get("checkin"),
                checkout=reservation.get("checkout"),
            )

            # Update session with new token
            room_payload["rfid_token"] = new_token
            room_payload["rfid_published"] = result.get("published", False)
            request.session["room_payload"] = room_payload

            return render(
                request,
                "kiosk/report_card_success.html",
                {"reservation": reservation, "room_number": room_number, "new_token": new_token, "reason": reason},
            )

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Card report error: {e}")
            return render(
                request,
                "kiosk/report_card.html",
                {"reservation": reservation, "room_number": room_number, "error": str(e)},
            )

    return render(request, "kiosk/report_card.html", {"reservation": reservation, "room_number": room_number})


@csrf_exempt
def revoke_rfid_card_api(request):
    """
    API endpoint to revoke an RFID card token.
    Used by staff dashboard or security systems.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        room_number = data.get("room_number")
        reason = data.get("reason", "revoked")

        if not token or not room_number:
            return JsonResponse({"error": "token and room_number required"}, status=400)

        from .mqtt_client import revoke_rfid_token

        result = revoke_rfid_token(token, room_number, reason=reason)

        return JsonResponse(
            {
                "success": result.get("success", False),
                "message": "Token revoked" if result.get("success") else "Revocation failed",
                "error": result.get("error"),
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ============================================================================
# DW Registration Card (DW R.C.) Document Views
# ============================================================================


def dw_registration_card(request):
    """
    Display and fill the DW Registration Card with guest data from passport extraction.
    Uses MRZ backend for document processing.

    Flow: passport_scan → dw_registration_card → verify_info → reservation_entry → pdf_sign_document

    GET: Show form pre-filled with data from session or query params
    POST from passport_scan: Store data in session, show form
    POST from this form: Store edited data and proceed to verify_info
    """
    import uuid

    # Get session ID from MRZ backend or create new one
    document_session_id = request.session.get("document_session_id")
    if not document_session_id:
        document_session_id = str(uuid.uuid4())
        request.session["document_session_id"] = document_session_id
        logger.warning(f"No document_session_id found in session, created new: {document_session_id}")
    else:
        logger.info(f"Using document_session_id from session: {document_session_id}")

    # Check if this is a POST from passport_scan (has basic passport fields but no signature_method)
    # vs a POST from this form itself (has signature_method)
    is_from_passport_scan = request.method == "POST" and not request.POST.get("signature_method")
    
    if is_from_passport_scan:
        # Store passport data in session and display the form for editing
        passport_data = {
            "surname": request.POST.get("last_name", "").strip(),
            "name": request.POST.get("first_name", "").strip(),
            "given_name": request.POST.get("first_name", "").strip(),
            "nationality": request.POST.get("nationality", "").strip(),
            "nationality_code": request.POST.get("nationality_code", "").strip() or request.POST.get("nationality", "").strip(),
            "passport_number": request.POST.get("passport_number", "").strip(),
            "date_of_birth": request.POST.get("date_of_birth", "").strip(),
            "sex": request.POST.get("sex", "").strip(),
            "expiry_date": request.POST.get("expiry_date", "").strip(),
            "country": request.POST.get("issuer_code", "").strip() or request.POST.get("nationality", "").strip(),
            "issuer_code": request.POST.get("issuer_code", "").strip() or request.POST.get("nationality_code", "").strip(),
        }
        
        # Store document_session_id if provided from passport scan
        if request.POST.get("document_session_id"):
            document_session_id = request.POST.get("document_session_id")
            request.session["document_session_id"] = document_session_id
            
        request.session["extracted_passport_data"] = passport_data
        logger.info(f"Received passport data from scan, displaying registration form")
        
        # Show form with passport data
        initial_data = {
            **passport_data,
            "checkin": str(timezone.now().date()),
            "checkout": "",
            "people_count": "1",
            "profession": "",
            "hometown": "",
            "email": "",
            "phone": "",
        }
        return render(request, "kiosk/dw_registration_card.html", {"initial": initial_data})

    # Get extracted data from session or query params
    extracted_data = request.session.get("extracted_passport_data", {})
    
    # DEBUG: Log extracted data from session
    logger.info("=" * 60)
    logger.info("DW_REGISTRATION_CARD: Session extracted_passport_data:")
    for key, value in extracted_data.items():
        logger.info(f"  {key}: '{value}'")
    logger.info("=" * 60)

    # Merge with query params (allows pre-filling from /document/ link)
    # Support both MRZ field names (given_name, nationality_code, issuer_code) and UI names
    initial_data = {
        "surname": request.GET.get("surname") or request.GET.get("last_name") or extracted_data.get("surname", "") or extracted_data.get("last_name", ""),
        "name": request.GET.get("name") or request.GET.get("first_name") or extracted_data.get("given_name", "") or extracted_data.get("first_name", ""),
        "nationality": request.GET.get("nationality") or extracted_data.get("nationality_code", "") or extracted_data.get("nationality", ""),
        "nationality_code": request.GET.get("nationality_code") or extracted_data.get("nationality_code", "") or extracted_data.get("nationality", ""),
        "passport_number": request.GET.get("passport_number") or extracted_data.get("passport_number", "") or extracted_data.get("document_number", ""),
        "date_of_birth": request.GET.get("date_of_birth") or extracted_data.get("date_of_birth", "") or extracted_data.get("birth_date", ""),
        "sex": extracted_data.get("sex", "") or extracted_data.get("gender", ""),
        "expiry_date": extracted_data.get("expiry_date", ""),
        "country": request.GET.get("country") or extracted_data.get("issuer_code", "") or extracted_data.get("issuer_country", ""),
        "issuer_code": request.GET.get("issuer_code") or extracted_data.get("issuer_code", "") or extracted_data.get("issuer_country", ""),
        "profession": request.GET.get("profession", ""),
        "hometown": request.GET.get("hometown", ""),
        "email": request.GET.get("email", ""),
        "phone": request.GET.get("phone", ""),
        "checkin": request.GET.get("checkin") or str(timezone.now().date()),
        "checkout": request.GET.get("checkout", ""),
        "people_count": request.GET.get("people_count", "1"),
    }

    if request.method == "POST":
        # Collect form data - include both UI names and MRZ-compatible names
        # IMPORTANT: Always preserve MRZ-extracted values even if visible fields are empty
        form_data = {
            "surname": request.POST.get("surname", "").strip(),
            "name": request.POST.get("name", "").strip(),
            "given_name": request.POST.get("name", "").strip(),  # MRZ-compatible alias
            "nationality": request.POST.get("nationality", "").strip(),
            "nationality_code": request.POST.get("nationality", "").strip(),  # Now comes from visible field
            "passport_number": request.POST.get("passport_number", "").strip(),
            "date_of_birth": request.POST.get("date_of_birth", "").strip(),
            "sex": request.POST.get("sex", "").strip(),
            "expiry_date": request.POST.get("expiry_date", "").strip(),
            "profession": request.POST.get("profession", "").strip(),
            "hometown": request.POST.get("hometown", "").strip(),
            "country": request.POST.get("country", "").strip(),
            "issuer_code": request.POST.get("country", "").strip(),  # country field now contains issuer_code
            "email": request.POST.get("email", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "checkin": request.POST.get("checkin", "").strip(),
            "checkout": request.POST.get("checkout", "").strip(),
        }

        # Handle accompanying guests
        try:
            people_count = max(1, int(request.POST.get("people_count") or 1))
        except ValueError:
            people_count = 1

        accompanying = []
        for i in range(1, people_count):
            name = request.POST.get(f"accompany_name_{i}", "").strip()
            if name:
                accompanying.append(
                    {
                        "name": name,
                        "nationality": request.POST.get(f"accompany_nationality_{i}", "").strip(),
                        "passport": request.POST.get(f"accompany_passport_{i}", "").strip(),
                    }
                )

        form_data["accompanying_guests"] = accompanying
        form_data["signature_method"] = request.POST.get("signature_method", "physical")

        # Store in session for next steps
        request.session["dw_registration_data"] = form_data
        logger.info(f"Stored dw_registration_data in session, redirecting to verify_info")

        # Redirect to verify_info to create guest and look up reservation
        return redirect("kiosk:verify_info")

    return render(request, "kiosk/dw_registration_card.html", {"initial": initial_data})


@handle_kiosk_errors
def select_access_method(request):
    """
    Access method selection page - SEPARATE PAGE in the flow.

    User chooses between keycard, face ID, or both.
    This page comes AFTER document signing and BEFORE room assignment.

    Flow: dw_sign_document → select_access_method → finalize (or enroll_face)
    """
    guest_id = request.session.get("guest_id")
    reservation_id = request.session.get("reservation_id")
    registration_data = request.session.get("dw_registration_data", {}) or request.session.get("registration_data", {})

    # GUARD: No guest AND no registration data = show error (don't loop)
    if not guest_id and not registration_data:
        return render_error(
            request,
            "Your session has expired. Please start over or contact the front desk for assistance.",
            error_code="SESSION_EXPIRED",
        )

    # Create guest from registration data if we don't have one yet
    if not guest_id and registration_data:
        try:
            guest_info = registration_data.get("guest", registration_data)
            first = guest_info.get("name", "") or guest_info.get("first_name", "")
            last = guest_info.get("surname", "") or guest_info.get("last_name", "")
            passport = guest_info.get("passport_number", "")
            dob_str = guest_info.get("date_of_birth", "")
            dob = parse_date(dob_str) if dob_str else None

            if first and last:
                guest = db.get_or_create_guest(first, last, passport, dob)
                guest_id = guest["id"]
                request.session["guest_id"] = guest_id
        except Exception as e:
            logger.error(f"Error creating guest in select_access_method: {e}")

    # Get reservation
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
                    request.session["reservation_id"] = reservation["id"]
                    reservation_id = reservation["id"]
    except Exception as e:
        logger.error(f"Database error in select_access_method: {e}")
        return render_error(
            request,
            "We're experiencing technical difficulties. Please contact the front desk.",
            error_code="DATABASE_ERROR",
        )

    # Pre-selected methods from session
    preselected = request.session.get("pending_access_methods", [])

    if request.method == "POST":
        # Allow multiple access methods (checkboxes). Default to keycard if none selected.
        methods = []
        if request.POST.get("access_keycard"):
            methods.append("keycard")
        if request.POST.get("access_face"):
            methods.append("face")

        # Default to keycard if nothing selected
        if not methods:
            methods = ["keycard"]

        request.session["access_method"] = ",".join(methods)
        request.session["pending_access_methods"] = methods

        # Assign room
        room_number = str(100 + (reservation_id % 50)) if reservation_id else "101"
        room_payload = {"room_number": room_number, "access_methods": methods}

        # If keycard selected, generate and publish RFID token
        if "keycard" in methods and reservation:
            try:
                from .mqtt_client import publish_rfid_token, generate_rfid_token

                token = generate_rfid_token()
                result = publish_rfid_token(
                    guest_id=reservation.get("guest_id"),
                    reservation_id=reservation["id"],
                    room_number=room_number,
                    token=token,
                    checkin=reservation.get("checkin"),
                    checkout=reservation.get("checkout"),
                )
                request.session["rfid_token"] = token
                room_payload["rfid_token"] = token
                room_payload["rfid_published"] = result.get("published", False)
            except Exception as e:
                logger.error(f"RFID token publish error: {e}")

        request.session["room_payload"] = room_payload

        # Create guest account in Dashboard for room access
        if reservation:
            guest = reservation.get("guest") or {}
            registration_data = request.session.get("dw_registration_data", {})

            dashboard_guest = {
                "first_name": (
                    guest.get("first_name") or registration_data.get("name", "").split()[0]
                    if registration_data.get("name")
                    else ""
                ),
                "last_name": guest.get("last_name") or registration_data.get("surname", ""),
                "email": registration_data.get("email", ""),
                "phone": registration_data.get("phone", ""),
                "passport_number": guest.get("passport_number") or registration_data.get("passport_number", ""),
            }

            dashboard_credentials = create_dashboard_guest_account(
                guest_data=dashboard_guest, reservation_data=reservation, room_number=room_number
            )

            if dashboard_credentials:
                request.session["dashboard_credentials"] = dashboard_credentials
                room_payload["dashboard_username"] = dashboard_credentials.get("username")
                request.session["room_payload"] = room_payload

        # FORWARD ONLY: face enrollment OR finalize
        if "face" in methods and reservation:
            return redirect("kiosk:enroll_face", reservation_id=reservation["id"])
        elif reservation:
            return redirect("kiosk:finalize", reservation_id=reservation["id"])
        else:
            return redirect("kiosk:reservation_entry")

    return render(
        request,
        "kiosk/select_access_method.html",
        {
            "reservation": reservation,
            "preselected_keycard": "keycard" in preselected,
            "preselected_face": "face" in preselected,
        },
    )


@handle_kiosk_errors
def pdf_sign_document(request):
    """
    PDF Document Signing Page - UNIFIED FLOW.

    Shows the registration document as an embedded PDF viewer and allows
    the user to sign directly on the page. The document is a single page PDF.
    
    This is the main document signing view used by all flows:
    - Check-in with reservation: verify → pdf_sign_document → select_access_method → finalize
    - Walk-in: verify → walkin → reservation → pdf_sign_document → select_access_method → finalize
    - DW Registration: dw_registration_card → pdf_sign_document → select_access_method → finalize
    
    Supports:
    - Digital signature on PDF (canvas overlay)
    - Print option for physical signature at front desk
    """
    import uuid

    # Check for registration data from EITHER flow (DW or legacy)
    registration_data = request.session.get("dw_registration_data", {})
    if not registration_data:
        # Fallback to legacy registration_data key
        legacy_data = request.session.get("registration_data", {})
        if legacy_data:
            # Convert legacy format to expected format
            guest_info = legacy_data.get("guest", {})
            registration_data = {
                "name": guest_info.get("name", ""),
                "surname": guest_info.get("surname", ""),
                "nationality": guest_info.get("nationality", ""),
                "passport_number": guest_info.get("passport_number", ""),
                "date_of_birth": guest_info.get("date_of_birth", ""),
                "profession": guest_info.get("profession", ""),
                "hometown": guest_info.get("hometown", ""),
                "country": guest_info.get("country", ""),
                "email": guest_info.get("email", ""),
                "phone": guest_info.get("phone", ""),
                "checkin": guest_info.get("checkin", ""),
                "checkout": guest_info.get("checkout", ""),
                "people_count": legacy_data.get("people_count", 1),
                "accompany": legacy_data.get("accompany", []),
                "accompany_count": legacy_data.get("accompany_count", 0),
                "signature_method": legacy_data.get("signature_method", "digital"),
            }
            # Store in dw_registration_data for consistency
            request.session["dw_registration_data"] = registration_data

    # Third fallback: Build registration data from guest/reservation in database
    # This handles the walk-in flow where only guest_id and reservation_id are set
    if not registration_data:
        guest_id = request.session.get("guest_id")
        reservation_id = request.session.get("reservation_id")

        if guest_id:
            try:
                guest = db.get_guest(int(guest_id))
                if guest:
                    reservation = None
                    if reservation_id:
                        reservation = db.get_reservation(int(reservation_id))
                    elif guest:
                        res_qs = db.get_reservations_by_guest(guest)
                        if res_qs:
                            reservation = res_qs[-1]
                            request.session["reservation_id"] = reservation["id"]

                    # Build registration data from database records
                    registration_data = {
                        "name": guest.get("first_name", ""),
                        "surname": guest.get("last_name", ""),
                        "nationality": guest.get("nationality", ""),
                        "passport_number": guest.get("passport_number", ""),
                        "date_of_birth": str(guest.get("date_of_birth", "")) if guest.get("date_of_birth") else "",
                        "profession": "",
                        "hometown": "",
                        "country": "",
                        "email": guest.get("email", ""),
                        "phone": guest.get("phone", ""),
                        "checkin": (
                            str(reservation.get("checkin", "")) if reservation and reservation.get("checkin") else ""
                        ),
                        "checkout": (
                            str(reservation.get("checkout", "")) if reservation and reservation.get("checkout") else ""
                        ),
                        "people_count": reservation.get("people_count", 1) if reservation else 1,
                        "accompany": [],
                        "accompany_count": 0,
                        "signature_method": "digital",
                    }
                    request.session["dw_registration_data"] = registration_data
                    logger.info(f"Built registration data from guest {guest_id} for PDF signing")
            except Exception as e:
                logger.error(f"Error building registration data from guest: {e}")

    document_session_id = request.session.get("document_session_id", str(uuid.uuid4()))
    request.session["document_session_id"] = document_session_id

    # GUARD: No registration data = show error (don't loop back)
    if not registration_data:
        return render_error(
            request,
            "Your registration session has expired. Please start over or contact the front desk.",
            error_code="SESSION_EXPIRED",
        )

    # Get reservation if exists
    reservation = None
    guest_id = request.session.get("guest_id")
    if guest_id:
        guest = db.get_guest(int(guest_id))
        if guest:
            res_qs = db.get_reservations_by_guest(guest)
            if res_qs:
                reservation = res_qs[-1]
                request.session["reservation_id"] = reservation["id"]

    # Generate PDF via MRZ backend service (required)
    pdf_url = None
    mrz_pdf_filename = None
    pdf_error = None

    try:
        doc_client = get_document_client()
        mrz_result = doc_client.update_document(
            session_id=document_session_id,
            guest_data=registration_data
        )
        
        if mrz_result.get("success") and mrz_result.get("filled_document"):
            filled_doc = mrz_result.get("filled_document", {})
            mrz_pdf_filename = filled_doc.get("filename")
            if mrz_pdf_filename:
                # Store the PDF info for serving via proxy
                request.session["mrz_pdf_filename"] = mrz_pdf_filename
                pdf_url = f"/document/preview-pdf/?session={document_session_id}"
                logger.info(f"Generated PDF via MRZ backend: {mrz_pdf_filename}")
            else:
                pdf_error = "MRZ backend did not return a PDF filename"
        else:
            pdf_error = mrz_result.get("error", "MRZ backend failed to generate PDF")
    except Exception as e:
        logger.error(f"MRZ backend PDF generation failed: {e}")
        pdf_error = str(e)

    # If PDF generation failed, show error
    if not pdf_url:
        return render_error(
            request,
            f"Failed to generate registration document. Please try again or contact the front desk. Error: {pdf_error}",
            error_code="PDF_GENERATION_FAILED",
        )

    if request.method == "POST":
        # Get signature type (digital or physical)
        signature_type = request.POST.get("signature_type", "digital")

        if signature_type == "physical":
            # User chose to print and sign physically
            registration_data["signature_type"] = "physical"
            registration_data["document_printed"] = True
            registration_data["document_signed"] = False  # Will be signed at front desk
            request.session["dw_registration_data"] = registration_data

            # Create guest if not exists
            if not guest_id:
                first = registration_data.get("name", "")
                last = registration_data.get("surname", "")
                passport = registration_data.get("passport_number", "")
                dob = registration_data.get("date_of_birth", "")
                guest = db.create_guest(first, last, passport, dob)
                request.session["guest_id"] = guest["id"]
                guest_id = guest["id"]

            request.session["registration_complete"] = True

            # FORWARD: access method selection page
            return redirect("kiosk:select_access_method")

        # Digital signature flow
        signature_svg = request.POST.get("signature_svg", "")
        signature_data = request.POST.get("signature_data", "")

        # Use SVG if available, fall back to PNG
        signature_to_use = signature_svg or signature_data

        if not signature_to_use:
            return render(
                request,
                "kiosk/pdf_sign_document.html",
                {
                    "registration_data": registration_data,
                    "pdf_url": pdf_url,
                    "reservation": reservation,
                    "error": "Please draw your signature before continuing.",
                },
            )

        # Save signature locally as SVG (preferred) or PNG
        try:
            sig_dir = os.path.join(settings.BASE_DIR, "media", "signatures")
            os.makedirs(sig_dir, exist_ok=True)

            if signature_svg:
                sig_filename = f"signature_{guest_id or 'guest'}_{int(time.time())}.svg"
                sig_path = os.path.join(sig_dir, sig_filename)
                with open(sig_path, "w", encoding="utf-8") as f:
                    f.write(signature_svg)
                registration_data["signature_format"] = "svg"
            elif signature_data and signature_data.startswith("data:image/png;base64,"):
                sig_filename = f"signature_{guest_id or 'guest'}_{int(time.time())}.png"
                sig_path = os.path.join(sig_dir, sig_filename)
                sig_bytes = base64.b64decode(signature_data.split(",")[1])
                with open(sig_path, "wb") as f:
                    f.write(sig_bytes)
                registration_data["signature_format"] = "png"
            else:
                sig_path = None
                sig_filename = None

            if sig_path:
                registration_data["signature_file"] = sig_filename
                request.session["dw_signature_path"] = sig_path

        except Exception as e:
            logger.warning(f"Failed to save signature: {e}")

        # Update registration data with signature
        registration_data["signature_data"] = signature_to_use
        registration_data["signature_type"] = "digital"
        registration_data["document_signed"] = True
        request.session["dw_registration_data"] = registration_data

        # Get PDF filename from MRZ backend (stored in session)
        mrz_pdf_filename = request.session.get("mrz_pdf_filename")

        # Store signed document in database
        try:
            document_record = db.store_signed_document(
                guest_id=guest_id,
                reservation_id=reservation["id"] if reservation else None,
                guest_data=registration_data,
                signature_svg=signature_svg,
                signature_path=sig_path if "sig_path" in dir() else None,
                pdf_path=mrz_pdf_filename,
            )
            request.session["signed_document_id"] = document_record.get("document_id")
            registration_data["signature_stored_in_db"] = True
        except Exception as e:
            logger.warning(f"Failed to store signed document: {e}")
            registration_data["signature_stored_in_db"] = False

        request.session["dw_registration_data"] = registration_data

        # Create guest if not exists
        if not guest_id:
            first = registration_data.get("name", "")
            last = registration_data.get("surname", "")
            passport = registration_data.get("passport_number", "")
            dob = registration_data.get("date_of_birth", "")
            guest = db.create_guest(first, last, passport, dob)
            request.session["guest_id"] = guest["id"]
            guest_id = guest["id"]

        # Store completed registration
        request.session["registration_complete"] = True

        # FORWARD based on flow type:
        # - checkout: go to submit_keycards (return keycards and finalize payment)
        # - checkin: go to select_access_method (get new keycards/face enrollment)
        checkout_mode = request.session.get("checkout_mode", False)
        checkout_reservation_id = request.session.get("checkout_reservation_id")
        
        if checkout_mode and checkout_reservation_id:
            logger.info(f"Checkout flow: redirecting to submit_keycards for reservation {checkout_reservation_id}")
            return redirect("kiosk:submit_keycards", reservation_id=checkout_reservation_id)
        else:
            return redirect("kiosk:select_access_method")

    return render(
        request,
        "kiosk/pdf_sign_document.html",
        {
            "registration_data": registration_data,
            "pdf_url": pdf_url,
            "reservation": reservation,
        },
    )


def serve_preview_pdf(request):
    """
    Serve the preview PDF for the embedded viewer.
    Fetches PDF from MRZ backend only.
    """
    document_session_id = request.session.get("document_session_id")
    mrz_pdf_filename = request.session.get("mrz_pdf_filename")
    
    if not mrz_pdf_filename or not document_session_id:
        logger.error("No PDF available - missing session_id or filename")
        return HttpResponse("PDF not available. Please go back and try again.", status=404)
    
    try:
        doc_client = get_document_client()
        pdf_content = doc_client.get_pdf_content(
            session_id=document_session_id,
            filename=mrz_pdf_filename
        )
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="registration_card.pdf"'
        logger.info(f"Serving PDF from MRZ backend: {mrz_pdf_filename}")
        return response
    except Exception as e:
        logger.error(f"Failed to fetch PDF from MRZ backend: {e}")
        return HttpResponse(f"Failed to load PDF: {e}", status=500)


@csrf_exempt
def dw_generate_pdf(request):
    """
    Generate/serve the DW R.C. for printing.

    Redirects to serve PDF from MRZ backend.
    """
    document_session_id = request.session.get("document_session_id")
    mrz_pdf_filename = request.session.get("mrz_pdf_filename")
    
    if not mrz_pdf_filename or not document_session_id:
        return HttpResponse("Document not available. Please complete registration first.", status=404)
    
    # Redirect to PDF serve endpoint
    pdf_url = f"/document/preview-pdf/?session={document_session_id}"
    return redirect(pdf_url)


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
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Save to session
            request.session["extracted_passport_data"] = data

            # Store passport image in database if provided
            passport_image_record = None
            guest_id = data.get("guest_id")
            reservation_id = data.get("reservation_id")
            image_path = data.get("image_path")
            image_base64 = data.get("image_base64")

            # Save image file if base64 provided
            if image_base64 and not image_path:
                try:
                    import base64 as b64

                    img_dir = os.path.join(settings.BASE_DIR, "media", "passport_scans")
                    os.makedirs(img_dir, exist_ok=True)

                    timestamp = int(time.time())
                    img_filename = f"passport_{timestamp}.jpg"
                    image_path = os.path.join(img_dir, img_filename)

                    # Decode and save image
                    img_data = b64.b64decode(image_base64)
                    with open(image_path, "wb") as f:
                        f.write(img_data)

                    logger.info(f"Saved passport image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to save passport image file: {e}")
                    image_path = None

            # Store passport image record in database
            if image_path or image_base64:
                mrz_data = {
                    "first_name": data.get("first_name"),
                    "last_name": data.get("last_name"),
                    "passport_number": data.get("passport_number"),
                    "date_of_birth": data.get("date_of_birth"),
                    "nationality": data.get("nationality"),
                    "sex": data.get("sex"),
                    "expiry_date": data.get("expiry_date"),
                }

                passport_image_record = db.store_passport_image(
                    guest_id=guest_id,
                    reservation_id=reservation_id,
                    image_path=image_path,
                    image_data_base64=image_base64 if not image_path else None,
                    mrz_data=mrz_data,
                )

                logger.info(f"Stored passport image in database: {passport_image_record.get('passport_image_id')}")

            response = {"success": True}
            if passport_image_record:
                response["passport_image_stored"] = True
                response["passport_image_id"] = passport_image_record.get("passport_image_id")
                response["database_record_id"] = passport_image_record.get("id")

            return JsonResponse(response)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
    return JsonResponse({"error": "POST only"}, status=400)


# ============================================================================
# MRZ Service API Proxy Endpoints
# ============================================================================


def mrz_service_health(request):
    """
    Check if the MRZ microservice is healthy.
    Returns JSON with status info.
    """
    if not USE_MRZ_SERVICE:
        return JsonResponse(
            {"available": False, "mode": "local", "message": "Running in local mode without MRZ service"}
        )

    try:
        client = get_mrz_client()
        is_healthy = client.health_check()
        return JsonResponse(
            {
                "available": is_healthy,
                "mode": "service",
                "service_url": os.environ.get("MRZ_SERVICE_URL", "not configured"),
            }
        )
    except Exception as e:
        return JsonResponse({"available": False, "mode": "service", "error": str(e)})


def mrz_video_feed_url(request):
    """
    Get the URL for the MRZ service video feed.
    The frontend can use this to display the camera stream.
    """
    if not USE_MRZ_SERVICE:
        return JsonResponse({"available": False, "error": "MRZ service not configured"})

    try:
        client = get_mrz_client()
        feed_url = client.get_video_feed_url()
        return JsonResponse({"available": True, "video_feed_url": feed_url})
    except Exception as e:
        return JsonResponse({"available": False, "error": str(e)})


@csrf_exempt
def mrz_detect(request):
    """
    Proxy document detection request to MRZ backend service.
    Used for auto-capture functionality with browser camera.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        # Fallback: simple detection simulation
        return JsonResponse({"detected": False, "confidence": 0, "ready_for_capture": False, "mode": "local"})

    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL

        # Forward the request body to the MRZ backend
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/detect", json=request.body and json.loads(request.body) or {}, timeout=5
        )
        return JsonResponse(response.json())
    except Exception as e:
        return JsonResponse({"detected": False, "error": str(e)})


@csrf_exempt
def mrz_extract(request):
    """
    Proxy MRZ extraction request to MRZ backend service.
    Receives base64 image from browser camera and returns extracted data.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({"success": False, "error": "MRZ service not configured", "mode": "local"})

    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL

        # Forward the request body to the MRZ backend
        body = json.loads(request.body) if request.body else {}
        response = requests.post(f"{MRZ_SERVICE_URL}/api/extract", json=body, timeout=30)
        result = response.json()

        if result.get("success"):
            # Convert to kiosk format
            kiosk_data = convert_mrz_to_kiosk_format(result.get("data", {}))
            return JsonResponse(
                {
                    "success": True,
                    "data": result.get("data"),  # Return raw data for display
                    "kiosk_data": kiosk_data,  # Also return kiosk format
                    "timestamp": result.get("timestamp"),
                    "filled_document": result.get("filled_document"),
                }
            )
        else:
            return JsonResponse(result, status=422)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# WebRTC Stream API Proxy Endpoints
# =============================================================================


@csrf_exempt
def mrz_stream_session(request):
    """
    Create a new WebRTC stream session.
    Proxies to Flask /api/stream/session endpoint.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({"success": False, "error": "MRZ service not configured"}, status=503)

    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL

        response = requests.post(f"{MRZ_SERVICE_URL}/api/stream/session", timeout=5)
        return JsonResponse(response.json())
    except Exception as e:
        logger.error(f"Stream session creation failed: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def mrz_stream_session_delete(request, session_id):
    """
    Close and cleanup a stream session.
    Proxies to Flask DELETE /api/stream/session/<session_id> endpoint.
    """
    if request.method != "DELETE":
        return JsonResponse({"error": "DELETE only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({"success": False, "error": "MRZ service not configured"}, status=503)

    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL

        response = requests.delete(f"{MRZ_SERVICE_URL}/api/stream/session/{session_id}", timeout=5)
        return JsonResponse(response.json())
    except Exception as e:
        logger.error(f"Stream session delete failed: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def mrz_stream_frame(request):
    """
    Process a frame from WebRTC stream.
    Proxies to Flask /api/stream/frame endpoint.
    
    This is called at ~20fps (every 50ms) for real-time detection.
    Returns detection status, corners, stability count, quality score.
    """
    import requests
    
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({
            "detected": False, 
            "error": "MRZ service not configured",
            "stable_count": 0,
            "ready_for_capture": False
        })

    try:
        from .mrz_api_client import MRZ_SERVICE_URL

        body = json.loads(request.body) if request.body else {}
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/stream/frame",
            json=body,
            timeout=2  # Short timeout for real-time
        )
        return JsonResponse(response.json())
    except requests.exceptions.Timeout:
        return JsonResponse({
            "detected": False,
            "error": "Backend timeout",
            "stable_count": 0,
            "ready_for_capture": False
        })
    except Exception as e:
        return JsonResponse({
            "detected": False,
            "error": str(e),
            "stable_count": 0,
            "ready_for_capture": False
        })


@csrf_exempt
def mrz_stream_video_frames(request):
    """
    Process a batch of video frames (24fps video stream).
    Proxies to Flask /api/stream/video/frames endpoint.
    
    The kiosk captures at 24fps and sends batches of frames.
    Backend processes frames and returns detection results.
    """
    import requests
    
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({
            "detected": False, 
            "error": "MRZ service not configured",
            "frames_processed": 0,
            "ready_for_capture": False
        })

    try:
        from .mrz_api_client import MRZ_SERVICE_URL

        body = json.loads(request.body) if request.body else {}
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/stream/video/frames",
            json=body,
            timeout=5  # Slightly longer timeout for batch processing
        )
        return JsonResponse(response.json())
    except requests.exceptions.Timeout:
        return JsonResponse({
            "detected": False,
            "error": "Backend timeout",
            "frames_processed": 0,
            "ready_for_capture": False
        })
    except Exception as e:
        return JsonResponse({
            "detected": False,
            "error": str(e),
            "frames_processed": 0,
            "ready_for_capture": False
        })


@csrf_exempt
def mrz_stream_video_chunk(request):
    """
    Process a video chunk (raw WebM/MP4 video data).
    Proxies to Flask /api/stream/video endpoint.
    
    Backend splits the video into frames and processes them.
    """
    import requests
    
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({
            "detected": False, 
            "error": "MRZ service not configured",
            "frames_processed": 0,
            "ready_for_capture": False
        })

    try:
        from .mrz_api_client import MRZ_SERVICE_URL

        # Forward the multipart form data
        session_id = request.POST.get('session_id')
        chunk_index = request.POST.get('chunk_index', '0')
        video_file = request.FILES.get('video')
        
        if not session_id or not video_file:
            return JsonResponse({
                "detected": False,
                "error": "session_id and video file required",
                "frames_processed": 0
            }, status=400)
        
        files = {'video': (video_file.name, video_file.read(), video_file.content_type)}
        data = {'session_id': session_id, 'chunk_index': chunk_index}
        
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/stream/video",
            files=files,
            data=data,
            timeout=10  # Longer timeout for video processing
        )
        return JsonResponse(response.json())
    except requests.exceptions.Timeout:
        return JsonResponse({
            "detected": False,
            "error": "Backend timeout",
            "frames_processed": 0,
            "ready_for_capture": False
        })
    except Exception as e:
        logger.error(f"Video chunk proxy error: {e}")
        return JsonResponse({
            "detected": False,
            "error": str(e),
            "frames_processed": 0,
            "ready_for_capture": False
        })


@csrf_exempt
def mrz_stream_capture(request):
    """
    Capture the best frame from stream session and extract MRZ.
    Proxies to Flask /api/stream/capture endpoint.
    
    Called when ready_for_capture is true.
    Returns extracted MRZ data.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    if not USE_MRZ_SERVICE:
        return JsonResponse({"success": False, "error": "MRZ service not configured"}, status=503)

    try:
        import requests
        from .mrz_api_client import MRZ_SERVICE_URL

        body = json.loads(request.body) if request.body else {}
        response = requests.post(
            f"{MRZ_SERVICE_URL}/api/stream/capture",
            json=body,
            timeout=30  # Longer timeout for MRZ extraction
        )
        result = response.json()

        if result.get("success"):
            # Convert to kiosk format for form population
            kiosk_data = convert_mrz_to_kiosk_format(result.get("data", {}))
            result["kiosk_data"] = kiosk_data

        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Stream capture failed: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def passport_scan(request):
    """
    Passport scanning page with browser-based camera and auto-capture.
    Uses WebRTC to capture from browser, sends to MRZ backend for processing.
    """
    mrz_service_url = "/api/mrz"  # Proxy through Django
    return render(request, "kiosk/passport_scan.html", {"mrz_service_url": mrz_service_url})


def face_capture(request, reservation_id):
    """
    Face capture page with browser-based camera and auto-capture on face detection.
    """
    from . import emulator as db

    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404("Reservation not found")

    # Get room capacity for max faces
    room = reservation.get("room")
    max_faces = room.get("capacity", 4) if room else 4

    return render(request, "kiosk/face_capture.html", {"reservation": reservation, "max_faces": max_faces})


@csrf_exempt
def save_faces(request, reservation_id):
    """
    Save captured face images for a reservation.
    Receives JSON array of base64 face images from browser camera.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    from . import emulator as db

    reservation = db.get_reservation(reservation_id)
    if not reservation:
        raise Http404("Reservation not found")

    try:
        face_data = request.POST.get("face_data", "[]")
        faces = json.loads(face_data)

        # In production, save face images to storage and register with face recognition system
        # For now, just store the count
        enrolled_count = len(faces)

        # Update reservation or guest with face enrollment status
        # db.update_reservation_faces(reservation_id, enrolled_count)

        return redirect("kiosk:finalize", reservation_id=reservation_id)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
            "session_id": "abc123",
            "filled_document": { "path": "...", "filename": "..." },
            "pdf_url": "/document/preview-pdf/?session=..."
        }
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get("session_id", str(__import__("uuid").uuid4()))
        guest_data = data.get("guest_data", {})
        accompanying = data.get("accompanying_guests", [])

        if not guest_data:
            return JsonResponse({"success": False, "error": "guest_data is required"}, status=400)

        # Store in Django session
        request.session["document_session_id"] = session_id
        request.session["dw_registration_data"] = guest_data

        # Generate PDF via MRZ backend (required)
        try:
            doc_client = get_document_client()
            result = doc_client.update_document(
                session_id=session_id, guest_data=guest_data, accompanying_guests=accompanying
            )
            # Store PDF filename for later serving
            if result.get("filled_document"):
                request.session["mrz_pdf_filename"] = result["filled_document"].get("filename")
            # Add PDF URL to result
            result["pdf_url"] = f"/document/preview-pdf/?session={session_id}"
            return JsonResponse(result)
        except MRZAPIError as e:
            logger.error(f"MRZ document API failed: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Failed to generate PDF: {e}",
                    "error_code": "PDF_GENERATION_FAILED"
                },
                status=500
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Document update API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get("session_id")
        guest_data = data.get("guest_data")

        # Use session data if guest_data not provided
        if not guest_data and session_id:
            guest_data = request.session.get("dw_registration_data", {})

        if not guest_data:
            return JsonResponse({"success": False, "error": "guest_data or valid session_id is required"}, status=400)

        # Use MRZ backend only
        try:
            doc_client = get_document_client()
            result = doc_client.get_document_preview(session_id=session_id, guest_data=guest_data)
            return JsonResponse(result)
        except MRZAPIError as e:
            logger.error(f"MRZ preview API failed: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Failed to get document preview: {e}",
                    "error_code": "PREVIEW_FAILED"
                },
                status=500
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Document preview API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get("session_id")
        guest_data = data.get("guest_data")
        signature_svg = data.get("signature_svg", "")
        guest_id = data.get("guest_id")
        reservation_id = data.get("reservation_id")

        if not guest_data:
            guest_data = request.session.get("dw_registration_data", {})

        if not signature_svg:
            return JsonResponse({"success": False, "error": "signature_svg is required"}, status=400)

        # Save signature locally as SVG file
        sig_path = None
        try:
            sig_dir = os.path.join(settings.BASE_DIR, "media", "signatures")
            os.makedirs(sig_dir, exist_ok=True)

            sig_filename = f"signature_{session_id}_{int(time.time())}.svg"
            sig_path = os.path.join(sig_dir, sig_filename)

            with open(sig_path, "w", encoding="utf-8") as f:
                f.write(signature_svg)

            logger.info(f"Saved SVG signature file: {sig_path}")
        except Exception as e:
            logger.warning(f"Failed to save signature file: {e}")

        # Get PDF path from MRZ backend (stored in session)
        pdf_filename = request.session.get("mrz_pdf_filename")

        # Store signed document in kiosk database
        document_record = db.store_signed_document(
            guest_id=guest_id,
            reservation_id=reservation_id,
            guest_data=guest_data,
            signature_svg=signature_svg,
            signature_path=sig_path,
            pdf_path=pdf_filename,  # MRZ backend PDF filename
        )

        document_id = document_record.get("document_id")

        # Update session
        request.session["signed_document_id"] = document_id
        guest_data["signature_data"] = signature_svg
        guest_data["signature_type"] = "digital"
        guest_data["signature_format"] = "svg"
        guest_data["document_signed"] = True
        guest_data["signature_stored_in_db"] = True
        request.session["dw_registration_data"] = guest_data

        logger.info(f"Stored signed document in database: {document_id}")

        return JsonResponse(
            {
                "success": True,
                "document_id": document_id,
                "signature_path": sig_path,
                "pdf_filename": pdf_filename,
                "signature_stored": True,
                "stored_in_database": True,
                "database_record_id": document_record.get("id"),
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Document sign API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        session_id = data.get("session_id")
        guest_data = data.get("guest_data")
        reservation_id = data.get("reservation_id")
        room_number = data.get("room_number")

        if not guest_data:
            guest_data = request.session.get("dw_registration_data", {})

        # Submit to MRZ backend (required)
        try:
            doc_client = get_document_client()
            result = doc_client.submit_physical_signature(
                session_id=session_id, guest_data=guest_data, reservation_id=reservation_id, room_number=room_number
            )

            # Update session
            request.session["physical_submission_id"] = result.get("submission_id")
            guest_data["signature_type"] = "physical"
            guest_data["front_desk_notified"] = result.get("front_desk_notified", False)
            request.session["dw_registration_data"] = guest_data

            return JsonResponse(result)
        except MRZAPIError as e:
            logger.error(f"MRZ physical submission API failed: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Failed to submit physical signature request: {e}",
                    "error_code": "PHYSICAL_SUBMISSION_FAILED"
                },
                status=500
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Document physical submission API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        import requests

        dashboard_url = os.environ.get("DASHBOARD_API_URL", "http://dashboard:8001")
        api_token = os.environ.get("KIOSK_API_TOKEN", "")

        if not dashboard_url:
            return JsonResponse({"success": False, "error": "Dashboard API not configured"}, status=503)

        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required_fields = ["first_name", "last_name", "email", "room_number", "checkout_date"]
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

        # Parse checkout date
        checkout_str = data["checkout_date"]
        try:
            if "T" in checkout_str:
                checkout_date = datetime.datetime.fromisoformat(checkout_str.replace("Z", "+00:00"))
            else:
                checkout_date = datetime.datetime.strptime(checkout_str, "%Y-%m-%d")
                # Default checkout time is noon
                checkout_date = checkout_date.replace(hour=12, minute=0)
        except ValueError:
            return JsonResponse({"error": "Invalid checkout_date format. Use YYYY-MM-DD"}, status=400)

        # Create the guest account via Dashboard API
        headers = {"Authorization": f"Token {api_token}"} if api_token else {}
        response = requests.post(
            f"{dashboard_url}/api/guests/create/",
            json={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "room_number": data["room_number"],
                "checkout_date": checkout_date.isoformat(),
                "passport_number": data.get("passport_number"),
                "phone": data.get("phone"),
            },
            headers=headers,
            timeout=10,
        )

        if response.status_code == 201:
            result = response.json()
            return JsonResponse({"success": True, **result})
        else:
            return JsonResponse(
                {"success": False, "error": response.json().get("error", "Failed to create account")},
                status=response.status_code,
            )

    except requests.exceptions.RequestException as e:
        return JsonResponse({"success": False, "error": f"Dashboard API error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Internal error: {str(e)}"}, status=500)


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
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)

    try:
        import requests

        dashboard_url = os.environ.get("DASHBOARD_API_URL", "http://dashboard:8001")
        api_token = os.environ.get("KIOSK_API_TOKEN", "")

        if not dashboard_url:
            return JsonResponse({"success": False, "error": "Dashboard API not configured"}, status=503)

        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        username = data.get("username")
        if not username:
            return JsonResponse({"error": "Missing required field: username"}, status=400)

        # Deactivate the account via Dashboard API
        headers = {"Authorization": f"Token {api_token}"} if api_token else {}
        response = requests.post(
            f"{dashboard_url}/api/guests/deactivate/", json={"username": username}, headers=headers, timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({"success": True, "message": "Account deactivated"})
        else:
            return JsonResponse(
                {"success": False, "error": response.json().get("error", "Failed to deactivate account")},
                status=response.status_code,
            )

    except requests.exceptions.RequestException as e:
        return JsonResponse({"success": False, "error": f"Dashboard API error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Internal error: {str(e)}"}, status=500)


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
        guest_id = request.GET.get("guest_id")
        reservation_id = request.GET.get("reservation_id")

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
            doc_list.append(
                {
                    "id": doc.get("id"),
                    "document_id": doc.get("document_id"),
                    "guest_id": doc.get("guest_id"),
                    "reservation_id": doc.get("reservation_id"),
                    "signed_at": doc.get("signed_at"),
                    "status": doc.get("status"),
                    "signature_type": doc.get("signature_type"),
                    "has_pdf": bool(doc.get("pdf_path")),
                }
            )

        return JsonResponse({"success": True, "documents": doc_list, "count": len(doc_list)})

    except Exception as e:
        logger.error(f"List signed documents API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
            return JsonResponse({"success": False, "error": "Document not found"}, status=404)

        return JsonResponse({"success": True, "document": document})

    except Exception as e:
        logger.error(f"Get signed document API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
        guest_id = request.GET.get("guest_id")
        reservation_id = request.GET.get("reservation_id")

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
            img_list.append(
                {
                    "id": img.get("id"),
                    "passport_image_id": img.get("passport_image_id"),
                    "guest_id": img.get("guest_id"),
                    "reservation_id": img.get("reservation_id"),
                    "captured_at": img.get("captured_at"),
                    "status": img.get("status"),
                    "has_mrz_data": bool(img.get("mrz_data")),
                }
            )

        return JsonResponse({"success": True, "passport_images": img_list, "count": len(img_list)})

    except Exception as e:
        logger.error(f"List passport images API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
            if img.get("passport_image_id") == passport_image_id:
                passport_image = img
                break

        if not passport_image:
            return JsonResponse({"success": False, "error": "Passport image not found"}, status=404)

        # Remove base64 data for response (can be large)
        response_data = dict(passport_image)
        response_data.pop("image_data_base64", None)

        return JsonResponse({"success": True, "passport_image": response_data})

    except Exception as e:
        logger.error(f"Get passport image API error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
