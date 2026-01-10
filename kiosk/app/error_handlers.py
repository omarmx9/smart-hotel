"""
Error Handling System
Provides consistent error responses across all layers
"""
import logging

logger = logging.getLogger(__name__)


class ScannerError(Exception):
    """Base exception for scanner errors"""
    def __init__(self, message, error_code, details=None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert error to JSON-serializable dict"""
        return {
            "success": False,
            "error": self.message,
            "error_code": self.error_code,
            "details": self.details
        }


# Layer 1 Errors - Camera and Auto-Capture
class CameraError(ScannerError):
    """Camera-related errors"""
    pass


class CameraNotFoundError(CameraError):
    """Camera device not found"""
    def __init__(self, camera_index):
        super().__init__(
            message=f"Camera not found at /dev/video{camera_index}",
            error_code="CAMERA_NOT_FOUND",
            details={
                "camera_index": camera_index,
                "suggestion": "Check camera connection and device index"
            }
        )


class CameraInitError(CameraError):
    """Camera initialization failed"""
    def __init__(self, camera_index, reason=None):
        super().__init__(
            message=f"Failed to initialize camera at /dev/video{camera_index}",
            error_code="CAMERA_INIT_FAILED",
            details={
                "camera_index": camera_index,
                "reason": reason,
                "suggestion": "Check camera permissions and ensure no other app is using it"
            }
        )


class CameraNotInitializedError(CameraError):
    """Attempting to use camera before initialization"""
    def __init__(self):
        super().__init__(
            message="Camera not initialized. Please start the camera first.",
            error_code="CAMERA_NOT_INITIALIZED",
            details={
                "suggestion": "Call /api/capture/start endpoint first"
            }
        )


class FrameCaptureError(CameraError):
    """Failed to capture frame"""
    def __init__(self):
        super().__init__(
            message="Failed to capture frame from camera",
            error_code="FRAME_CAPTURE_FAILED",
            details={
                "suggestion": "Check camera connection or restart the camera"
            }
        )


class AutoCaptureError(ScannerError):
    """Auto-capture related errors"""
    pass


class ModelNotFoundError(AutoCaptureError):
    """YOLO model file not found"""
    def __init__(self, model_path):
        super().__init__(
            message=f"Document detection model not found: {model_path}",
            error_code="MODEL_NOT_FOUND",
            details={
                "model_path": model_path,
                "suggestion": "Ensure the YOLO model file exists in models/ directory"
            }
        )


class CaptureTimeoutError(AutoCaptureError):
    """Capture timed out waiting for stable document"""
    def __init__(self, timeout_seconds):
        super().__init__(
            message=f"Auto-capture timed out after {timeout_seconds}s waiting for stable document",
            error_code="CAPTURE_TIMEOUT",
            details={
                "timeout": timeout_seconds,
                "suggestion": "Hold the document steady within the frame"
            }
        )


class QualityTooLowError(AutoCaptureError):
    """Image quality below acceptable threshold"""
    def __init__(self, quality_score, min_required, reason=None):
        super().__init__(
            message=f"Image quality too low: {quality_score:.1f} (minimum: {min_required})",
            error_code="QUALITY_TOO_LOW",
            details={
                "quality_score": quality_score,
                "min_required": min_required,
                "reason": reason,
                "suggestion": "Improve lighting, reduce motion blur, or hold steady"
            }
        )


# Layer 2 Errors - Image Processing
class ProcessingError(ScannerError):
    """Image processing errors"""
    pass


class DocumentNotDetectedError(ProcessingError):
    """Document not detected in frame"""
    def __init__(self):
        super().__init__(
            message="No document detected in the image",
            error_code="DOCUMENT_NOT_DETECTED",
            details={
                "suggestion": "Ensure document is fully visible and well-lit"
            }
        )


# Layer 3 Errors - MRZ Extraction
class MRZError(ScannerError):
    """MRZ extraction errors"""
    pass


class MRZNotFoundError(MRZError):
    """No MRZ data found in image"""
    def __init__(self):
        super().__init__(
            message="No MRZ data found in the image",
            error_code="MRZ_NOT_FOUND",
            details={
                "suggestion": "Ensure passport MRZ area is clearly visible and in focus"
            }
        )


class MRZExtractionError(MRZError):
    """MRZ extraction process failed"""
    def __init__(self, reason):
        super().__init__(
            message=f"MRZ extraction failed: {reason}",
            error_code="MRZ_EXTRACTION_FAILED",
            details={
                "reason": str(reason),
                "suggestion": "Check image quality and lighting"
            }
        )


# Layer 4 Errors - Document Filling
class DocumentFillingError(ScannerError):
    """Document filling errors"""
    pass


class TemplateNotFoundError(DocumentFillingError):
    """Template file not found"""
    def __init__(self, template_path):
        super().__init__(
            message=f"Template file not found: {template_path}",
            error_code="TEMPLATE_NOT_FOUND",
            details={
                "template_path": template_path,
                "suggestion": "Check that the template file exists in the templates/ directory"
            }
        )


class TemplateSaveError(DocumentFillingError):
    """Failed to save filled document"""
    def __init__(self, output_path, reason):
        super().__init__(
            message=f"Failed to save filled document to {output_path}",
            error_code="TEMPLATE_SAVE_FAILED",
            details={
                "output_path": output_path,
                "reason": str(reason),
                "suggestion": "Check disk space and write permissions in filled_documents/"
            }
        )


# WebRTC Stream Errors
class StreamError(ScannerError):
    """WebRTC stream related errors"""
    pass


class InvalidSessionError(StreamError):
    """Invalid or expired stream session"""
    def __init__(self, session_id):
        super().__init__(
            message=f"Invalid or expired stream session: {session_id}",
            error_code="INVALID_SESSION",
            details={
                "session_id": session_id,
                "suggestion": "Create a new session with POST /api/stream/session"
            }
        )


class FrameDecodeError(StreamError):
    """Failed to decode frame from stream"""
    def __init__(self, reason=None):
        super().__init__(
            message="Failed to decode frame from stream",
            error_code="FRAME_DECODE_FAILED",
            details={
                "reason": reason,
                "suggestion": "Ensure frame is properly base64 encoded JPEG/PNG"
            }
        )


class NoStableFrameError(StreamError):
    """No stable frame available for capture"""
    def __init__(self):
        super().__init__(
            message="No stable frame captured yet",
            error_code="NO_STABLE_FRAME",
            details={
                "suggestion": "Continue sending frames until ready_for_capture is true"
            }
        )


class SaveError(ScannerError):
    """File saving errors"""
    pass


class ImageSaveError(SaveError):
    """Failed to save image"""
    def __init__(self, filepath, reason):
        super().__init__(
            message=f"Failed to save image to {filepath}",
            error_code="IMAGE_SAVE_FAILED",
            details={
                "filepath": filepath,
                "reason": str(reason),
                "suggestion": "Check disk space and write permissions"
            }
        )


class JSONSaveError(SaveError):
    """Failed to save JSON"""
    def __init__(self, filepath, reason):
        super().__init__(
            message=f"Failed to save JSON to {filepath}",
            error_code="JSON_SAVE_FAILED",
            details={
                "filepath": filepath,
                "reason": str(reason),
                "suggestion": "Check disk space and write permissions"
            }
        )


# Error response helpers
def handle_error(error, log_message=None):
    """
    Handle error consistently across the application
    
    Args:
        error: Exception that occurred
        log_message: Optional custom log message
    
    Returns:
        dict: Error response for JSON serialization
    """
    if isinstance(error, ScannerError):
        # Known scanner error
        logger.error(f"{error.error_code}: {error.message}")
        if error.details:
            logger.debug(f"Error details: {error.details}")
        return error.to_dict()
    else:
        # Unexpected error
        logger.error(f"Unexpected error: {error}")
        logger.exception("Full traceback:")
        return {
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "UNEXPECTED_ERROR",
            "details": {
                "error_type": type(error).__name__,
                "error_message": str(error)
            }
        }