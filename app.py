"""
Passport Scanner Web Application
Thin coordinator for layered document scanning system
"""
from flask import Flask, Response, jsonify, send_from_directory
import cv2
import time
import logging

# Import layers
from layer1_capture import Camera
from layer2_readjustment import DocumentProcessor
from layer3_mrz import MRZExtractor, ImageSaver

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


class ScannerCoordinator:
    """
    Coordinates the scanning pipeline across layers
    Thin wrapper that delegates to layer-specific components
    """
    
    def __init__(self, camera_index, tessdata_path, save_dir):
        logger.info("Initializing ScannerCoordinator")
        
        # Layer 1: Capture
        self.camera = Camera(camera_index=camera_index)
        
        # Layer 2: Image Readjustment with real-time detection
        self.processor = DocumentProcessor()
        
        # Layer 3: MRZ Extraction
        self.mrz_extractor = MRZExtractor(tessdata_path=tessdata_path)
        self.image_saver = ImageSaver(base_dir=save_dir)
        
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
        Layer 1 -> Layer 2 -> Layer 3
        
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
            
            # Prepare result data
            result_data = {
                "timestamp": timestamp,
                "image_path": filepath,
                "image_filename": filename,
                "status": "success",
                "mrz_data": mrz_data
            }
            
            # Save JSON
            self.image_saver.save_result_json(result_data, timestamp)
            
            logger.info("[Pipeline] Success!")
            logger.info("=" * 60)
            
            return {
                "success": True,
                "data": mrz_data,
                "image_path": filepath,
                "timestamp": timestamp
            }
            
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

# Configuration
CAMERA_INDEX = 2
TESSDATA_PATH = "models/"  # Directory containing mrz.traineddata
SAVE_DIR = "captured_passports"  # Base directory for outputs

scanner = ScannerCoordinator(
    camera_index=CAMERA_INDEX,
    tessdata_path=TESSDATA_PATH,
    save_dir=SAVE_DIR
)


# Flask Routes

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
                    logger.debug(f"Video stream: {frame_count} frames sent")
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
    """Initialize camera"""
    logger.info("Start camera request received")
    success = scanner.initialize_camera()
    logger.info(f"Camera start result: {success}")
    return jsonify({"success": success})


@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    """Stop camera"""
    logger.info("Stop camera request received")
    scanner.release_camera()
    return jsonify({"success": True})


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("PASSPORT SCANNER WEB SERVER")
    print("=" * 60)
    print("\n📁 Project Structure:")
    print("  layer1_capture/       - Camera handling")
    print("  layer2_readjustment/  - Document processing + Real-time Detection")
    print("  layer3_mrz/           - MRZ extraction")
    print("  web/                  - Frontend files")
    print("  models/               - OCR models (mrz.traineddata)")
    print("  captured_passports/")
    print("    ├── captured_images/  - Saved JPG files")
    print("    └── captured_json/    - Extraction results")
    print("\n🌐 Server Info:")
    print("  URL: http://localhost:5000")
    print("  Debug Mode: ON")
    print("  Logging Level: DEBUG")
    print("\n🎥 Camera:")
    print(f"  Device: /dev/video{CAMERA_INDEX}")
    print("  Resolution: 1920x1080")
    print("  Features: Real-time document detection overlay")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)