"""
Emulator module for kiosk reservation system.

This module provides an in-memory fallback for reservation/guest data when
the frontdesk PostgreSQL database is not available. When the frontdesk
database IS available, it queries that database for reservation and guest
information.

Priority:
1. Frontdesk PostgreSQL database (production)
2. MOCK_API_BASE remote API (testing)  
3. In-memory storage (development/fallback)
"""

import threading
import os
import json
import logging

logger = logging.getLogger(__name__)

try:
    import requests
except Exception:
    requests = None

# Import frontdesk database adapter (may not be available in all contexts)
try:
    from . import frontdesk_db
    _has_frontdesk = True
except ImportError:
    frontdesk_db = None
    _has_frontdesk = False

_lock = threading.Lock()
_counters = {
    'guest': 0,
    'reservation': 0,
    'task': 0,
    'face': 0,
}

# In-memory fallback storage (used when frontdesk DB not available)
guests = {}
reservations = {}
tasks = {}
faces = {}


def _next(kind):
    with _lock:
        _counters[kind] += 1
        return _counters[kind]


def create_guest(first_name, last_name, passport_number='', date_of_birth=None):
    gid = _next('guest')
    guest = {'id': gid, 'first_name': first_name, 'last_name': last_name, 'passport_number': passport_number, 'date_of_birth': date_of_birth}
    guests[gid] = guest
    return guest


def get_guest(gid):
    # Try frontdesk database first (production)
    if _has_frontdesk and frontdesk_db:
        guest = frontdesk_db.get_guest(gid)
        if guest:
            return guest
    
    # If a remote mock API is configured, try to fetch guest from it
    base = os.environ.get('MOCK_API_BASE')
    if base and requests:
        try:
            resp = requests.get(f"{base}/guests", timeout=2)
            data = resp.json()
            lst = data.get('guests') if isinstance(data, dict) and 'guests' in data else data
            for g in lst:
                if int(g.get('id')) == int(gid):
                    return g
        except Exception:
            pass
    
    # Fallback to in-memory storage
    return guests.get(int(gid))


def get_or_create_guest(first_name, last_name, passport_number='', date_of_birth=None):
    # Try frontdesk database first (production)
    if _has_frontdesk and frontdesk_db:
        guest = frontdesk_db.get_or_create_guest(
            first_name, last_name, passport_number, date_of_birth
        )
        if guest:
            return guest
    
    # Fallback to in-memory storage
    for g in guests.values():
        if g['first_name'] == first_name and g['last_name'] == last_name and (not passport_number or g.get('passport_number') == passport_number):
            return g
    return create_guest(first_name, last_name, passport_number, date_of_birth)


def create_reservation(reservation_number, guest, checkin, checkout, room_count=1, people_count=1):
    rid = _next('reservation')
    # guest may be dict or id
    if isinstance(guest, dict):
        guest_id = guest['id']
        guest_obj = guest
    else:
        guest_id = int(guest)
        guest_obj = guests.get(guest_id)
    res = {'id': rid, 'reservation_number': reservation_number, 'guest_id': guest_id, 'guest': guest_obj, 'checkin': str(checkin), 'checkout': str(checkout), 'room_count': room_count, 'people_count': people_count, 'keycards_submitted': False, 'paid': False, 'amount_due': 0}
    reservations[rid] = res
    return res


def submit_keycards(reservation):
    rid = reservation['id'] if isinstance(reservation, dict) else int(reservation)
    r = reservations.get(int(rid))
    if r:
        r['keycards_submitted'] = True
        return r
    return None


def finalize_payment(reservation, amount=0):
    rid = reservation['id'] if isinstance(reservation, dict) else int(reservation)
    r = reservations.get(int(rid))
    if r:
        # simplistic payment emulation: set amount_due to 0 and mark paid
        r['amount_due'] = max(0, (r.get('amount_due') or 0) - amount)
        r['paid'] = True
        return r
    return None


def get_reservation(rid):
    # Try frontdesk database first (production)
    if _has_frontdesk and frontdesk_db:
        res = frontdesk_db.get_reservation(rid)
        if res:
            return res
    
    base = os.environ.get('MOCK_API_BASE')
    if base and requests:
        try:
            resp = requests.get(f"{base}/reservations", timeout=2)
            data = resp.json()
            lst = data.get('reservations') if isinstance(data, dict) and 'reservations' in data else data
            for r in lst:
                if int(r.get('id')) == int(rid):
                    return r
        except Exception:
            pass
    return reservations.get(int(rid))


def get_reservation_by_number(resnum):
    # Try frontdesk database first (production)
    if _has_frontdesk and frontdesk_db:
        res = frontdesk_db.get_reservation_by_number(resnum)
        if res:
            return res
    
    base = os.environ.get('MOCK_API_BASE')
    if base and requests:
        try:
            resp = requests.get(f"{base}/reservations", timeout=2)
            data = resp.json()
            lst = data.get('reservations') if isinstance(data, dict) and 'reservations' in data else data
            for r in lst:
                if str(r.get('reservation_number')) == str(resnum):
                    return r
        except Exception:
            pass
    for r in reservations.values():
        if r['reservation_number'] == resnum:
            return r
    return None


def get_reservations_by_guest(guest):
    gid = guest['id'] if isinstance(guest, dict) else int(guest)
    
    # Try frontdesk database first (production)
    # Note: frontdesk_db uses name-based lookup, not ID, so we get the guest first
    if _has_frontdesk and frontdesk_db:
        guest_data = frontdesk_db.get_guest(gid)
        if guest_data:
            results = frontdesk_db.get_reservations_by_guest_name(
                guest_data.get('first_name', ''),
                guest_data.get('last_name', '')
            )
            if results:
                return results
    
    base = os.environ.get('MOCK_API_BASE')
    if base and requests:
        try:
            resp = requests.get(f"{base}/reservations", timeout=2)
            data = resp.json()
            lst = data.get('reservations') if isinstance(data, dict) and 'reservations' in data else data
            return [r for r in lst if int(r.get('guest_id')) == int(gid)]
        except Exception:
            pass
    return [r for r in reservations.values() if r.get('guest_id') == gid]


def get_reservations_by_guest_name(first_name, last_name):
    """
    Find reservations by guest name (for check-in lookup after passport scan).
    
    Args:
        first_name: Guest's first name
        last_name: Guest's last name
    
    Returns:
        List of matching reservations
    """
    # Try frontdesk database first (production)
    if _has_frontdesk and frontdesk_db:
        results = frontdesk_db.get_reservations_by_guest_name(first_name, last_name)
        if results:
            return results
    
    # Fallback to in-memory storage
    matches = []
    for r in reservations.values():
        guest = r.get('guest', {})
        if isinstance(guest, dict):
            if (guest.get('first_name', '').lower() == first_name.lower() and
                guest.get('last_name', '').lower() == last_name.lower()):
                matches.append(r)
    return matches


def get_todays_arrivals():
    """Get all reservations arriving today (for kiosk welcome screen)."""
    if _has_frontdesk and frontdesk_db:
        return frontdesk_db.get_todays_arrivals()
    return []


def create_task(status='processing'):
    tid = _next('task')
    tasks[tid] = {'id': tid, 'status': status, 'data': {}}
    return tasks[tid]


def set_task_data(tid, data):
    t = tasks.get(int(tid))
    if t:
        t['data'] = data
        t['status'] = 'done'


def get_task(tid):
    return tasks.get(int(tid))


def create_face_enrollment(guest, reservation, person_index, image_name=None):
    fid = _next('face')
    guest_id = guest['id'] if isinstance(guest, dict) else int(guest)
    reservation_id = reservation['id'] if isinstance(reservation, dict) else int(reservation)
    faces[fid] = {'id': fid, 'guest_id': guest_id, 'reservation_id': reservation_id, 'person_index': person_index, 'image': image_name}
    return faces[fid]


def count_face_enrollments_for_reservation(reservation):
    rid = reservation['id'] if isinstance(reservation, dict) else int(reservation)
    return sum(1 for f in faces.values() if f.get('reservation_id') == rid)


# ============================================================================
# DOCUMENT STORAGE (Signatures and Passport Images)
# ============================================================================

signed_documents = {}
passport_images = {}


def _next_document():
    with _lock:
        _counters.setdefault('document', 0)
        _counters['document'] += 1
        return _counters['document']


def _next_passport_image():
    with _lock:
        _counters.setdefault('passport_image', 0)
        _counters['passport_image'] += 1
        return _counters['passport_image']


def store_signed_document(guest_id, reservation_id, guest_data, signature_svg, signature_path=None, pdf_path=None):
    """
    Store a signed document with SVG signature in database.
    
    Args:
        guest_id: ID of the guest
        reservation_id: ID of the reservation
        guest_data: Dictionary with guest information
        signature_svg: SVG string of the signature
        signature_path: File path where SVG signature is stored
        pdf_path: File path where signed PDF is stored
    
    Returns:
        dict: The stored document record
    """
    import time
    doc_id = _next_document()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    document = {
        'id': doc_id,
        'document_id': f"doc_{doc_id}_{timestamp}",
        'guest_id': guest_id,
        'reservation_id': reservation_id,
        'guest_data': guest_data,
        'signature_svg': signature_svg,
        'signature_path': signature_path,
        'pdf_path': pdf_path,
        'signed_at': timestamp,
        'signature_type': 'digital',
        'status': 'signed'
    }
    
    signed_documents[doc_id] = document
    
    # Also store in frontdesk database if available
    if _has_frontdesk and frontdesk_db and pdf_path:
        try:
            frontdesk_db.store_guest_document(
                guest_id=guest_id,
                document_type='registration_form',
                file_path=pdf_path,
                notes=f'Signed at kiosk, reservation: {reservation_id}'
            )
        except Exception as e:
            logger.warning(f"Failed to store document in frontdesk DB: {e}")
    
    return document


def get_signed_document(doc_id):
    """Get a signed document by ID."""
    return signed_documents.get(int(doc_id))


def get_signed_document_by_document_id(document_id):
    """Get a signed document by document_id string."""
    for doc in signed_documents.values():
        if doc.get('document_id') == document_id:
            return doc
    return None


def get_signed_documents_by_reservation(reservation_id):
    """Get all signed documents for a reservation."""
    rid = int(reservation_id) if not isinstance(reservation_id, int) else reservation_id
    return [d for d in signed_documents.values() if d.get('reservation_id') == rid]


def get_signed_documents_by_guest(guest_id):
    """Get all signed documents for a guest."""
    gid = int(guest_id) if not isinstance(guest_id, int) else guest_id
    return [d for d in signed_documents.values() if d.get('guest_id') == gid]


def store_passport_image(guest_id, reservation_id, image_path, image_data_base64=None, mrz_data=None):
    """
    Store a passport image in database.
    
    Args:
        guest_id: ID of the guest
        reservation_id: ID of the reservation (optional)
        image_path: File path where passport image is stored
        image_data_base64: Base64 encoded image data (optional, for direct storage)
        mrz_data: Extracted MRZ data from the passport (optional)
    
    Returns:
        dict: The stored passport image record
    """
    import time
    img_id = _next_passport_image()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    passport_img = {
        'id': img_id,
        'passport_image_id': f"passport_{img_id}_{timestamp}",
        'guest_id': guest_id,
        'reservation_id': reservation_id,
        'image_path': image_path,
        'image_data_base64': image_data_base64,
        'mrz_data': mrz_data,
        'captured_at': timestamp,
        'status': 'stored'
    }
    
    passport_images[img_id] = passport_img
    
    # Also store in frontdesk database if available
    if _has_frontdesk and frontdesk_db and image_path:
        try:
            # Extract document details from MRZ if available
            metadata = {}
            if mrz_data:
                metadata['document_number'] = mrz_data.get('passport_number', '')
                metadata['issuing_country'] = mrz_data.get('nationality', '')
                if mrz_data.get('expiration_date'):
                    metadata['expiry_date'] = mrz_data.get('expiration_date')
            
            frontdesk_db.store_guest_document(
                guest_id=guest_id,
                document_type='passport',
                file_path=image_path,
                **metadata
            )
        except Exception as e:
            logger.warning(f"Failed to store passport image in frontdesk DB: {e}")
    
    return passport_img


def get_passport_image(img_id):
    """Get a passport image by ID."""
    return passport_images.get(int(img_id))


def get_passport_images_by_guest(guest_id):
    """Get all passport images for a guest."""
    gid = int(guest_id) if not isinstance(guest_id, int) else guest_id
    return [p for p in passport_images.values() if p.get('guest_id') == gid]


def get_passport_images_by_reservation(reservation_id):
    """Get all passport images for a reservation."""
    rid = int(reservation_id) if not isinstance(reservation_id, int) else reservation_id
    return [p for p in passport_images.values() if p.get('reservation_id') == rid]
