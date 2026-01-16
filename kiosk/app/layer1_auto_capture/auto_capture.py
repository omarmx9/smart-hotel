"""
Layer 1 — Auto-Capture Engine
Production-level document auto-capture with YOLO model.
Captures only the single best-quality image per session.

Features:
- YOLO-based document corner detection
- Virtual padding for better detection near edges
- Stability tracking (document must be still)
- Burst capture with quality assessment
- Returns only the best frame from burst
- Perspective correction to flat document
"""
import cv2
import numpy as np
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .camera import CameraHandler
from .quality import QualityAssessor, QualityMetrics

logger = logging.getLogger(__name__)


@dataclass
class CaptureConfig:
    """Configuration for auto-capture engine."""
    # Camera settings
    camera_index: int = 2
    camera_width: int = 1920
    camera_height: int = 1080
    
    # Display settings (for preview)
    display_width: int = 1280
    display_height: int = 720
    
    # Detection settings
    model_path: str = "models/document_detector.pt"
    confidence_threshold: float = 0.5
    
    # Stability settings
    stability_frames: int = 8         # Frames document must be stable
    stability_tolerance: float = 10.0  # Max corner movement (pixels)
    frame_margin: int = 50            # Margin from frame edge
    
    # Virtual padding for better edge detection
    use_virtual_padding: bool = True
    virtual_padding_ratio: float = 0.15
    
    # Burst capture settings
    burst_frames: int = 5             # Number of frames to capture in burst
    burst_delay_ms: int = 50          # Delay between burst frames
    min_quality_score: float = 40.0   # Minimum acceptable quality
    
    # Output settings
    output_dir: str = "Logs/auto_capture"


@dataclass
class CaptureResult:
    """Result of a capture session."""
    success: bool
    image: Optional[np.ndarray] = None
    corners: Optional[List[Tuple[float, float]]] = None
    quality_metrics: Optional[QualityMetrics] = None
    timestamp: str = ""
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        result = {
            'success': self.success,
            'timestamp': self.timestamp,
            'error': self.error,
            'metadata': self.metadata
        }
        if self.quality_metrics:
            result['quality'] = self.quality_metrics.to_dict()
        if self.corners:
            result['corners'] = self.corners
        return result


class AutoCaptureEngine:
    """
    Production-level document auto-capture engine.
    
    Uses YOLO model for document corner detection, tracks stability,
    performs burst capture, and returns only the best quality image.
    """
    
    def __init__(self, config: Optional[CaptureConfig] = None):
        """
        Initialize auto-capture engine.
        
        Args:
            config: Capture configuration (uses defaults if not provided)
        """
        self.config = config or CaptureConfig()
        
        # Components
        self.camera: Optional[CameraHandler] = None
        self.quality_assessor = QualityAssessor()
        self.model = None
        self._model_loaded = False
        
        # State tracking
        self._prev_corners: Optional[List[Tuple[float, float]]] = None
        self._stable_count: int = 0
        self._is_running: bool = False
        
        # Ensure output directory exists
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info("AutoCaptureEngine initialized")
        logger.debug(f"Config: {self.config}")
    
    def load_model(self) -> bool:
        """
        Load YOLO model for document detection.
        
        Returns:
            bool: True if model loaded successfully
        """
        if self._model_loaded:
            return True
        
        model_path = Path(self.config.model_path)
        
        if not model_path.exists():
            logger.error(f"Model not found: {model_path}")
            return False
        
        try:
            from ultralytics import YOLO
            
            logger.info(f"Loading YOLO model from {model_path}")
            self.model = YOLO(str(model_path))
            self.model.fuse()  # Optimize for inference
            self._model_loaded = True
            logger.info("YOLO model loaded and fused")
            return True
            
        except ImportError:
            logger.error("ultralytics package not installed. Run: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def initialize(self) -> bool:
        """
        Initialize camera and model.
        
        Returns:
            bool: True if initialization successful
        """
        # Initialize camera
        self.camera = CameraHandler(
            camera_index=self.config.camera_index,
            config={
                'width': self.config.camera_width,
                'height': self.config.camera_height,
            }
        )
        
        try:
            self.camera.initialize()
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return False
        
        # Load model
        if not self.load_model():
            logger.error("Model loading failed")
            self.camera.release()
            return False
        
        self._reset_state()
        logger.info("AutoCaptureEngine fully initialized")
        return True
    
    def _reset_state(self):
        """Reset tracking state."""
        self._prev_corners = None
        self._stable_count = 0
    
    def release(self):
        """Release all resources."""
        if self.camera:
            self.camera.release()
        self._is_running = False
        self._reset_state()
        logger.info("AutoCaptureEngine released")
    
    def _add_virtual_padding(self, frame: np.ndarray) -> Tuple[np.ndarray, int, int]:
        """
        Add virtual padding around frame for better edge detection.
        
        Args:
            frame: Input frame
            
        Returns:
            Tuple of (padded_frame, padding_x, padding_y)
        """
        h, w = frame.shape[:2]
        ratio = self.config.virtual_padding_ratio
        px, py = int(w * ratio), int(h * ratio)
        
        # Create padded frame with neutral gray
        padded = np.full((h + 2*py, w + 2*px, 3), 128, dtype=np.uint8)
        padded[py:py+h, px:px+w] = frame
        
        return padded, px, py
    
    def _detect_corners(self, frame: np.ndarray) -> Tuple[Optional[List[Tuple[float, float]]], float]:
        """
        Detect document corners using YOLO model.
        
        Args:
            frame: Input frame (BGR)
            
        Returns:
            Tuple of (corners, confidence) or (None, 0) if not detected
        """
        if not self._model_loaded or self.model is None:
            return None, 0.0
        
        # Apply virtual padding if enabled
        if self.config.use_virtual_padding:
            padded, px, py = self._add_virtual_padding(frame)
            inference_frame = padded
        else:
            px, py = 0, 0
            inference_frame = frame
        
        # Run inference
        results = self.model(
            inference_frame,
            conf=self.config.confidence_threshold,
            verbose=False,
            device=0  # GPU
        )
        
        # Extract corners from keypoints
        for r in results:
            if r.keypoints is not None and len(r.keypoints) > 0:
                kpts = r.keypoints.data[0].cpu().numpy()
                
                # Filter visible keypoints and adjust for padding
                visible = []
                for x, y, v in kpts:
                    if v > 0.5:  # Visibility threshold
                        visible.append((float(x) - px, float(y) - py))
                
                if len(visible) == 4:
                    confidence = float(r.boxes.conf[0].item())
                    return visible, confidence
        
        return None, 0.0
    
    def _order_corners(self, corners: List[Tuple[float, float]]) -> np.ndarray:
        """
        Order corners: top-left, top-right, bottom-right, bottom-left.
        """
        c = np.array(corners, dtype='float32')
        
        # Sort by y-coordinate
        c = c[c[:, 1].argsort()]
        
        # Top two and bottom two
        top = c[:2][c[:2, 0].argsort()]
        bottom = c[2:][c[2:, 0].argsort()]
        
        return np.array([top[0], top[1], bottom[1], bottom[0]], dtype='float32')
    
    def _corners_stable(self, current: List[Tuple[float, float]]) -> bool:
        """Check if corners are stable compared to previous frame."""
        if self._prev_corners is None:
            return False
        
        curr_arr = np.array(current)
        prev_arr = np.array(self._prev_corners)
        
        # Calculate maximum corner movement
        distances = np.linalg.norm(curr_arr - prev_arr, axis=1)
        max_movement = np.max(distances)
        
        return max_movement < self.config.stability_tolerance
    
    def _corners_in_frame(self, corners: List[Tuple[float, float]], frame_shape: Tuple[int, int]) -> bool:
        """Check if all corners are within acceptable frame margins."""
        h, w = frame_shape[:2]
        margin = self.config.frame_margin
        
        for x, y in corners:
            if x < margin or x > w - margin or y < margin or y > h - margin:
                return False
        return True
    
    def _perspective_crop(self, image: np.ndarray, corners: List[Tuple[float, float]]) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Apply perspective transform to extract flat document.
        
        Args:
            image: Source image
            corners: Document corners
            
        Returns:
            Tuple of (warped_image, (width, height))
        """
        src = self._order_corners(corners)
        
        # Calculate output dimensions based on corner positions
        width = int(max(
            np.linalg.norm(src[1] - src[0]),
            np.linalg.norm(src[2] - src[3])
        ))
        height = int(max(
            np.linalg.norm(src[3] - src[0]),
            np.linalg.norm(src[2] - src[1])
        ))
        
        # Ensure minimum size
        width = max(width, 400)
        height = max(height, 300)
        
        # Destination points for flat rectangle
        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype='float32')
        
        # Compute and apply perspective transform
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(image, M, (width, height))
        
        return warped, (width, height)
    
    def _burst_capture(self, initial_frame: np.ndarray, corners: List[Tuple[float, float]]) -> Tuple[Optional[np.ndarray], Optional[QualityMetrics]]:
        """
        Perform burst capture and select best quality frame.
        
        Args:
            initial_frame: First captured frame
            corners: Detected corners for perspective crop
            
        Returns:
            Tuple of (best_image, quality_metrics) or (None, None) if failed
        """
        cfg = self.config
        
        # Collect burst frames
        warped_frames = []
        
        # Add initial frame
        warped, _ = self._perspective_crop(initial_frame, corners)
        warped_frames.append(warped)
        
        # Capture additional burst frames
        for i in range(cfg.burst_frames - 1):
            time.sleep(cfg.burst_delay_ms / 1000.0)
            
            try:
                frame = self.camera.get_frame()
                new_corners, conf = self._detect_corners(frame)
                
                # Use new corners if detected, else use original
                if new_corners and self._corners_stable(new_corners):
                    corners_to_use = new_corners
                else:
                    corners_to_use = corners
                
                warped, _ = self._perspective_crop(frame, corners_to_use)
                warped_frames.append(warped)
                
            except Exception as e:
                logger.warning(f"Burst frame {i+1} capture failed: {e}")
        
        logger.debug(f"Burst capture: {len(warped_frames)} frames")
        
        # Select best quality frame
        best_image, best_metrics, best_idx = self.quality_assessor.select_best(
            warped_frames,
            min_quality=cfg.min_quality_score
        )
        
        return best_image, best_metrics
    
    def capture_single(self) -> CaptureResult:
        """
        Capture a single frame and process if document detected.
        Does NOT wait for stability - immediate capture.
        
        Returns:
            CaptureResult: Capture result with image and metadata
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if not self.camera or not self.camera.is_opened():
            return CaptureResult(
                success=False,
                timestamp=timestamp,
                error="Camera not initialized"
            )
        
        try:
            frame = self.camera.get_frame()
            corners, confidence = self._detect_corners(frame)
            
            if corners is None:
                return CaptureResult(
                    success=False,
                    timestamp=timestamp,
                    error="No document detected"
                )
            
            # Perspective crop
            warped, size = self._perspective_crop(frame, corners)
            
            # Assess quality
            metrics = self.quality_assessor.assess(warped)
            acceptable, reason = self.quality_assessor.is_acceptable(metrics)
            
            if not acceptable:
                return CaptureResult(
                    success=False,
                    timestamp=timestamp,
                    corners=corners,
                    quality_metrics=metrics,
                    error=reason
                )
            
            return CaptureResult(
                success=True,
                image=warped,
                corners=corners,
                quality_metrics=metrics,
                timestamp=timestamp,
                metadata={
                    'confidence': confidence,
                    'size': size,
                    'mode': 'single'
                }
            )
            
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return CaptureResult(
                success=False,
                timestamp=timestamp,
                error=str(e)
            )
    
    def capture_with_stability(self, timeout_seconds: float = 10.0) -> CaptureResult:
        """
        Wait for stable document detection, then perform burst capture.
        Returns only the single best-quality image.
        
        Args:
            timeout_seconds: Maximum time to wait for stable detection
            
        Returns:
            CaptureResult: Best quality capture result
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cfg = self.config
        
        if not self.camera or not self.camera.is_opened():
            return CaptureResult(
                success=False,
                timestamp=timestamp,
                error="Camera not initialized"
            )
        
        self._reset_state()
        start_time = time.time()
        
        logger.info("Starting stability capture...")
        
        while time.time() - start_time < timeout_seconds:
            try:
                frame = self.camera.get_frame()
                corners, confidence = self._detect_corners(frame)
                
                if corners is None:
                    # No document detected
                    self._reset_state()
                    continue
                
                if not self._corners_in_frame(corners, frame.shape):
                    # Document too close to edge
                    self._reset_state()
                    self._prev_corners = corners
                    continue
                
                if self._corners_stable(corners):
                    self._stable_count += 1
                    
                    if self._stable_count >= cfg.stability_frames:
                        # Document is stable - perform burst capture
                        logger.info(f"Document stable for {cfg.stability_frames} frames, capturing burst...")
                        
                        best_image, best_metrics = self._burst_capture(frame, corners)
                        
                        if best_image is None:
                            return CaptureResult(
                                success=False,
                                timestamp=timestamp,
                                corners=corners,
                                quality_metrics=best_metrics,
                                error="No acceptable quality frame in burst"
                            )
                        
                        # Get size from best image
                        h, w = best_image.shape[:2]
                        
                        return CaptureResult(
                            success=True,
                            image=best_image,
                            corners=corners,
                            quality_metrics=best_metrics,
                            timestamp=timestamp,
                            metadata={
                                'confidence': confidence,
                                'size': (w, h),
                                'mode': 'burst',
                                'burst_frames': cfg.burst_frames,
                                'stability_frames': cfg.stability_frames
                            }
                        )
                else:
                    # Document moved - reset stability counter
                    self._stable_count = 0
                
                self._prev_corners = corners
                
            except Exception as e:
                logger.warning(f"Frame processing error: {e}")
                self._reset_state()
        
        # Timeout
        return CaptureResult(
            success=False,
            timestamp=timestamp,
            error=f"Timeout after {timeout_seconds}s waiting for stable document"
        )
    
    def get_preview_frame(self, overlay: bool = True) -> Tuple[Optional[np.ndarray], Dict]:
        """
        Get current frame with optional detection overlay for preview.
        
        Args:
            overlay: Whether to draw detection overlay
            
        Returns:
            Tuple of (frame, detection_info)
        """
        if not self.camera or not self.camera.is_opened():
            return None, {'error': 'Camera not initialized'}
        
        try:
            frame = self.camera.get_frame()
            corners, confidence = self._detect_corners(frame)
            
            # Resize for display
            display = cv2.resize(
                frame,
                (self.config.display_width, self.config.display_height),
                interpolation=cv2.INTER_LINEAR
            )
            
            # Calculate scale for corner coordinates
            scale_x = self.config.display_width / self.config.camera_width
            scale_y = self.config.display_height / self.config.camera_height
            
            detection_info = {
                'detected': corners is not None,
                'confidence': confidence if corners else 0,
                'stable_count': self._stable_count,
                'stable_required': self.config.stability_frames,
                'progress': self._stable_count / self.config.stability_frames if corners else 0
            }
            
            if overlay and corners:
                # Scale corners for display
                display_corners = [(x * scale_x, y * scale_y) for x, y in corners]
                pts = np.array(display_corners, dtype=np.int32)
                
                # Update stability
                if self._corners_stable(corners):
                    self._stable_count = min(self._stable_count + 1, self.config.stability_frames)
                    color = (0, 255, 255) if self._stable_count >= self.config.stability_frames else (0, 255, 0)
                else:
                    self._stable_count = 0
                    color = (0, 165, 255)
                
                self._prev_corners = corners
                detection_info['stable_count'] = self._stable_count
                detection_info['progress'] = self._stable_count / self.config.stability_frames
                
                # Draw quadrilateral
                cv2.polylines(display, [pts], True, color, 2, cv2.LINE_AA)
                
                # Draw corner circles
                for pt in pts:
                    cv2.circle(display, tuple(pt), 6, color, -1)
                
                # Draw progress bar if stabilizing
                if self._stable_count > 0 and self._stable_count < self.config.stability_frames:
                    h, w = display.shape[:2]
                    bar_w, bar_h = 200, 8
                    bar_x = (w - bar_w) // 2
                    bar_y = h - 40
                    progress = self._stable_count / self.config.stability_frames
                    
                    cv2.rectangle(display, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (100, 100, 100), -1)
                    cv2.rectangle(display, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + bar_h), color, -1)
            
            return display, detection_info
            
        except Exception as e:
            logger.error(f"Preview error: {e}")
            return None, {'error': str(e)}
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False
