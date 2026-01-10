"""
MRZ Backend Microservice
Pure API service for MRZ extraction from uploaded images.

Provides REST API for:
- MRZ extraction from uploaded images (base64 or multipart)
- Document detection for auto-capture
- Document processing and perspective correction
- Document filling (PDF) - triggered after MRZ update

NOTE: This is a backend-only service. Camera capture is handled by the frontend
(browser-based using WebRTC/getUserMedia).
"""
from flask import Flask, Response, jsonify, send_from_directory, request
from flask_cors import CORS
import cv2
import numpy as np
import time
import logging
import os
import tempfile
import uuid
import base64
import json
import glob

# Import layers (no camera layer needed for backend)
from layer2_readjustment import DocumentProcessor
from layer3_mrz import MRZExtractor, ImageSaver
from layer4_document_filling import DocumentFiller, DocumentFillingError

# Import error handling
from error_handlers import (
    ScannerError, 
    MRZError,
    handle_error
)

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Enable CORS for cross-origin requests from kiosk service
CORS(app, origins=["*"])

# Configuration
TESSDATA_PATH = "models/"  # Directory containing mrz.traineddata
TEMPLATE_PATH = "templates/DWA_Registration_Card.pdf"  # Registration card template (PDF)

# New directory structure
CAPTURED_PASSPORTS_DIR = "Logs/captured_passports"
CAPTURED_IMAGES_DIR = os.path.join(CAPTURED_PASSPORTS_DIR, "captured_images")
CAPTURED_JSON_DIR = os.path.join(CAPTURED_PASSPORTS_DIR, "captured_json")
DOCUMENT_FILLING_DIR = "Logs/document_filling"
DOCUMENT_MRZ_DIR = os.path.join(DOCUMENT_FILLING_DIR, "document_mrz")
DOCUMENT_FILLED_DIR = os.path.join(DOCUMENT_FILLING_DIR, "document_filled")

# Ensure directories exist
for dir_path in [CAPTURED_IMAGES_DIR, CAPTURED_JSON_DIR, DOCUMENT_MRZ_DIR, DOCUMENT_FILLED_DIR]:
    os.makedirs(dir_path, exist_ok=True)


class MRZBackendService:
    """
    Backend service for MRZ extraction.
    Handles image processing and MRZ extraction from uploaded images.
    No camera hardware dependencies.
    
    Flow:
    1. /api/extract - Extract MRZ, save to captured_passports (no document filling yet)
    2. /api/mrz/update - Receive final/edited MRZ, trigger document filling
    """
    
    def __init__(self, tessdata_path, captured_images_dir, captured_json_dir, 
                 template_path, document_mrz_dir, document_filled_dir):
        logger.info("Initializing MRZBackendService")
        
        # Layer 2: Image Readjustment
        self.processor = DocumentProcessor()
        
        # Layer 3: MRZ Extraction
        self.mrz_extractor = MRZExtractor(tessdata_path=tessdata_path)
        self.image_saver = ImageSaver(base_dir=captured_images_dir)
        
        # Directory paths
        self.captured_images_dir = captured_images_dir
        self.captured_json_dir = captured_json_dir
        self.document_mrz_dir = document_mrz_dir
        self.document_filled_dir = document_filled_dir
        
        # Layer 4: Document Filling (PDF)
        try:
            self.document_filler = DocumentFiller(
                template_path=template_path,
                saved_documents_dir=document_filled_dir
            )
        except Exception as e:
            logger.warning(f"Document filler initialization failed: {e}")
            logger.warning("Layer 4 will be skipped in pipeline")
            self.document_filler = None
        
        logger.info("MRZBackendService initialized successfully")
    
    def process_image(self, image_data, filename="upload.jpg"):
        """
        Process an uploaded image and extract MRZ data.
        NOTE: Document filling is NOT done here. It waits for /api/mrz/update.
        
        Args:
            image_data: Raw image bytes or base64 encoded string
            filename: Original filename for logging
            
        Returns:
            dict: Extraction result with MRZ data and session_id
        """
        logger.info("=" * 60)
        logger.info(f"Processing uploaded image: {filename}")
        
        try:
            # Decode image
            if isinstance(image_data, str):
                # Base64 encoded
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data
            
            # Convert to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            raw_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if raw_frame is None:
                return {
                    "success": False,
                    "error": "Could not decode image",
                    "error_code": "INVALID_IMAGE"
                }
            
            logger.info(f"Image decoded - Shape: {raw_frame.shape}")
            
            # Generate session_id for tracking through the flow
            session_id = str(uuid.uuid4())
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # Layer 2: Process image
            logger.info("[Layer 2] Processing image...")
            processed_frame = self.processor.process(raw_frame)
            logger.info("[Layer 2] Processing complete")
            
            # Layer 3: Save image and extract MRZ
            logger.info("[Layer 3] Saving image...")
            
            # Save to captured_images with session_id in filename
            image_filename = f"{timestamp}_{session_id}.jpg"
            image_path = os.path.join(self.captured_images_dir, image_filename)
            cv2.imwrite(image_path, processed_frame)
            logger.info(f"[Layer 3] Image saved to: {image_path}")
            
            logger.info("[Layer 3] Extracting MRZ...")
            mrz_data = self.mrz_extractor.extract(image_path)
            
            # Prepare result data (initial extraction - before any edits)
            result_data = {
                "session_id": session_id,
                "timestamp": timestamp,
                "image_path": image_path,
                "image_filename": filename,
                "status": "extracted",  # Status: extracted (not yet finalized)
                "mrz_data": mrz_data,
                "is_edited": False
            }
            
            # Save initial JSON to captured_json
            json_filename = f"{timestamp}_{session_id}.json"
            json_path = os.path.join(self.captured_json_dir, json_filename)
            with open(json_path, 'w') as f:
                json.dump(result_data, f, indent=2)
            logger.info(f"[Layer 3] JSON saved to: {json_path}")
            
            logger.info("[Layer 3] MRZ extraction successful")
            logger.info("[Pipeline] Waiting for /api/mrz/update to finalize and fill document")
            logger.info("=" * 60)
            
            # NOTE: Document filling is NOT done here
            # It will be triggered by /api/mrz/update after user confirms/edits
            
            return {
                "success": True,
                "session_id": session_id,
                "data": mrz_data,
                "image_path": image_path,
                "timestamp": timestamp,
                "message": "MRZ extracted. Call /api/mrz/update to finalize and generate document."
            }
            
        except ScannerError as e:
            logger.info("[Pipeline] Failed with known error")
            logger.info("=" * 60)
            return handle_error(e)
            
        except Exception as e:
            logger.error(f"[Pipeline] Failed with unexpected error: {e}")
            logger.info("=" * 60)
            return handle_error(e)
    
    def _find_original_extraction(self, session_id: str) -> dict:
        """
        Find the original MRZ extraction data by session_id.
        Searches in captured_json directory for matching session.
        
        Args:
            session_id: The session ID to search for
            
        Returns:
            dict: Original extraction data, or None if not found
        """
        # Search for JSON files containing this session_id
        pattern = os.path.join(self.captured_json_dir, f"*_{session_id}.json")
        matching_files = glob.glob(pattern)
        
        if matching_files:
            try:
                with open(matching_files[0], 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load original extraction: {e}")
        
        return None
    
    def _compare_mrz_data(self, original_mrz: dict, new_guest_data: dict) -> dict:
        """
        Compare original MRZ extraction with new guest data to detect edits.
        
        Args:
            original_mrz: Original MRZ data from extraction
            new_guest_data: New guest data from update request
            
        Returns:
            dict: Comparison result with is_edited flag and changed_fields list
        """
        # Fields to compare (map MRZ field names to guest_data field names)
        field_mapping = {
            'surname': 'surname',
            'name': 'name',
            'first_name': 'first_name',
            'nationality': 'nationality',
            'passport_number': 'passport_number',
            'date_of_birth': 'date_of_birth',
            'sex': 'sex',
            'expiry_date': 'expiry_date',
            'country': 'country',
        }
        
        changed_fields = []
        
        for mrz_field, guest_field in field_mapping.items():
            original_value = original_mrz.get(mrz_field, '').strip().upper() if original_mrz.get(mrz_field) else ''
            new_value = new_guest_data.get(guest_field, '').strip().upper() if new_guest_data.get(guest_field) else ''
            
            if original_value != new_value:
                changed_fields.append({
                    'field': guest_field,
                    'original': original_mrz.get(mrz_field, ''),
                    'new': new_guest_data.get(guest_field, '')
                })
                logger.info(f"[MRZ Compare] Field '{guest_field}' changed: '{original_mrz.get(mrz_field, '')}' -> '{new_guest_data.get(guest_field, '')}'")
        
        is_edited = len(changed_fields) > 0
        
        return {
            'is_edited': is_edited,
            'changed_fields': changed_fields,
            'total_changes': len(changed_fields)
        }
    
    def update_mrz_and_fill_document(self, session_id: str, guest_data: dict) -> dict:
        """
        Update MRZ data (potentially edited) and trigger document filling.
        
        This method:
        1. Loads the original MRZ extraction from captured_json (using session_id)
        2. Compares original vs new guest_data to detect edits
        3. Logs whether data was edited and which fields changed
        4. Saves finalized data to document_mrz
        5. Triggers document filling (PDF generation)
        
        Args:
            session_id: Session ID from initial extraction
            guest_data: Final guest data (may be edited by user)
            
        Returns:
            dict: Result with document filling info and edit detection
        """
        logger.info("=" * 60)
        logger.info(f"[MRZ Update] Processing session: {session_id}")
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        try:
            # Step 1: Find original extraction data
            original_extraction = self._find_original_extraction(session_id)
            
            # Step 2: Compare to detect edits (don't trust frontend is_edited flag)
            comparison_result = {'is_edited': False, 'changed_fields': [], 'total_changes': 0}
            
            if original_extraction and original_extraction.get('mrz_data'):
                original_mrz = original_extraction['mrz_data']
                comparison_result = self._compare_mrz_data(original_mrz, guest_data)
                
                if comparison_result['is_edited']:
                    logger.info(f"[MRZ Update] ⚠️  DATA WAS EDITED - {comparison_result['total_changes']} field(s) changed")
                    for change in comparison_result['changed_fields']:
                        logger.info(f"[MRZ Update]   └─ {change['field']}: '{change['original']}' → '{change['new']}'")
                else:
                    logger.info("[MRZ Update] ✓ Data confirmed without changes")
            else:
                logger.warning(f"[MRZ Update] Original extraction not found for session {session_id}")
                logger.warning("[MRZ Update] Cannot determine if data was edited (treating as new)")
            
            is_edited = comparison_result['is_edited']
            
            # Step 3: Save finalized MRZ data to document_mrz directory
            mrz_filename = f"{timestamp}_{session_id}_final.json"
            mrz_path = os.path.join(self.document_mrz_dir, mrz_filename)
            
            finalized_data = {
                "session_id": session_id,
                "timestamp": timestamp,
                "status": "finalized",
                "is_edited": is_edited,
                "edit_details": comparison_result,  # Include what changed
                "guest_data": guest_data
            }
            
            with open(mrz_path, 'w') as f:
                json.dump(finalized_data, f, indent=2)
            logger.info(f"[Layer 3+] Finalized MRZ saved to: {mrz_path}")
            
            # Layer 4: Now fill the document with finalized data
            fill_result = None
            if self.document_filler is not None:
                try:
                    logger.info("[Layer 4] Filling registration card (PDF) with finalized data...")
                    # Convert guest_data format to MRZ format expected by DocumentFiller
                    mrz_format_data = _convert_guest_data_to_mrz(guest_data)
                    fill_result = self.document_filler.fill_registration_card(
                        mrz_format_data, 
                        f"{timestamp}_{session_id}"
                    )
                    logger.info(f"[Layer 4] ✓ Document saved: {fill_result['output_filename']}")
                except DocumentFillingError as e:
                    logger.warning(f"[Layer 4] Document filling failed: {e.message}")
                    return {
                        "success": False,
                        "error": f"Document filling failed: {e.message}",
                        "error_code": "DOCUMENT_FILLING_ERROR",
                        "session_id": session_id
                    }
                except Exception as e:
                    logger.error(f"[Layer 4] Unexpected error: {e}")
                    return {
                        "success": False,
                        "error": f"Document filling failed: {str(e)}",
                        "error_code": "DOCUMENT_FILLING_ERROR",
                        "session_id": session_id
                    }
            else:
                logger.warning("[Layer 4] Document filler not available, skipping")
            
            logger.info("[Pipeline] MRZ update and document filling complete!")
            logger.info("=" * 60)
            
            response = {
                "success": True,
                "session_id": session_id,
                "timestamp": timestamp,
                "guest_data": guest_data,
                "is_edited": is_edited,
                "edit_details": comparison_result,  # What fields were changed
                "mrz_saved_path": mrz_path
            }
            
            if fill_result:
                response["filled_document"] = {
                    "path": fill_result['output_path'],
                    "filename": fill_result['output_filename']
                }
            
            return response
            
        except Exception as e:
            logger.error(f"[MRZ Update] Failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UPDATE_FAILED",
                "session_id": session_id
            }
    
    def detect_document(self, image_data):
        """
        Detect if a document is present in the image (for auto-capture).
        
        Args:
            image_data: Raw image bytes or base64 encoded string
            
        Returns:
            dict: Detection result with confidence and bounding box
        """
        try:
            # Decode image
            if isinstance(image_data, str):
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data
            
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return {"detected": False, "error": "Could not decode image"}
            
            # Use processor to detect document
            overlay_frame, detection_info = self.processor.get_preview_with_overlay(frame)
            
            if detection_info and detection_info.get('detected'):
                return {
                    "detected": True,
                    "confidence": detection_info.get('area_percentage', 0),
                    "corners": detection_info.get('corners', []),
                    "ready_for_capture": detection_info.get('area_percentage', 0) > 15
                }
            
            return {"detected": False, "confidence": 0}
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return {"detected": False, "error": str(e)}


# Initialize backend service
logger.info("Starting MRZ Backend Service initialization")

service = MRZBackendService(
    tessdata_path=TESSDATA_PATH,
    captured_images_dir=CAPTURED_IMAGES_DIR,
    captured_json_dir=CAPTURED_JSON_DIR,
    template_path=TEMPLATE_PATH,
    document_mrz_dir=DOCUMENT_MRZ_DIR,
    document_filled_dir=DOCUMENT_FILLED_DIR
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for service discovery and load balancers"""
    return jsonify({
        "status": "healthy",
        "service": "mrz-backend",
        "version": "2.1.0",
        "capabilities": ["mrz_extraction", "document_detection", "document_filling"]
    })


@app.route("/api/extract", methods=["POST"])
def api_extract_from_image():
    """
    Extract MRZ data from an uploaded image.
    NOTE: This only extracts MRZ. Document filling happens after /api/mrz/update.
    
    Request (multipart/form-data):
        - 'image': Image file
        
    Request (application/json):
        - 'image': Base64 encoded image data
        - 'filename': Optional filename
        
    Response:
        {
            "success": true,
            "session_id": "uuid-here",
            "data": { ... MRZ fields ... },
            "timestamp": "20231231_120000",
            "message": "MRZ extracted. Call /api/mrz/update to finalize."
        }
    """
    logger.info("API extract request received")
    
    # Handle multipart form data
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({
                "success": False,
                "error": "Empty filename",
                "error_code": "EMPTY_FILENAME"
            }), 400
        
        image_data = image_file.read()
        filename = image_file.filename
        
    # Handle JSON with base64
    elif request.is_json:
        data = request.get_json()
        if 'image' not in data:
            return jsonify({
                "success": False,
                "error": "No image data provided",
                "error_code": "NO_IMAGE"
            }), 400
        
        image_data = data['image']
        filename = data.get('filename', 'upload.jpg')
        
    else:
        return jsonify({
            "success": False,
            "error": "No image file provided. Send multipart/form-data with 'image' field or JSON with base64 'image'",
            "error_code": "NO_IMAGE"
        }), 400
    
    result = service.process_image(image_data, filename)
    
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 422


@app.route("/api/detect", methods=["POST"])
def api_detect_document():
    """
    Detect if a document is present in the image.
    Used for auto-capture functionality in the frontend.
    
    Request (application/json):
        - 'image': Base64 encoded image data
        
    Response:
        {
            "detected": true,
            "confidence": 45.2,
            "ready_for_capture": true
        }
    """
    logger.debug("Document detection request received")
    
    if request.is_json:
        data = request.get_json()
        if 'image' not in data:
            return jsonify({"detected": False, "error": "No image data"})
        
        result = service.detect_document(data['image'])
        return jsonify(result)
    
    elif 'image' in request.files:
        image_file = request.files['image']
        image_data = image_file.read()
        result = service.detect_document(image_data)
        return jsonify(result)
    
    return jsonify({"detected": False, "error": "No image provided"})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Get service status and capabilities"""
    return jsonify({
        "success": True,
        "service": "mrz-backend",
        "version": "2.1.0",
        "document_filler_available": service.document_filler is not None,
        "tessdata_path": TESSDATA_PATH,
        "directories": {
            "captured_images": CAPTURED_IMAGES_DIR,
            "captured_json": CAPTURED_JSON_DIR,
            "document_mrz": DOCUMENT_MRZ_DIR,
            "document_filled": DOCUMENT_FILLED_DIR
        },
        "endpoints": {
            "health": "/health",
            "extract": "/api/extract",
            "detect": "/api/detect",
            "status": "/api/status",
            "mrz_update": "/api/mrz/update",
            "document_preview": "/api/document/preview"
        },
    })


# ============================================================================
# MRZ Update API Endpoint - Triggers Document Filling
# ============================================================================

@app.route("/api/mrz/update", methods=["POST"])
def api_mrz_update():
    """
    Update guest information after MRZ extraction and trigger document filling.
    This is called after user confirms or edits the extracted MRZ data.
    
    IMPORTANT: The backend automatically detects if data was edited by comparing
    the incoming guest_data with the original MRZ extraction (stored in captured_json).
    No need to send is_edited from frontend - it's determined server-side.
    
    Request (application/json):
        {
            "session_id": "abc123",  // Required: from /api/extract response
            "guest_data": {
                "surname": "DOE",
                "name": "JOHN",
                "nationality": "USA",
                "passport_number": "AB1234567",
                "date_of_birth": "1990-01-15",
                ...
            }
        }
    
    Response:
        {
            "success": true,
            "session_id": "abc123",
            "timestamp": "20260109_120000",
            "guest_data": { ... },
            "is_edited": true,  // Auto-detected by backend
            "edit_details": {
                "is_edited": true,
                "changed_fields": [
                    {"field": "surname", "original": "DOE", "new": "DOEE"}
                ],
                "total_changes": 1
            },
            "mrz_saved_path": "Logs/document_filling/document_mrz/...",
            "filled_document": {
                "path": "Logs/document_filling/document_filled/...",
                "filename": "..."
            }
        }
    """
    logger.info("MRZ update request received")
    
    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "JSON body required",
            "error_code": "INVALID_REQUEST"
        }), 400
    
    data = request.get_json()
    guest_data = data.get('guest_data', {})
    session_id = data.get('session_id')
    
    # Validate required fields
    if not session_id:
        return jsonify({
            "success": False,
            "error": "session_id is required (from /api/extract response)",
            "error_code": "MISSING_SESSION_ID"
        }), 400
    
    if not guest_data:
        return jsonify({
            "success": False,
            "error": "guest_data is required",
            "error_code": "MISSING_DATA"
        }), 400
    
    # Process the update - is_edited is auto-detected by comparing with original
    result = service.update_mrz_and_fill_document(
        session_id=session_id,
        guest_data=guest_data
    )
    
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 500


# ============================================================================
# Document Preview API Endpoint (for PDF generation only)
# ============================================================================

@app.route("/api/document/preview", methods=["POST"])
def api_document_preview():
    """
    Get document preview with current data (before signing).
    Returns HTML preview for the kiosk to display.
    NOTE: Signing and storage are handled by kiosk service.
    
    Request (application/json):
        {
            "session_id": "abc123",
            "guest_data": { ... }
        }
    
    Response:
        {
            "success": true,
            "preview_html": "<html>...</html>",
            "fields": { ... normalized fields ... }
        }
    """
    logger.info("Document preview request received")
    
    if not request.is_json:
        return jsonify({
            "success": False,
            "error": "JSON body required"
        }), 400
    
    data = request.get_json()
    guest_data = data.get('guest_data', {})
    session_id = data.get('session_id')
    
    try:
        accompanying = data.get('accompanying_guests', [])
        preview_html = _generate_document_preview_html(guest_data, accompanying, for_signing=True)
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "preview_html": preview_html,
            "fields": guest_data
        })
        
    except Exception as e:
        logger.error(f"Document preview failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/document/pdf/<session_id>", methods=["GET"])
def api_serve_pdf(session_id):
    """
    Serve a generated PDF file for preview.
    
    GET /api/document/pdf/<session_id>?file=<filename>
    
    Returns:
        PDF binary file
    """
    filename = request.args.get('file')
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    
    # Security: ensure filename is safe
    safe_filename = os.path.basename(filename)
    pdf_path = os.path.join(DOCUMENT_FILLED_DIR, safe_filename)
    
    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not found"}), 404
    
    try:
        return send_from_directory(
            DOCUMENT_FILLED_DIR, 
            safe_filename, 
            mimetype='application/pdf',
            as_attachment=False
        )
    except Exception as e:
        logger.error(f"Error serving PDF: {e}")
        return jsonify({"error": str(e)}), 500


def _convert_guest_data_to_mrz(guest_data: dict) -> dict:
    """
    Convert guest_data format to MRZ format expected by DocumentFiller.
    """
    return {
        'surname': guest_data.get('surname', ''),
        'given_name': guest_data.get('name', guest_data.get('first_name', '')),
        'nationality_code': guest_data.get('nationality_code', guest_data.get('nationality', '')[:3].upper() if guest_data.get('nationality') else ''),
        'document_number': guest_data.get('passport_number', ''),
        'birth_date': guest_data.get('date_of_birth', ''),
        'expiry_date': guest_data.get('expiry_date', ''),
        'issuer_code': guest_data.get('country', guest_data.get('issuing_country', ''))[:3].upper() if guest_data.get('country') or guest_data.get('issuing_country') else '',
    }


# ============================================================================
# Helper Functions for Document API
# ============================================================================

def _generate_document_preview_html(guest_data: dict, accompanying: list = None, for_signing: bool = False) -> str:
    """
    Generate HTML preview of the registration document.
    
    Args:
        guest_data: Dictionary with guest information
        accompanying: List of accompanying guest dicts
        for_signing: If True, includes legal disclaimer for signing
    
    Returns:
        str: HTML string for document preview
    """
    # TODO: Use proper template engine
    
    surname = guest_data.get('surname', '')
    name = guest_data.get('name', guest_data.get('first_name', ''))
    nationality = guest_data.get('nationality', '')
    passport_number = guest_data.get('passport_number', '')
    date_of_birth = guest_data.get('date_of_birth', '')
    profession = guest_data.get('profession', '')
    hometown = guest_data.get('hometown', '')
    country = guest_data.get('country', '')
    email = guest_data.get('email', '')
    phone = guest_data.get('phone', '')
    checkin = guest_data.get('checkin', '')
    checkout = guest_data.get('checkout', '')
    
    accompanying = accompanying or []
    
    html = f'''
    <div class="document-preview-content">
        <h3>DW Registration Card</h3>
        <div class="preview-section">
            <h4>Guest Information</h4>
            <div class="preview-row"><span class="label">Surname:</span> <span class="value">{surname}</span></div>
            <div class="preview-row"><span class="label">Name:</span> <span class="value">{name}</span></div>
            <div class="preview-row"><span class="label">Nationality:</span> <span class="value">{nationality}</span></div>
            <div class="preview-row"><span class="label">Passport No:</span> <span class="value">{passport_number}</span></div>
            <div class="preview-row"><span class="label">Date of Birth:</span> <span class="value">{date_of_birth}</span></div>
            <div class="preview-row"><span class="label">Country:</span> <span class="value">{country}</span></div>
        </div>
        <div class="preview-section">
            <h4>Contact Information</h4>
            <div class="preview-row"><span class="label">Email:</span> <span class="value">{email or "-"}</span></div>
            <div class="preview-row"><span class="label">Phone:</span> <span class="value">{phone or "-"}</span></div>
            <div class="preview-row"><span class="label">Profession:</span> <span class="value">{profession or "-"}</span></div>
            <div class="preview-row"><span class="label">Hometown:</span> <span class="value">{hometown or "-"}</span></div>
        </div>
        <div class="preview-section">
            <h4>Stay Information</h4>
            <div class="preview-row"><span class="label">Check-in:</span> <span class="value">{checkin}</span></div>
            <div class="preview-row"><span class="label">Check-out:</span> <span class="value">{checkout or "-"}</span></div>
        </div>
    '''
    
    if accompanying:
        html += '''
        <div class="preview-section">
            <h4>Accompanying Guests</h4>
        '''
        for i, guest in enumerate(accompanying, 1):
            html += f'''
            <div class="preview-row"><span class="label">Guest {i}:</span> <span class="value">{guest.get("name", "")} ({guest.get("nationality", "")}) - {guest.get("passport", "")}</span></div>
            '''
        html += '</div>'
    
    if for_signing:
        html += '''
        <div class="preview-section legal-notice">
            <p><strong>Legal Notice:</strong> By signing this document, I confirm that the information provided above is accurate and complete. 
            I agree to the hotel's terms and conditions.</p>
        </div>
        '''
    
    html += '</div>'
    
    return html


# ============================================================================
# Test Frontend (for development/testing only - will be removed)
# ============================================================================

@app.route('/')
def index():
    """Serve test frontend index.html"""
    logger.info("Serving test frontend index.html")
    return send_from_directory('web', 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve CSS and JS files for test frontend"""
    logger.debug(f"Serving static file: {filename}")
    return send_from_directory('web', filename)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("MRZ BACKEND MICROSERVICE v2.1.0")
    print("=" * 60)
    print("\n📁 Architecture:")
    print("  This is a BACKEND-ONLY service for MRZ extraction.")
    print("  Camera capture is handled by the frontend (browser-based).")
    print("  Document signing and storage handled by kiosk service.")
    print("\n📂 Directory Structure:")
    print(f"  Logs/captured_passports/")
    print(f"    ├── captured_images/  - Processed passport images")
    print(f"    └── captured_json/    - Initial MRZ extraction JSON")
    print(f"  Logs/document_filling/")
    print(f"    ├── document_mrz/     - Finalized MRZ data (after edit)")
    print(f"    └── document_filled/  - Filled PDF documents")
    print("\n📡 API Flow:")
    print("  1. POST /api/extract      - Extract MRZ (saves to captured_*)")
    print("  2. [User can edit MRZ in frontend]")
    print("  3. POST /api/mrz/update   - Finalize MRZ & fill document")
    print("\n📡 All Endpoints:")
    print("  GET  /health              - Health check")
    print("  GET  /api/status          - Service status")
    print("  POST /api/extract         - Extract MRZ from uploaded image")
    print("  POST /api/detect          - Detect document in image")
    print("  POST /api/mrz/update      - Update MRZ & trigger doc filling")
    print("  POST /api/document/preview- Get document preview HTML")
    print("\n🧪 Test Frontend:")
    print("  GET  /                    - Test frontend with browser camera")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
