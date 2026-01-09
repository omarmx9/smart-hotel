import threading
import os
import json
try:
    import requests
except Exception:
    requests = None

_lock = threading.Lock()
_counters = {
    'guest': 0,
    'reservation': 0,
    'task': 0,
    'face': 0,
}

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
    return guests.get(int(gid))


def get_or_create_guest(first_name, last_name, passport_number='', date_of_birth=None):
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
