"""
Passport Scanner Web Application / MRZ Microservice
Thin coordinator for layered document scanning system.

Provides REST API for:
- Camera capture and preview (local hardware)
- MRZ extraction from captured or uploaded images
- Document filling (PDF)
"""
from flask import Flask, Response, jsonify, send_from_directory, request
from flask_cors import CORS
import cv2
import time
import logging
import os
import tempfile
import uuid

# Import layers
from layer1_capture import Camera
from layer2_readjustment import DocumentProcessor
from layer3_mrz import MRZExtractor, ImageSaver
from layer4_document_filling import DocumentFiller, DocumentFillingError

# Import error handling
from error_handlers import (
    ScannerError, 
    CameraError, 
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
CAMERA_INDEX = int(os.environ.get('CAMERA_INDEX', 2))
TESSDATA_PATH = "models/"  # Directory containing mrz.traineddata
TEMPLATE_PATH = "templates/DWA_Registration_Card.pdf"  # Registration card template (PDF)
SAVE_DIR = "Logs/captured_passports"  # Base directory for outputs
SAVED_DOCUMENTS_DIR = "Logs/filled_documents"  # Directory for saved filled documents


class ScannerCoordinator:
    """
    Coordinates the scanning pipeline across layers
    Thin wrapper that delegates to layer-specific components
    """
    
    def __init__(self, camera_index, tessdata_path, save_dir, template_path, saved_documents_dir):
        logger.info("Initializing ScannerCoordinator")
        
        # Layer 1: Capture
        self.camera = Camera(camera_index=camera_index)
        
        # Layer 2: Image Readjustment with real-time detection
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
        
        logger.info("ScannerCoordinator initialized successfully")
    
    def initialize_camera(self):
        """
        Initialize camera (Layer 1)
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            return self.camera.initialize()
        except (CameraError, Exception) as e:
            logger.error(f"Camera initialization failed: {e}")
            return False
    
    def get_preview_frame(self):
        """
        Get preview frame for video streaming (Layer 1)
        
        Returns:
            numpy.ndarray or None: Frame if successful, None on error
        """
        try:
            return self.camera.get_preview_frame()
        except Exception as e:
            logger.debug(f"Failed to get preview frame: {e}")
            return None
    
    def get_preview_with_overlay(self):
        """
        Get preview frame with document detection overlay
        
        Returns:
            tuple: (frame, detection_info) or (None, None) on error
        """
        try:
            # Get raw frame from camera
            raw_frame = self.camera.get_preview_frame()
            if raw_frame is None:
                return None, None
            
            # Apply detection overlay
            overlay_frame, detection_info = self.processor.get_preview_with_overlay(raw_frame)
            return overlay_frame, detection_info
            
        except Exception as e:
            logger.debug(f"Failed to get overlay frame: {e}")
            return None, None
    
    def release_camera(self):
        """Release camera resources (Layer 1)"""
        self.camera.release()
    
    def capture_and_extract(self):
        """
        Execute full scanning pipeline with error handling:
        Layer 1 -> Layer 2 -> Layer 3 -> Layer 4
        
        Returns:
            dict: Success response or error response
        """
        logger.info("=" * 60)
        logger.info("Starting capture and extraction pipeline")
        
        try:
            # Layer 1: Capture raw frame
            logger.info("[Layer 1] Capturing frame...")
            raw_frame = self.camera.get_frame()
            logger.info(f"[Layer 1] Frame captured - Shape: {raw_frame.shape}")
            
            # Layer 2: Process image
            logger.info("[Layer 2] Processing frame...")
            processed_frame = self.processor.process(raw_frame)
            logger.info("[Layer 2] Processing complete")
            
            # Layer 3: Save and extract MRZ
            logger.info("[Layer 3] Saving image...")
            save_result = self.image_saver.save_image(processed_frame)
            
            timestamp = save_result["timestamp"]
            filepath = save_result["filepath"]
            filename = save_result["filename"]
            
            logger.info("[Layer 3] Extracting MRZ...")
            mrz_data = self.mrz_extractor.extract(filepath)
            
            # Layer 4: Fill document template (optional - continues on failure)
            fill_result = None
            if self.document_filler is not None:
                try:
                    logger.info("[Layer 4] Filling registration card (PDF)...")
                    fill_result = self.document_filler.fill_registration_card(mrz_data, timestamp)
                    logger.info(f"[Layer 4] ✓ Document saved: {fill_result['output_filename']}")
                except DocumentFillingError as e:
                    logger.warning(f"[Layer 4] Document filling failed: {e.message}")
                    logger.debug(f"  Details: {e.details}")
                    # Continue - document filling is not critical
                except Exception as e:
                    logger.error(f"[Layer 4] Unexpected error in document filling: {e}")
                    # Continue - document filling is not critical
            else:
                logger.info("[Layer 4] Skipped (document filler not available)")
            
            # Prepare result data
            result_data = {
                "timestamp": timestamp,
                "image_path": filepath,
                "image_filename": filename,
                "status": "success",
                "mrz_data": mrz_data,
                "filled_document": fill_result if fill_result else None
            }
            
            # Save JSON
            self.image_saver.save_result_json(result_data, timestamp)
            
            logger.info("[Pipeline] Success!")
            logger.info("=" * 60)
            
            response = {
                "success": True,
                "data": mrz_data,
                "image_path": filepath,
                "timestamp": timestamp
            }
            
            # Add filled document info if available
            if fill_result:
                response["filled_document"] = {
                    "path": fill_result['output_path'],
                    "filename": fill_result['output_filename']
                }
            
            return response
            
        except ScannerError as e:
            # Known scanner error - handle gracefully
            logger.info("[Pipeline] Failed with known error")
            logger.info("=" * 60)
            
            # Try to save error info if we have a timestamp
            if 'save_result' in locals():
                try:
                    error_data = {
                        "timestamp": save_result["timestamp"],
                        "image_path": save_result["filepath"],
                        "image_filename": save_result["filename"],
                        "status": "error",
                        "error": e.message,
                        "error_code": e.error_code,
                        "details": e.details
                    }
                    self.image_saver.save_result_json(error_data, save_result["timestamp"])
                except Exception as save_error:
                    logger.warning(f"Could not save error JSON: {save_error}")
            
            return handle_error(e)
            
        except Exception as e:
            # Unexpected error
            logger.error("[Pipeline] Failed with unexpected error")
            logger.info("=" * 60)
            return handle_error(e)


# Initialize scanner coordinator
logger.info("Starting application initialization")

scanner = ScannerCoordinator(
    camera_index=CAMERA_INDEX,
    tessdata_path=TESSDATA_PATH,
    save_dir=SAVE_DIR,
    template_path=TEMPLATE_PATH,
    saved_documents_dir=SAVED_DOCUMENTS_DIR
)


# ============================================================================
# Flask Routes - Web Interface
# ============================================================================

@app.route('/')
def index():
    """Serve index.html"""
    logger.info("Serving index.html")
    return send_from_directory('web', 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve CSS and JS files"""
    logger.debug(f"Serving static file: {filename}")
    return send_from_directory('web', filename)


@app.route('/video_feed')
def video_feed():
    """Video streaming route with real-time document detection overlay"""
    logger.info("Video feed with overlay requested")
    
    def generate():
        logger.info("Starting video stream generator with overlay")
        scanner.initialize_camera()
        
        frame_count = 0
        while True:
            # Get frame with detection overlay
            frame, detection_info = scanner.get_preview_with_overlay()
            
            if frame is not None:
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                
                frame_count += 1
                if frame_count % 30 == 0:
                    if detection_info and detection_info.get('detected'):
                        logger.debug(f"  Document detected: {detection_info['area_percentage']:.1f}% of frame")
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                time.sleep(0.1)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/detection_status', methods=['GET'])
def detection_status():
    """Get current document detection status (for potential UI updates)"""
    try:
        _, detection_info = scanner.get_preview_with_overlay()
        if detection_info:
            return jsonify({
                "success": True,
                "detection": detection_info
            })
        else:
            return jsonify({
                "success": False,
                "detection": {"detected": False}
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/capture', methods=['POST'])
def capture():
    """Capture and process passport"""
    logger.info("Capture request received from client")
    result = scanner.capture_and_extract()
    logger.info(f"Sending response to client: {result.get('success', False)}")
    return jsonify(result)


@app.route('/start_camera', methods=['POST'])
def start_camera():
    """Initialize camera with error details"""
    logger.info("Start camera request received")
    
    try:
        success = scanner.initialize_camera()
        logger.info(f"Camera start result: {success}")
        return jsonify({"success": success})
    except CameraError as e:
        return jsonify(handle_error(e))
    except Exception as e:
        return jsonify(handle_error(e))


@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    """Stop camera"""
    logger.info("Stop camera request received")
    scanner.release_camera()
    return jsonify({"success": True})


# ============================================================================
# API Endpoints for Microservice Communication
# ============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for service discovery and load balancers"""
    return jsonify({
        "status": "healthy",
        "service": "mrz-service",
        "version": "1.0.0"
    })


@app.route("/api/extract", methods=["POST"])
def api_extract_from_image():
    """
    Extract MRZ data from an uploaded image.
    
    This endpoint allows the kiosk service to send images for MRZ extraction
    without needing direct camera access.
    
    Request:
        - multipart/form-data with 'image' field containing the passport image
        
    Response:
        {
            "success": true,
            "data": { ... MRZ fields ... },
            "timestamp": "20231231_120000"
        }
    """
    logger.info("API extract request received")
    
    if 'image' not in request.files:
        return jsonify({
            "success": False,
            "error": "No image file provided",
            "error_code": "NO_IMAGE"
        }), 400
    
    image_file = request.files['image']
    
    if image_file.filename == '':
        return jsonify({
            "success": False,
            "error": "Empty filename",
            "error_code": "EMPTY_FILENAME"
        }), 400
    
    try:
        # Save uploaded file temporarily
        temp_dir = tempfile.gettempdir()
        unique_id = uuid.uuid4().hex[:8]
        temp_filename = f"upload_{unique_id}_{image_file.filename}"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        image_file.save(temp_path)
        logger.info(f"Saved uploaded image to: {temp_path}")
        
        # Read image with OpenCV
        raw_frame = cv2.imread(temp_path)
        if raw_frame is None:
            os.remove(temp_path)
            return jsonify({
                "success": False,
                "error": "Could not read image file",
                "error_code": "INVALID_IMAGE"
            }), 400
        
        # Layer 2: Process image
        logger.info("[Layer 2] Processing uploaded image...")
        processed_frame = scanner.processor.process(raw_frame)
        
        # Layer 3: Save and extract MRZ
        logger.info("[Layer 3] Saving processed image...")
        save_result = scanner.image_saver.save_image(processed_frame)
        
        timestamp = save_result["timestamp"]
        filepath = save_result["filepath"]
        
        logger.info("[Layer 3] Extracting MRZ...")
        mrz_data = scanner.mrz_extractor.extract(filepath)
        
        # Clean up temp file
        os.remove(temp_path)
        
        # Prepare response
        response = {
            "success": True,
            "data": mrz_data,
            "image_path": filepath,
            "timestamp": timestamp
        }
        
        # Optionally fill document
        if scanner.document_filler is not None:
            try:
                logger.info("[Layer 4] Filling registration card (PDF)...")
                fill_result = scanner.document_filler.fill_registration_card(
                    mrz_data, timestamp
                )
                response["filled_document"] = {
                    "path": fill_result["output_path"],
                    "filename": fill_result["output_filename"],
                }
            except Exception as e:
                logger.warning(f"[Layer 4] Document filling failed: {e}")
        
        logger.info("API extraction successful")
        return jsonify(response)
        
    except ScannerError as e:
        logger.error(f"Scanner error during API extraction: {e}")
        return jsonify(handle_error(e)), 422
        
    except Exception as e:
        logger.error(f"Unexpected error during API extraction: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "EXTRACTION_FAILED"
        }), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    """Get service status and capabilities"""
    return jsonify({
        "success": True,
        "camera_available": scanner.camera is not None,
        "document_filler_available": scanner.document_filler is not None,
        "tessdata_path": TESSDATA_PATH,
        "endpoints": {
            "health": "/health",
            "extract": "/api/extract",
            "capture": "/capture",
            "video_feed": "/video_feed",
            "detection_status": "/detection_status"
        }
    })


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("PASSPORT SCANNER WEB SERVER / MRZ MICROSERVICE")
    print("=" * 60)
    print("\n📁 Project Structure:")
    print("  layer1_capture/          - Camera handling")
    print("  layer2_readjustment/     - Document processing + Real-time Detection")
    print("  layer3_mrz/              - MRZ extraction")
    print("  layer4_document_filling/ - Auto-fill registration cards (PDF)")
    print("  web/                     - Frontend files")
    print("  models/                  - OCR models (mrz.traineddata)")
    print("  templates/               - Document templates (PDF)")
    print("  Logs/captured_passports/")
    print("    ├── captured_images/   - Saved JPG files")
    print("    └── captured_json/     - Extraction results")
    print("  Logs/filled_documents/   - Auto-filled registration cards")
    print("\n🌐 Server Info:")
    print("  URL: http://localhost:5000")
    print("  Debug Mode: ON")
    print("  Logging Level: DEBUG")
    print("\n📡 API Endpoints:")
    print("  GET  /health           - Health check")
    print("  GET  /api/status       - Service status")
    print("  POST /api/extract      - Extract MRZ from uploaded image")
    print("  POST /capture          - Capture from camera and extract")
    print("  GET  /video_feed       - MJPEG video stream")
    print("\n🎥 Camera:")
    print(f"  Device: /dev/video{CAMERA_INDEX}")
    print("  Resolution: 1920x1080")
    print("  Features: Real-time document detection overlay")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
