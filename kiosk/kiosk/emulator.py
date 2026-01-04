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
