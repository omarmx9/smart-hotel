"""
Layer 1 — Capture
Responsibility: Camera initialization, frame capture, live preview
Output: Raw numpy.ndarray frame
"""
import cv2
import logging
import os

logger = logging.getLogger(__name__)


class Camera:
    """Handles USB camera initialization and frame capture"""
    
    def __init__(self, camera_index=3):
        """
        Initialize camera handler
        
        Args:
            camera_index: V4L2 device index (default: 3 for /dev/video3)
        """
        self.camera_index = camera_index
        self.camera = None
        logger.info(f"Camera handler created for device index {camera_index}")
    
    def _check_camera_exists(self):
        """Check if camera device exists"""
        device_path = f"/dev/video{self.camera_index}"
        if not os.path.exists(device_path):
            logger.error(f"Camera device not found: {device_path}")
            from error_handlers import CameraNotFoundError
            raise CameraNotFoundError(self.camera_index)
        return True
    
    def initialize(self):
        """
        Initialize and configure the camera
        
        Returns:
            bool: True if successful
            
        Raises:
            CameraNotFoundError: If camera device doesn't exist
            CameraInitError: If camera fails to initialize
        """
        logger.info(f"Attempting to initialize camera at index {self.camera_index}")
        
        if self.camera is not None and self.camera.isOpened():
            logger.debug("Camera already initialized")
            return True
        
        # Check if camera device exists
        self._check_camera_exists()
        
        try:
            # Open camera with V4L2 backend
            self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                logger.error(f"Failed to open camera at index {self.camera_index}")
                from error_handlers import CameraInitError
                raise CameraInitError(
                    self.camera_index, 
                    reason="Camera opened but isOpened() returned False"
                )
            
            # Configure camera settings
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            self.camera.set(cv2.CAP_PROP_FPS, 30)
            
            # Adjust exposure and brightness
            self.camera.set(cv2.CAP_PROP_BRIGHTNESS, 100)
            self.camera.set(cv2.CAP_PROP_CONTRAST, 130)
            self.camera.set(cv2.CAP_PROP_EXPOSURE, -7)
            
            # Log actual settings
            actual_width = self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"Camera initialized successfully")
            logger.debug(f"Resolution: {actual_width}x{actual_height}")
            logger.debug(f"FPS: {actual_fps}")
            
            return True
            
        except Exception as e:
            if "CameraInitError" in str(type(e).__name__) or "CameraNotFoundError" in str(type(e).__name__):
                raise  # Re-raise our custom errors
            
            logger.error(f"Error initializing camera: {e}")
            from error_handlers import CameraInitError
            raise CameraInitError(self.camera_index, reason=str(e))
    
    def get_frame(self):
        """
        Capture a single frame from the camera
        
        Returns:
            numpy.ndarray: Raw frame
            
        Raises:
            CameraNotInitializedError: If camera not initialized
            FrameCaptureError: If frame capture fails
        """
        if self.camera is None or not self.camera.isOpened():
            logger.warning("Camera not initialized when getting frame")
            from error_handlers import CameraNotInitializedError
            raise CameraNotInitializedError()
        
        ret, frame = self.camera.read()
        
        if not ret or frame is None:
            logger.warning("Failed to read frame from camera")
            from error_handlers import FrameCaptureError
            raise FrameCaptureError()
        
        return frame
    
    def get_preview_frame(self, width=960, height=540):
        """
        Get resized frame for web preview
        
        Args:
            width: Preview width (default: 960)
            height: Preview height (default: 540)
        
        Returns:
            numpy.ndarray: Resized frame
            
        Raises:
            CameraNotInitializedError: If camera not initialized
            FrameCaptureError: If frame capture fails
        """
        frame = self.get_frame()
        return cv2.resize(frame, (width, height))
    
    def is_opened(self):
        """Check if camera is currently open"""
        return self.camera is not None and self.camera.isOpened()
    
    def release(self):
        """Release camera resources"""
        logger.info("Releasing camera")
        
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            logger.info("Camera released successfully")