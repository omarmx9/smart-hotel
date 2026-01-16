"""
Layer 1 — Camera Handler
Low-level camera initialization and frame capture with V4L2.
Optimized for high-speed capture with minimal latency.
"""
import cv2
import logging
import os
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class CameraHandler:
    """
    Production-level USB camera handler with V4L2 backend.
    Optimized for high FPS and low latency capture.
    """
    
    # Default camera configuration
    DEFAULT_CONFIG = {
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'codec': 'MJPG',
        'buffer_size': 1,  # Minimal buffer for low latency
        'brightness': 100,
        'contrast': 130,
        'exposure': -7,
    }
    
    def __init__(
        self, 
        camera_index: int = 2,
        config: Optional[dict] = None
    ):
        """
        Initialize camera handler.
        
        Args:
            camera_index: V4L2 device index (e.g., 2 for /dev/video2)
            config: Optional configuration override
        """
        self.camera_index = camera_index
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.camera: Optional[cv2.VideoCapture] = None
        self._is_initialized = False
        
        # Actual resolution (may differ from requested)
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0
        
        logger.info(f"CameraHandler created for /dev/video{camera_index}")
    
    def _check_device_exists(self) -> bool:
        """Check if camera device file exists."""
        device_path = f"/dev/video{self.camera_index}"
        exists = os.path.exists(device_path)
        if not exists:
            logger.error(f"Camera device not found: {device_path}")
        return exists
    
    def initialize(self) -> bool:
        """
        Initialize and configure the camera.
        
        Returns:
            bool: True if successful
            
        Raises:
            CameraNotFoundError: If camera device doesn't exist
            CameraInitError: If camera fails to initialize
        """
        if self._is_initialized and self.camera is not None:
            logger.debug("Camera already initialized")
            return True
        
        # Check device exists
        if not self._check_device_exists():
            from error_handlers import CameraNotFoundError
            raise CameraNotFoundError(self.camera_index)
        
        logger.info(f"Initializing camera at /dev/video{self.camera_index}")
        
        try:
            # Open with V4L2 backend for Linux
            self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                from error_handlers import CameraInitError
                raise CameraInitError(
                    self.camera_index,
                    reason="Failed to open camera device"
                )
            
            # Configure camera for optimal performance
            self._configure_camera()
            
            # Read actual values
            self.actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
            
            self._is_initialized = True
            
            logger.info(f"Camera initialized: {self.actual_width}x{self.actual_height} @ {self.actual_fps}fps")
            return True
            
        except Exception as e:
            if "CameraInitError" in type(e).__name__ or "CameraNotFoundError" in type(e).__name__:
                raise
            
            logger.error(f"Camera initialization failed: {e}")
            from error_handlers import CameraInitError
            raise CameraInitError(self.camera_index, reason=str(e))
    
    def _configure_camera(self):
        """Apply camera configuration settings."""
        cfg = self.config
        
        # Set codec (MJPG for high FPS)
        fourcc = cv2.VideoWriter_fourcc(*cfg['codec'])
        self.camera.set(cv2.CAP_PROP_FOURCC, fourcc)
        
        # Set resolution
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, cfg['width'])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg['height'])
        
        # Set FPS
        self.camera.set(cv2.CAP_PROP_FPS, cfg['fps'])
        
        # Minimal buffer for low latency
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, cfg['buffer_size'])
        
        # Image adjustments
        self.camera.set(cv2.CAP_PROP_BRIGHTNESS, cfg['brightness'])
        self.camera.set(cv2.CAP_PROP_CONTRAST, cfg['contrast'])
        self.camera.set(cv2.CAP_PROP_EXPOSURE, cfg['exposure'])
        
        logger.debug(f"Camera configured: {cfg['width']}x{cfg['height']} @ {cfg['fps']}fps")
    
    def get_frame(self) -> np.ndarray:
        """
        Capture a single frame from the camera.
        
        Returns:
            numpy.ndarray: Raw BGR frame
            
        Raises:
            CameraNotInitializedError: If camera not initialized
            FrameCaptureError: If frame capture fails
        """
        if not self._is_initialized or self.camera is None:
            from error_handlers import CameraNotInitializedError
            raise CameraNotInitializedError()
        
        ret, frame = self.camera.read()
        
        if not ret or frame is None:
            from error_handlers import FrameCaptureError
            raise FrameCaptureError()
        
        return frame
    
    def get_resolution(self) -> Tuple[int, int]:
        """Get actual camera resolution."""
        return (self.actual_width, self.actual_height)
    
    def is_opened(self) -> bool:
        """Check if camera is currently open and initialized."""
        return self._is_initialized and self.camera is not None and self.camera.isOpened()
    
    def release(self):
        """Release camera resources."""
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self._is_initialized = False
        logger.info("Camera released")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False
