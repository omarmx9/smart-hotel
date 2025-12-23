"""
Layer 1 — Capture
Responsibility: Camera initialization, frame capture, live preview
Output: Raw numpy.ndarray frame
"""
import cv2
import logging

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
    
    def initialize(self):
        """
        Initialize and configure the camera
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Attempting to initialize camera at index {self.camera_index}")
        
        if self.camera is not None and self.camera.isOpened():
            logger.debug("Camera already initialized")
            return True
        
        try:
            # Open camera with V4L2 backend
            self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                logger.error(f"Failed to open camera at index {self.camera_index}")
                return False
            
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
            logger.error(f"Error initializing camera: {e}")
            return False
    
    def get_frame(self):
        """
        Capture a single frame from the camera
        
        Returns:
            numpy.ndarray: Raw frame, or None if capture failed
        """
        if self.camera is None or not self.camera.isOpened():
            logger.warning("Camera not initialized when getting frame")
            return None
        
        ret, frame = self.camera.read()
        
        if not ret:
            logger.warning("Failed to read frame from camera")
            return None
        
        return frame
    
    def get_preview_frame(self, width=960, height=540):
        """
        Get resized frame for web preview
        
        Args:
            width: Preview width (default: 960)
            height: Preview height (default: 540)
        
        Returns:
            numpy.ndarray: Resized frame, or None if capture failed
        """
        frame = self.get_frame()
        
        if frame is not None:
            return cv2.resize(frame, (width, height))
        
        return None
    
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