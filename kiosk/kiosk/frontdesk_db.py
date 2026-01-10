"""
Frontdesk Database Adapter

This module provides access to the frontdesk PostgreSQL database for
reading reservations, guests, and rooms. Documents uploaded via kiosk
are stored here and accessible to front desk staff.

The frontdesk database is READ-MOSTLY from kiosk perspective:
- Read: reservations, guests, rooms
- Write: guest documents, passport images
"""

import os
import logging
from datetime import date, datetime
from django.conf import settings

logger = logging.getLogger(__name__)


def _has_frontdesk_db():
    """Check if frontdesk database is configured."""
    return 'frontdesk' in getattr(settings, 'DATABASES', {})


def _get_connection():
    """Get a connection to the frontdesk database."""
    if not _has_frontdesk_db():
        return None
    
    from django.db import connections
    return connections['frontdesk']


# =============================================================================
# RESERVATION QUERIES
# =============================================================================

def get_reservation_by_number(reservation_number):
    """
    Get a reservation by its confirmation number.
    
    Returns dict with reservation data or None if not found.
    """
    if not _has_frontdesk_db():
        return None
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.id, r.confirmation_number, r.status,
                    r.check_in_date, r.check_out_date,
                    r.num_guests, r.total_amount, r.amount_paid,
                    r.special_requests, r.notes,
                    g.id as guest_id, g.first_name, g.last_name,
                    g.email, g.phone_number, g.passport_number,
                    g.nationality, g.date_of_birth,
                    rm.id as room_id, rm.room_number, rm.room_type, rm.floor
                FROM reservations_reservation r
                JOIN reservations_guest g ON r.guest_id = g.id
                LEFT JOIN reservations_room rm ON r.room_id = rm.id
                WHERE r.confirmation_number = %s
            """, [reservation_number])
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return _row_to_reservation(row, cursor.description)
    except Exception as e:
        logger.error(f"Error fetching reservation {reservation_number}: {e}")
        return None


def get_reservation(reservation_id):
    """Get a reservation by its ID."""
    if not _has_frontdesk_db():
        return None
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.id, r.confirmation_number, r.status,
                    r.check_in_date, r.check_out_date,
                    r.num_guests, r.total_amount, r.amount_paid,
                    r.special_requests, r.notes,
                    g.id as guest_id, g.first_name, g.last_name,
                    g.email, g.phone_number, g.passport_number,
                    g.nationality, g.date_of_birth,
                    rm.id as room_id, rm.room_number, rm.room_type, rm.floor
                FROM reservations_reservation r
                JOIN reservations_guest g ON r.guest_id = g.id
                LEFT JOIN reservations_room rm ON r.room_id = rm.id
                WHERE r.id = %s
            """, [reservation_id])
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return _row_to_reservation(row, cursor.description)
    except Exception as e:
        logger.error(f"Error fetching reservation ID {reservation_id}: {e}")
        return None


def get_reservations_by_guest_name(first_name, last_name):
    """
    Find reservations by guest name (for check-in lookup).
    Returns list of reservations.
    """
    if not _has_frontdesk_db():
        return []
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.id, r.confirmation_number, r.status,
                    r.check_in_date, r.check_out_date,
                    r.num_guests, r.total_amount, r.amount_paid,
                    r.special_requests, r.notes,
                    g.id as guest_id, g.first_name, g.last_name,
                    g.email, g.phone_number, g.passport_number,
                    g.nationality, g.date_of_birth,
                    rm.id as room_id, rm.room_number, rm.room_type, rm.floor
                FROM reservations_reservation r
                JOIN reservations_guest g ON r.guest_id = g.id
                LEFT JOIN reservations_room rm ON r.room_id = rm.id
                WHERE LOWER(g.first_name) = LOWER(%s) 
                  AND LOWER(g.last_name) = LOWER(%s)
                  AND r.status IN ('pending', 'confirmed')
                ORDER BY r.check_in_date
            """, [first_name, last_name])
            
            results = []
            for row in cursor.fetchall():
                results.append(_row_to_reservation(row, cursor.description))
            return results
    except Exception as e:
        logger.error(f"Error searching reservations for {first_name} {last_name}: {e}")
        return []


def get_todays_arrivals():
    """Get all reservations arriving today."""
    if not _has_frontdesk_db():
        return []
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            today = date.today()
            cursor.execute("""
                SELECT 
                    r.id, r.confirmation_number, r.status,
                    r.check_in_date, r.check_out_date,
                    r.num_guests, r.total_amount, r.amount_paid,
                    r.special_requests, r.notes,
                    g.id as guest_id, g.first_name, g.last_name,
                    g.email, g.phone_number, g.passport_number,
                    g.nationality, g.date_of_birth,
                    rm.id as room_id, rm.room_number, rm.room_type, rm.floor
                FROM reservations_reservation r
                JOIN reservations_guest g ON r.guest_id = g.id
                LEFT JOIN reservations_room rm ON r.room_id = rm.id
                WHERE r.check_in_date = %s
                  AND r.status IN ('pending', 'confirmed')
                ORDER BY g.last_name
            """, [today])
            
            results = []
            for row in cursor.fetchall():
                results.append(_row_to_reservation(row, cursor.description))
            return results
    except Exception as e:
        logger.error(f"Error fetching today's arrivals: {e}")
        return []


def _row_to_reservation(row, description):
    """Convert a database row to a reservation dict."""
    cols = [col[0] for col in description]
    data = dict(zip(cols, row))
    
    # Build structured response matching emulator format
    return {
        'id': data['id'],
        'reservation_number': data['confirmation_number'],
        'status': data['status'],
        'checkin': str(data['check_in_date']) if data['check_in_date'] else None,
        'checkout': str(data['check_out_date']) if data['check_out_date'] else None,
        'people_count': data['num_guests'] or 1,
        'room_count': 1,
        'amount_due': float(data['total_amount'] or 0) - float(data['amount_paid'] or 0),
        'paid': float(data['amount_paid'] or 0) >= float(data['total_amount'] or 0),
        'keycards_submitted': data['status'] == 'checked_in',
        'special_requests': data['special_requests'],
        'guest_id': data['guest_id'],
        'guest': {
            'id': data['guest_id'],
            'first_name': data['first_name'],
            'last_name': data['last_name'],
            'email': data['email'],
            'phone_number': data['phone_number'],
            'passport_number': data['passport_number'],
            'nationality': data['nationality'],
            'date_of_birth': str(data['date_of_birth']) if data['date_of_birth'] else None,
        },
        'room': {
            'id': data['room_id'],
            'room_number': data['room_number'],
            'room_type': data['room_type'],
            'floor': data['floor'],
        } if data['room_id'] else None,
    }


# =============================================================================
# GUEST QUERIES
# =============================================================================

def get_guest(guest_id):
    """Get a guest by ID."""
    if not _has_frontdesk_db():
        return None
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name, last_name, email, phone_number,
                       passport_number, nationality, date_of_birth,
                       address, city, country, postal_code, notes, vip
                FROM reservations_guest
                WHERE id = %s
            """, [guest_id])
            
            row = cursor.fetchone()
            if not row:
                return None
            
            cols = [col[0] for col in cursor.description]
            data = dict(zip(cols, row))
            data['date_of_birth'] = str(data['date_of_birth']) if data['date_of_birth'] else None
            return data
    except Exception as e:
        logger.error(f"Error fetching guest {guest_id}: {e}")
        return None


def get_or_create_guest(first_name, last_name, passport_number='', date_of_birth=None, **extra):
    """
    Get existing guest or create new one.
    Returns guest dict with 'id' field.
    """
    if not _has_frontdesk_db():
        return None
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            # Try to find existing guest by passport or name
            if passport_number:
                cursor.execute("""
                    SELECT id FROM reservations_guest
                    WHERE passport_number = %s
                    LIMIT 1
                """, [passport_number])
            else:
                cursor.execute("""
                    SELECT id FROM reservations_guest
                    WHERE LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s)
                    LIMIT 1
                """, [first_name, last_name])
            
            row = cursor.fetchone()
            if row:
                return get_guest(row[0])
            
            # Create new guest
            cursor.execute("""
                INSERT INTO reservations_guest 
                    (first_name, last_name, passport_number, date_of_birth,
                     email, phone_number, nationality, address, city, country,
                     postal_code, notes, vip, kiosk_guest_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, [
                first_name, last_name, passport_number, date_of_birth,
                extra.get('email', ''), extra.get('phone_number', ''),
                extra.get('nationality', ''), extra.get('address', ''),
                extra.get('city', ''), extra.get('country', ''),
                extra.get('postal_code', ''), extra.get('notes', ''),
                False, None
            ])
            
            guest_id = cursor.fetchone()[0]
            conn.commit()
            
            return get_guest(guest_id)
    except Exception as e:
        logger.error(f"Error creating guest {first_name} {last_name}: {e}")
        return None


def update_guest_kiosk_id(guest_id, kiosk_guest_id):
    """Link a frontdesk guest to their kiosk session."""
    if not _has_frontdesk_db():
        return False
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE reservations_guest
                SET kiosk_guest_id = %s, updated_at = NOW()
                WHERE id = %s
            """, [kiosk_guest_id, guest_id])
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating kiosk ID for guest {guest_id}: {e}")
        return False


# =============================================================================
# ROOM QUERIES
# =============================================================================

def get_available_rooms(check_in, check_out, room_type=None):
    """Get rooms available for the given date range."""
    if not _has_frontdesk_db():
        return []
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT rm.id, rm.room_number, rm.room_type, rm.floor,
                       rm.max_guests, rm.base_rate, rm.status
                FROM reservations_room rm
                WHERE rm.status = 'available'
                  AND rm.id NOT IN (
                      SELECT r.room_id FROM reservations_reservation r
                      WHERE r.room_id IS NOT NULL
                        AND r.status IN ('confirmed', 'checked_in')
                        AND r.check_in_date < %s
                        AND r.check_out_date > %s
                  )
            """
            params = [check_out, check_in]
            
            if room_type:
                query += " AND rm.room_type = %s"
                params.append(room_type)
            
            query += " ORDER BY rm.room_number"
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                cols = [col[0] for col in cursor.description]
                data = dict(zip(cols, row))
                data['base_rate'] = float(data['base_rate']) if data['base_rate'] else 0
                results.append(data)
            return results
    except Exception as e:
        logger.error(f"Error fetching available rooms: {e}")
        return []


# =============================================================================
# DOCUMENT STORAGE
# =============================================================================

def store_guest_document(guest_id, document_type, file_path, **metadata):
    """
    Store a document for a guest (passport image, signed form, etc.)
    
    Args:
        guest_id: ID of the guest in frontdesk database
        document_type: 'passport', 'id_card', 'visa', 'registration_form', 'other'
        file_path: Path to the file (relative to kiosk media)
        **metadata: document_number, issue_date, expiry_date, issuing_country, notes
    
    Returns:
        Document ID or None on error
    """
    if not _has_frontdesk_db():
        return None
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO documents_guestdocument
                    (guest_id, document_type, kiosk_file_url, source,
                     document_number, issue_date, expiry_date, issuing_country,
                     notes, verified, uploaded_at)
                VALUES (%s, %s, %s, 'kiosk', %s, %s, %s, %s, %s, FALSE, NOW())
                RETURNING id
            """, [
                guest_id, document_type, file_path,
                metadata.get('document_number', ''),
                metadata.get('issue_date'),
                metadata.get('expiry_date'),
                metadata.get('issuing_country', ''),
                metadata.get('notes', ''),
            ])
            
            doc_id = cursor.fetchone()[0]
            conn.commit()
            
            logger.info(f"Stored document {doc_id} for guest {guest_id}")
            return doc_id
    except Exception as e:
        logger.error(f"Error storing document for guest {guest_id}: {e}")
        return None


# =============================================================================
# RESERVATION UPDATES
# =============================================================================

def update_reservation_status(reservation_id, status):
    """Update reservation status (e.g., to 'checked_in')."""
    if not _has_frontdesk_db():
        return False
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            extra_fields = ""
            if status == 'checked_in':
                extra_fields = ", actual_check_in = NOW()"
            elif status == 'checked_out':
                extra_fields = ", actual_check_out = NOW()"
            
            cursor.execute(f"""
                UPDATE reservations_reservation
                SET status = %s, updated_at = NOW() {extra_fields}
                WHERE id = %s
            """, [status, reservation_id])
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating reservation {reservation_id} status: {e}")
        return False


def assign_room_to_reservation(reservation_id, room_id):
    """Assign a room to a reservation."""
    if not _has_frontdesk_db():
        return False
    
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE reservations_reservation
                SET room_id = %s, updated_at = NOW()
                WHERE id = %s
            """, [room_id, reservation_id])
            
            # Also mark room as occupied
            cursor.execute("""
                UPDATE reservations_room
                SET status = 'occupied'
                WHERE id = %s
            """, [room_id])
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error assigning room {room_id} to reservation {reservation_id}: {e}")
        return False
