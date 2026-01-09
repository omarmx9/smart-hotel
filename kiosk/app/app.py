"""
MRZ Backend Microservice
Pure API service for MRZ extraction from uploaded images.

Provides REST API for:
- MRZ extraction from uploaded images (base64 or multipart)
- Document detection for auto-capture
- Document processing and perspective correction
- Document filling (PDF)

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
SAVE_DIR = "Logs/captured_passports"  # Base directory for outputs
SAVED_DOCUMENTS_DIR = "Logs/filled_documents"  # Directory for saved filled documents


class MRZBackendService:
    """
    Backend service for MRZ extraction.
    Handles image processing and MRZ extraction from uploaded images.
    No camera hardware dependencies.
    """
    
    def __init__(self, tessdata_path, save_dir, template_path, saved_documents_dir):
        logger.info("Initializing MRZBackendService")
        
        # Layer 2: Image Readjustment
        self.processor = DocumentProcessor()
        
        # Layer 3: MRZ Extraction
        self.mrz_extractor = MRZExtractor(tessdata_path=tessdata_path)
        self.image_saver = ImageSaver(base_dir=save_dir)
        
        # Layer 4: Document Filling (PDF)
        try:
            self.document_filler = DocumentFiller(
                template_path=template_path,
                saved_documents_dir=saved_documents_dir
            )
        except Exception as e:
            logger.warning(f"Document filler initialization failed: {e}")
            logger.warning("Layer 4 will be skipped in pipeline")
            self.document_filler = None
        
        logger.info("MRZBackendService initialized successfully")
    
    def process_image(self, image_data, filename="upload.jpg"):
        """
        Process an uploaded image and extract MRZ data.
        
        Args:
            image_data: Raw image bytes or base64 encoded string
            filename: Original filename for logging
            
        Returns:
            dict: Extraction result with MRZ data
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
            
            # Layer 2: Process image
            logger.info("[Layer 2] Processing image...")
            processed_frame = self.processor.process(raw_frame)
            logger.info("[Layer 2] Processing complete")
            
            # Layer 3: Save and extract MRZ
            logger.info("[Layer 3] Saving image...")
            save_result = self.image_saver.save_image(processed_frame)
            
            timestamp = save_result["timestamp"]
            filepath = save_result["filepath"]
            
            logger.info("[Layer 3] Extracting MRZ...")
            mrz_data = self.mrz_extractor.extract(filepath)
            # Prepare result data
            result_data = {
                "timestamp": timestamp,
                "image_path": filepath,
                "image_filename": filename,
                "status": "success",
                "mrz_data": mrz_data,
            }
            
            # Save JSON (Layer 3)
            logger.info("[Pipeline] Saving result JSON...")
            self.image_saver.save_result_json(result_data, timestamp)

            logger.info("[Layer 3] MRZ extraction successful")

            # Note: Manual edit option and signature handling are implemented
            # in the Django kiosk frontend (passport_scan.html, views.py)

            # Layer 4: Fill document template (optional)
            fill_result = None
            if self.document_filler is not None:
                try:
                    logger.info("[Layer 4] Filling registration card (PDF)...")
                    fill_result = self.document_filler.fill_registration_card(mrz_data, timestamp)
                    logger.info(f"[Layer 4] ✓ Document saved: {fill_result['output_filename']}")
                except DocumentFillingError as e:
                    logger.warning(f"[Layer 4] Document filling failed: {e.message}")
                except Exception as e:
                    logger.error(f"[Layer 4] Unexpected error: {e}")
            



            
            logger.info("[Pipeline] Success!")
            logger.info("=" * 60)
            
            response = {
                "success": True,
                "data": mrz_data,
                "image_path": filepath,
                "timestamp": timestamp
            }
            
            if fill_result:
                response["filled_document"] = {
                    "path": fill_result['output_path'],
                    "filename": fill_result['output_filename']
                }
            
            return response
            
        except ScannerError as e:
            logger.info("[Pipeline] Failed with known error")
            logger.info("=" * 60)
            return handle_error(e)
            
        except Exception as e:
            logger.error(f"[Pipeline] Failed with unexpected error: {e}")
            logger.info("=" * 60)
            return handle_error(e)
    
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
    save_dir=SAVE_DIR,
    template_path=TEMPLATE_PATH,
    saved_documents_dir=SAVED_DOCUMENTS_DIR
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
        "version": "2.0.0",
        "capabilities": ["mrz_extraction", "document_detection", "document_filling"]
    })


@app.route("/api/extract", methods=["POST"])
def api_extract_from_image():
    """
    Extract MRZ data from an uploaded image.
    
    Request (multipart/form-data):
        - 'image': Image file
        
    Request (application/json):
        - 'image': Base64 encoded image data
        - 'filename': Optional filename
        
    Response:
        {
            "success": true,
            "data": { ... MRZ fields ... },
            "timestamp": "20231231_120000"
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
        "document_filler_available": service.document_filler is not None,
        "tessdata_path": TESSDATA_PATH,
        "endpoints": {
            "health": "/health",
            "extract": "/api/extract",
            "detect": "/api/detect",
            "status": "/api/status",
            "mrz/update": "/api/mrz/update"
        },
    })


# ============================================================================
# MRZ Update API Endpoint (renamed from document/update)
# ============================================================================

@app.route("/api/mrz/update", methods=["POST"])
def api_mrz_update():
    """
    Update guest information after MRZ extraction.
    This is a lightweight endpoint for processing MRZ data updates.
    Document signing and storage are handled by the kiosk service.
    
    Request (application/json):
        {
            "session_id": "abc123",
            "guest_data": {
                "surname": "DOE",
                "name": "JOHN",
                "nationality": "USA",
                "passport_number": "AB1234567",
                "date_of_birth": "1990-01-15"
            }
        }
    
    Response:
        {
            "success": true,
            "session_id": "abc123",
            "timestamp": "20260109_120000"
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
    session_id = data.get('session_id', str(uuid.uuid4()))
    
    if not guest_data:
        return jsonify({
            "success": False,
            "error": "guest_data is required",
            "error_code": "MISSING_DATA"
        }), 400
    
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "timestamp": timestamp,
            "guest_data": guest_data
        })
        
    except Exception as e:
        logger.error(f"MRZ update failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "UPDATE_FAILED"
        }), 500


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
    print("MRZ BACKEND MICROSERVICE")
    print("=" * 60)
    print("\n📁 Architecture:")
    print("  This is a BACKEND-ONLY service for MRZ extraction.")
    print("  Camera capture is handled by the frontend (browser-based).")
    print("  Document signing and storage handled by kiosk service.")
    print("\n📡 API Endpoints:")
    print("  GET  /health           - Health check")
    print("  GET  /api/status       - Service status")
    print("  POST /api/extract      - Extract MRZ from uploaded image")
    print("  POST /api/detect       - Detect document in image (for auto-capture)")
    print("  POST /api/mrz/update   - Update guest info after MRZ extraction")
    print("  POST /api/document/preview - Get document preview HTML")
    print("\n🧪 Test Frontend:")
    print("  GET  /                 - Test frontend with browser camera")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
