"""
MRZ Backend Microservice v3.3.0
Production API service for MRZ extraction with real-time WebSocket streaming.

Architecture:
- Layer 1: Auto-Capture (YOLO-based document detection, quality assessment)
- Layer 2: Image Enhancer (passthrough now, filters/enhancers later)
- Layer 3: MRZ Extraction (OCR, field parsing)
- Layer 4: Document Filling (PDF generation)

Provides:
- WebSocket endpoint for 24fps real-time binary frame streaming
- REST API for HTTP fallback (frame batching, gzip compression)
- Video stream processing (browser sends frames, backend detects)
- Real-time document detection and corner tracking
- MRZ extraction from captured/uploaded images
- Quality assessment and best-frame selection
- Document filling (PDF) - triggered after MRZ confirmation

NOTE: This is a pure BACKEND service. Camera is browser-based via WebRTC.
The frontend streams binary frames via WebSocket for optimal performance.
"""
from flask import Flask, Response, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_compress import Compress
from flask_sock import Sock
import gzip
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
import threading
import queue
import io
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

# Import layers
from layer1_auto_capture import QualityAssessor, QualityMetrics
from layer2_image_enhancer import ImageBridge, EnhancementConfig
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

# Enable gzip compression for all responses
Compress(app)
app.config['COMPRESS_MIMETYPES'] = ['application/json', 'text/html', 'text/css', 'application/javascript']
app.config['COMPRESS_LEVEL'] = 6  # Balance speed vs compression
app.config['COMPRESS_MIN_SIZE'] = 500  # Compress responses > 500 bytes

# Enable WebSocket support for real-time video streaming
sock = Sock(app)

# Configuration
TESSDATA_PATH = "models/"  # Directory containing mrz.traineddata
TEMPLATE_PATH = "templates/DWA_Registration_Card.pdf"  # Registration card template (PDF)
MODEL_PATH = "models/CornerDetection.pt"  # YOLO document detection model

# WebRTC Stream Settings
STREAM_FRAME_QUALITY = 85  # JPEG quality for stream responses
MAX_BURST_FRAMES = 5  # Maximum frames for burst capture
STABILITY_FRAMES = 8  # Frames required for stability
STABILITY_TOLERANCE = 15.0  # Max corner movement (pixels)
MIN_QUALITY_SCORE = 40.0  # Minimum acceptable quality score

# Video Stream Settings (24 FPS target)
VIDEO_TARGET_FPS = 24  # Target FPS for video streaming
VIDEO_FRAME_INTERVAL = 1.0 / VIDEO_TARGET_FPS  # ~41.67ms per frame
VIDEO_CHUNK_MAX_FRAMES = 48  # Max frames in a single chunk (~2 seconds)
VIDEO_BUFFER_SIZE = 72  # Buffer size for frame processing (~3 seconds)

# Directory structure
CAPTURED_PASSPORTS_DIR = "Logs/captured_passports"
CAPTURED_IMAGES_DIR = os.path.join(CAPTURED_PASSPORTS_DIR, "captured_images")
CAPTURED_JSON_DIR = os.path.join(CAPTURED_PASSPORTS_DIR, "captured_json")
DOCUMENT_FILLING_DIR = "Logs/document_filling"
DOCUMENT_MRZ_DIR = os.path.join(DOCUMENT_FILLING_DIR, "document_mrz")
DOCUMENT_FILLED_DIR = os.path.join(DOCUMENT_FILLING_DIR, "document_filled")
AUTO_CAPTURE_DIR = "Logs/auto_capture"

# Ensure directories exist
for dir_path in [CAPTURED_IMAGES_DIR, CAPTURED_JSON_DIR, DOCUMENT_MRZ_DIR, DOCUMENT_FILLED_DIR, AUTO_CAPTURE_DIR]:
    os.makedirs(dir_path, exist_ok=True)


# =============================================================================
# WebRTC Stream Session Manager
# =============================================================================

@dataclass
class StreamSession:
    """Tracks state for a WebRTC stream session."""
    session_id: str
    created_at: datetime
    prev_corners: Optional[List[Tuple[float, float]]] = None
    stable_count: int = 0
    burst_frames: List[np.ndarray] = field(default_factory=list)
    best_frame: Optional[np.ndarray] = None
    best_quality: float = 0.0
    captured: bool = False
    
    # Async YOLO detection state
    last_detection_corners: Optional[List[Tuple[float, float]]] = None
    last_detection_confidence: float = 0.0
    last_detection_time: float = 0.0
    pending_frame: Optional[np.ndarray] = None
    detection_in_progress: bool = False
    
    # Video stream state
    video_frame_buffer: deque = field(default_factory=lambda: deque(maxlen=VIDEO_BUFFER_SIZE))
    video_processing_active: bool = False
    video_last_processed_frame: int = 0
    video_total_frames_received: int = 0
    video_header: Optional[bytes] = None  # WebM header from first chunk
    
    def reset_stability(self):
        """Reset stability tracking."""
        self.prev_corners = None
        self.stable_count = 0
        self.burst_frames = []


class MRZBackendService:
    """
    Backend service for MRZ extraction with WebRTC stream support.
    
    This is a PURE BACKEND service. Camera is handled by the browser via WebRTC.
    The frontend sends frames to this backend for:
    - Document detection (corner tracking)
    - Stability monitoring
    - Quality assessment
    - Best-frame selection
    - MRZ extraction
    
    Flow:
    1. POST /api/stream/frame - Send frames for detection/stability
    2. POST /api/stream/capture - Trigger capture when stable
    3. POST /api/mrz/update - Finalize MRZ, trigger document filling
    """
    
    def __init__(self, tessdata_path, captured_images_dir, captured_json_dir, 
                 template_path, document_mrz_dir, document_filled_dir,
                 model_path=None):
        logger.info("Initializing MRZBackendService v3.3.0 (WebSocket + WebRTC Backend)")
        
        # Layer 1: YOLO model for document detection
        self.model = None
        self.model_path = model_path or MODEL_PATH
        self._model_loaded = False
        
        # Stream sessions (keyed by session_id)
        self.stream_sessions: Dict[str, StreamSession] = {}
        
        # Layer 2: Image Enhancer with OCR-optimized settings
        enhancement_config = EnhancementConfig(
            enable_contrast=True,      # Enable CLAHE for better text visibility
            clahe_clip_limit=2.0,
            enable_sharpening=True,    # Subtle sharpening for better OCR
            sharpen_amount=0.3,
            enable_denoise=False,      # Keep disabled to preserve text edges
            enable_upscaling=False      # Keep disabled for speed
        )
        self.image_enhancer = ImageBridge(config=enhancement_config)
        
        # Quality Assessor
        self.quality_assessor = QualityAssessor()
        
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
        
        # Load YOLO model for detection
        self._load_model()
        
        logger.info("MRZBackendService v3.1 initialized successfully")
    
    def _load_model(self) -> bool:
        """Load YOLO model for document detection."""
        if self._model_loaded:
            return True
        
        try:
            from ultralytics import YOLO
            
            if not os.path.exists(self.model_path):
                logger.warning(f"YOLO model not found at {self.model_path}")
                logger.warning("Document detection will use quality-only mode")
                return False
            
            logger.info(f"Loading YOLO model from {self.model_path}")
            self.model = YOLO(self.model_path)
            self.model.fuse()
            self._model_loaded = True
            logger.info("YOLO model loaded and fused")
            return True
            
        except ImportError:
            logger.warning("ultralytics not installed, detection disabled")
            return False
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            return False
    
    # =========================================================================
    # Stream Session Management
    # =========================================================================
    
    def create_stream_session(self) -> str:
        """Create a new stream session for WebRTC frame processing."""
        session_id = str(uuid.uuid4())
        self.stream_sessions[session_id] = StreamSession(
            session_id=session_id,
            created_at=datetime.now()
        )
        logger.info(f"Created stream session: {session_id}")
        return session_id
    
    def get_stream_session(self, session_id: str) -> Optional[StreamSession]:
        """Get an existing stream session."""
        return self.stream_sessions.get(session_id)
    
    def close_stream_session(self, session_id: str) -> bool:
        """
        Close and cleanup a stream session.
        
        Returns:
            bool: True if session was found and closed
        """
        session = self.stream_sessions.pop(session_id, None)
        if session is not None:
            # Explicitly clear large numpy arrays to help GC
            session.burst_frames.clear()
            session.best_frame = None
            session.prev_corners = None
            logger.info(f"Closed stream session: {session_id}")
            return True
        return False
    
    def cleanup_old_sessions(self, max_age_minutes: int = 30):
        """Remove sessions older than max_age_minutes."""
        now = datetime.now()
        expired = []
        for sid, session in self.stream_sessions.items():
            age = (now - session.created_at).total_seconds() / 60
            if age > max_age_minutes:
                expired.append(sid)
        
        for sid in expired:
            del self.stream_sessions[sid]
            logger.info(f"Expired stream session: {sid}")
    
    # =========================================================================
    # Document Detection (WebRTC Frame Processing)
    # =========================================================================
    
    def _detect_corners_yolo(self, frame: np.ndarray) -> Tuple[Optional[List[Tuple[float, float]]], float]:
        """
        Detect document corners using YOLO model.
        This is the accurate but slow method (~1-2s on CPU).
        
        Args:
            frame: BGR image from WebRTC stream
            
        Returns:
            Tuple of (corners, confidence) or (None, 0) if not detected
        """
        if not self._model_loaded or self.model is None:
            logger.warning("YOLO model not loaded, using fallback")
            return self._detect_corners_fallback(frame)
        
        try:
            # Add virtual padding for edge detection
            h, w = frame.shape[:2]
            ratio = 0.15
            px, py = int(w * ratio), int(h * ratio)
            padded = np.full((h + 2*py, w + 2*px, 3), 128, dtype=np.uint8)
            padded[py:py+h, px:px+w] = frame
            
            # Run inference
            results = self.model(padded, conf=0.5, verbose=False)
            
            # Extract corners from keypoints
            for r in results:
                if r.keypoints is not None and len(r.keypoints) > 0:
                    kpts = r.keypoints.data[0].cpu().numpy()
                    visible = []
                    for x, y, v in kpts:
                        if v > 0.5:
                            visible.append((float(x) - px, float(y) - py))
                    
                    if len(visible) == 4:
                        confidence = float(r.boxes.conf[0].item())
                        return visible, confidence
            
            return None, 0.0
            
        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
            return None, 0.0
    
    def _detect_corners(self, frame: np.ndarray, use_fast_mode: bool = True) -> Tuple[Optional[List[Tuple[float, float]]], float]:
        """
        Detect document corners using YOLO model or fast fallback.
        
        Args:
            frame: BGR image from WebRTC stream
            use_fast_mode: If True, use fast OpenCV detection (for streaming).
                          If False, use YOLO (for final capture).
            
        Returns:
            Tuple of (corners, confidence) or (None, 0) if not detected
        """
        if use_fast_mode:
            return self._detect_corners_fallback(frame)
        
        return self._detect_corners_yolo(frame)
    
    def _detect_corners_fallback(self, frame: np.ndarray) -> Tuple[Optional[List[Tuple[float, float]]], float]:
        """
        Fast fallback detection using edge detection and contour analysis.
        Optimized for real-time streaming (~10-20ms per frame).
        
        Args:
            frame: BGR image from WebRTC stream
            
        Returns:
            Tuple of (corners, confidence) or (None, 0) if not detected
        """
        try:
            h, w = frame.shape[:2]
            
            # Downscale for faster processing (process at 320px width)
            scale = 320 / w if w > 320 else 1.0
            if scale < 1.0:
                small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            else:
                small = frame
            sh, sw = small.shape[:2]
            
            # Convert to grayscale
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur (smaller kernel for speed)
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # Edge detection
            edges = cv2.Canny(blurred, 50, 150)
            
            # Dilate to connect edges (single iteration)
            kernel = np.ones((2, 2), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                return None, 0.0
            
            # Find largest contour
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            
            # Check if contour is large enough (at least 10% of frame)
            min_area = sh * sw * 0.10
            if area < min_area:
                return None, 0.0
            
            # Approximate contour to polygon
            epsilon = 0.02 * cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, epsilon, True)
            
            # Scale corners back to original size
            inv_scale = 1.0 / scale
            
            # Check if it's a quadrilateral
            if len(approx) == 4:
                corners = [(float(p[0][0]) * inv_scale, float(p[0][1]) * inv_scale) for p in approx]
                # Confidence based on area ratio
                confidence = min(area / (sh * sw * 0.5), 1.0)
                return corners, confidence
            
            # If not a quad, create synthetic corners based on bounding rect
            x, y, rw, rh = cv2.boundingRect(largest)
            
            # Check aspect ratio (passport is roughly 1.4:1)
            aspect = rw / rh if rh > 0 else 0
            if 0.6 < aspect < 2.0 and area > min_area:
                # Return bounding box corners (scaled back)
                corners = [
                    (float(x) * inv_scale, float(y) * inv_scale),
                    (float(x + rw) * inv_scale, float(y) * inv_scale),
                    (float(x + rw) * inv_scale, float(y + rh) * inv_scale),
                    (float(x) * inv_scale, float(y + rh) * inv_scale)
                ]
                confidence = min(area / (sh * sw * 0.4), 0.8)  # Max 80% for fallback
                return corners, confidence
            
            return None, 0.0
            
        except Exception as e:
            logger.debug(f"Fallback detection error: {e}")
            return None, 0.0
    
    def _order_corners(self, corners: List[Tuple[float, float]]) -> np.ndarray:
        """Order corners: top-left, top-right, bottom-right, bottom-left."""
        c = np.array(corners, dtype='float32')
        c = c[c[:, 1].argsort()]
        top = c[:2][c[:2, 0].argsort()]
        bottom = c[2:][c[2:, 0].argsort()]
        return np.array([top[0], top[1], bottom[1], bottom[0]], dtype='float32')
    
    def _corners_stable(self, current: List[Tuple[float, float]], 
                        previous: Optional[List[Tuple[float, float]]]) -> bool:
        """Check if corners are stable compared to previous frame."""
        if previous is None:
            return False
        
        curr_arr = np.array(current)
        prev_arr = np.array(previous)
        distances = np.linalg.norm(curr_arr - prev_arr, axis=1)
        return np.max(distances) < STABILITY_TOLERANCE
    
    def _perspective_crop(self, image: np.ndarray, 
                          corners: List[Tuple[float, float]]) -> np.ndarray:
        """Apply perspective transform to extract flat document."""
        src = self._order_corners(corners)
        
        width = int(max(
            np.linalg.norm(src[1] - src[0]),
            np.linalg.norm(src[2] - src[3])
        ))
        height = int(max(
            np.linalg.norm(src[3] - src[0]),
            np.linalg.norm(src[2] - src[1])
        ))
        
        width = max(width, 400)
        height = max(height, 300)
        
        dst = np.array([
            [0, 0], [width - 1, 0],
            [width - 1, height - 1], [0, height - 1]
        ], dtype='float32')
        
        M = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(image, M, (width, height))
    
    def process_stream_frame(self, session_id: str, image_data: str) -> dict:
        """
        Process a frame from WebRTC stream with async YOLO detection.
        
        Uses background thread for YOLO inference to maintain high FPS.
        Returns immediately with last known detection result.
        
        Args:
            session_id: Stream session ID
            image_data: Base64 encoded frame from browser
            
        Returns:
            dict with detection status, corners, stability info
        """
        session = self.get_stream_session(session_id)
        if session is None:
            return {"error": "Invalid session", "error_code": "INVALID_SESSION", "detected": False}
        
        try:
            # Decode frame
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return {"error": "Could not decode frame", "error_code": "DECODE_FAILED", "detected": False}
            
            # Use YOLO detection (accurate but slower)
            # Run in background thread to avoid blocking
            if not session.detection_in_progress:
                session.detection_in_progress = True
                session.pending_frame = frame.copy()
                
                def run_yolo_detection():
                    try:
                        corners, confidence = self._detect_corners_yolo(session.pending_frame)
                        session.last_detection_corners = corners
                        session.last_detection_confidence = confidence
                        session.last_detection_time = time.time()
                    except Exception as e:
                        logger.error(f"YOLO detection error: {e}")
                    finally:
                        session.detection_in_progress = False
                
                # Run YOLO in background thread
                threading.Thread(target=run_yolo_detection, daemon=True).start()
            
            # Use last known detection result (for instant response)
            corners = session.last_detection_corners
            confidence = session.last_detection_confidence
            
            result = {
                "detected": corners is not None,
                "confidence": confidence,
                "corners": corners,
                "stable_count": session.stable_count,
                "stable_required": STABILITY_FRAMES,
                "ready_for_capture": False,
                "detection_age_ms": int((time.time() - session.last_detection_time) * 1000) if session.last_detection_time > 0 else 0
            }
            
            if corners is None:
                session.reset_stability()
                return result
            
            # Check stability
            if self._corners_stable(corners, session.prev_corners):
                session.stable_count += 1
                
                # Only assess quality when approaching stability (expensive)
                if session.stable_count >= STABILITY_FRAMES // 2:
                    warped = self._perspective_crop(frame, corners)
                    quality = self.quality_assessor.assess(warped)
                    result["quality_score"] = quality.overall_score
                    
                    if quality.overall_score > session.best_quality:
                        session.best_quality = quality.overall_score
                        session.best_frame = warped
                    
                    if len(session.burst_frames) < MAX_BURST_FRAMES:
                        session.burst_frames.append(warped)
                
                if session.stable_count >= STABILITY_FRAMES:
                    result["ready_for_capture"] = True
                    result["quality_score"] = session.best_quality
            else:
                # Reset on instability
                session.stable_count = 0
                session.burst_frames.clear()
                session.best_frame = None
                session.best_quality = 0.0
            
            session.prev_corners = corners
            result["stable_count"] = session.stable_count
            result["quality_score"] = session.best_quality
            
            return result
            
        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return {"error": str(e), "detected": False}
    
    # =========================================================================
    # Video Stream Processing (MediaRecorder Chunks)
    # =========================================================================
    
    def process_video_chunk(self, session_id: str, video_data: bytes, 
                            chunk_index: int = 0) -> dict:
        """
        Process a video chunk from the kiosk (MediaRecorder WebM).
        The backend splits the video into frames and processes them.
        
        Args:
            session_id: Stream session ID
            video_data: Raw video bytes (WebM/MP4 chunk from MediaRecorder)
            chunk_index: Chunk sequence number for ordering
            
        Returns:
            dict with processing status and detection results
        """
        session = self.get_stream_session(session_id)
        if session is None:
            return {"error": "Invalid session", "error_code": "INVALID_SESSION", "detected": False}
        
        try:
            # For first chunk, we need to accumulate the WebM header
            # MediaRecorder chunks need the header from chunk 0 to be decodable
            if chunk_index == 0:
                session.video_header = video_data
            
            # Save video chunk to temp file for OpenCV processing
            # Include header for non-first chunks to make them decodable
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
                if chunk_index == 0:
                    tmp.write(video_data)
                else:
                    # Prepend header to make chunk decodable
                    if hasattr(session, 'video_header') and session.video_header:
                        tmp.write(session.video_header + video_data)
                    else:
                        tmp.write(video_data)
                tmp_path = tmp.name
            
            # Extract frames from video chunk
            frames = self._extract_frames_from_video(tmp_path)
            
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            
            if not frames:
                logger.warning(f"[Video] No frames extracted from chunk {chunk_index} ({len(video_data)} bytes)")
                # Return last known detection state instead of error
                return {
                    "detected": session.last_detection_corners is not None,
                    "confidence": session.last_detection_confidence,
                    "corners": session.last_detection_corners,
                    "stable_count": session.stable_count,
                    "stable_required": STABILITY_FRAMES,
                    "ready_for_capture": session.stable_count >= STABILITY_FRAMES,
                    "frames_processed": 0,
                    "chunk_index": chunk_index,
                    "quality_score": session.best_quality
                }
            
            logger.info(f"[Video] Extracted {len(frames)} frames from chunk {chunk_index}")
            
            # Process frames through detection pipeline
            result = self._process_video_frames(session, frames)
            result["frames_processed"] = len(frames)
            result["chunk_index"] = chunk_index
            
            return result
            
        except Exception as e:
            logger.error(f"Video chunk processing error: {e}")
            return {"error": str(e), "detected": False, "frames_processed": 0}
    
    def _extract_frames_from_video(self, video_path: str) -> List[np.ndarray]:
        """
        Extract frames from a video file.
        Uses OpenCV with ffmpeg backend for WebM support.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of frames as numpy arrays
        """
        frames = []
        
        try:
            # Try OpenCV first (works for most formats)
            cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
            
            if not cap.isOpened():
                # Try without explicit backend
                cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                logger.warning(f"Could not open video file with OpenCV: {video_path}")
                # Try ffmpeg directly as fallback
                return self._extract_frames_ffmpeg(video_path)
            
            # Get video properties
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            logger.debug(f"Video: {video_fps:.1f}fps, {total_frames} frames (reported)")
            
            # For short chunks, just extract all frames
            # Don't skip frames - process what we get
            frame_idx = 0
            max_frames = 24  # Limit to 24 frames per chunk (1 second at 24fps)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frames.append(frame)
                frame_idx += 1
                
                if len(frames) >= max_frames:
                    break
            
            cap.release()
            
            if not frames:
                logger.warning(f"OpenCV extracted 0 frames, trying ffmpeg fallback")
                return self._extract_frames_ffmpeg(video_path)
            
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            # Try ffmpeg fallback
            return self._extract_frames_ffmpeg(video_path)
        
        return frames
    
    def _extract_frames_ffmpeg(self, video_path: str) -> List[np.ndarray]:
        """
        Fallback frame extraction using ffmpeg directly.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of frames as numpy arrays
        """
        import subprocess
        
        frames = []
        output_pattern = video_path + "_frame_%03d.jpg"
        
        try:
            # Use ffmpeg to extract frames
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-vf', 'fps=24',  # Extract at 24fps
                '-q:v', '2',  # Good JPEG quality
                '-frames:v', '24',  # Max 24 frames
                output_pattern
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            
            if result.returncode != 0:
                logger.warning(f"ffmpeg failed: {result.stderr.decode()[:200]}")
                return frames
            
            # Read the extracted frames
            for i in range(1, 25):
                frame_path = video_path + f"_frame_{i:03d}.jpg"
                if os.path.exists(frame_path):
                    frame = cv2.imread(frame_path)
                    if frame is not None:
                        frames.append(frame)
                    os.unlink(frame_path)
                else:
                    break
            
            logger.debug(f"ffmpeg extracted {len(frames)} frames")
            
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg timeout")
        except FileNotFoundError:
            logger.warning("ffmpeg not installed")
        except Exception as e:
            logger.error(f"ffmpeg extraction error: {e}")
        
        return frames
    
    def _process_video_frames(self, session: StreamSession, 
                               frames: List[np.ndarray]) -> dict:
        """
        Process multiple frames from video stream.
        Uses the best frame based on detection and quality.
        
        Args:
            session: Stream session
            frames: List of frames to process
            
        Returns:
            dict with detection results from best frame
        """
        best_result = {
            "detected": False,
            "confidence": 0.0,
            "corners": None,
            "stable_count": 0,
            "stable_required": STABILITY_FRAMES,
            "ready_for_capture": False,
            "quality_score": 0.0
        }
        
        for frame in frames:
            session.video_total_frames_received += 1
            
            # Add frame to buffer
            session.video_frame_buffer.append(frame)
            
            # Start async YOLO detection if not already running
            if not session.detection_in_progress:
                session.detection_in_progress = True
                session.pending_frame = frame.copy()
                
                def run_yolo_detection():
                    try:
                        corners, confidence = self._detect_corners_yolo(session.pending_frame)
                        session.last_detection_corners = corners
                        session.last_detection_confidence = confidence
                        session.last_detection_time = time.time()
                    except Exception as e:
                        logger.error(f"YOLO detection error: {e}")
                    finally:
                        session.detection_in_progress = False
                
                threading.Thread(target=run_yolo_detection, daemon=True).start()
            
            # Use last known detection
            corners = session.last_detection_corners
            confidence = session.last_detection_confidence
            
            if corners is not None:
                # Check stability
                if self._corners_stable(corners, session.prev_corners):
                    session.stable_count += 1
                    
                    if session.stable_count >= STABILITY_FRAMES // 2:
                        warped = self._perspective_crop(frame, corners)
                        quality = self.quality_assessor.assess(warped)
                        
                        if quality.overall_score > session.best_quality:
                            session.best_quality = quality.overall_score
                            session.best_frame = warped
                        
                        if len(session.burst_frames) < MAX_BURST_FRAMES:
                            session.burst_frames.append(warped)
                else:
                    session.stable_count = 0
                    session.burst_frames.clear()
                    session.best_frame = None
                    session.best_quality = 0.0
                
                session.prev_corners = corners
                
                # Update best result
                if confidence > best_result["confidence"]:
                    best_result = {
                        "detected": True,
                        "confidence": confidence,
                        "corners": corners,
                        "stable_count": session.stable_count,
                        "stable_required": STABILITY_FRAMES,
                        "ready_for_capture": session.stable_count >= STABILITY_FRAMES,
                        "quality_score": session.best_quality,
                        "total_frames": session.video_total_frames_received
                    }
            else:
                session.reset_stability()
        
        return best_result
    
    def process_video_stream_base64(self, session_id: str, 
                                     frames_base64: List[str]) -> dict:
        """
        Process multiple base64-encoded frames from a video stream.
        This is an alternative to sending raw video chunks.
        
        The kiosk captures at 24fps and sends batches of frames.
        
        Args:
            session_id: Stream session ID
            frames_base64: List of base64-encoded JPEG frames
            
        Returns:
            dict with processing results
        """
        session = self.get_stream_session(session_id)
        if session is None:
            return {"error": "Invalid session", "error_code": "INVALID_SESSION", "detected": False}
        
        try:
            frames = []
            for frame_b64 in frames_base64:
                image_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(image_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.append(frame)
            
            if not frames:
                return {
                    "error": "No valid frames decoded",
                    "error_code": "DECODE_FAILED",
                    "detected": False,
                    "frames_processed": 0
                }
            
            logger.debug(f"[Video] Processing batch of {len(frames)} frames")
            
            result = self._process_video_frames(session, frames)
            result["frames_processed"] = len(frames)
            
            return result
            
        except Exception as e:
            logger.error(f"Video stream processing error: {e}")
            return {"error": str(e), "detected": False, "frames_processed": 0}

    def capture_from_stream(self, session_id: str) -> dict:
        """
        Capture the best frame from stream session.
        
        Args:
            session_id: Stream session ID
            
        Returns:
            dict with captured image and quality info
        """
        session = self.get_stream_session(session_id)
        if session is None:
            return {"success": False, "error": "Invalid session"}
        
        if session.best_frame is None:
            return {"success": False, "error": "No stable frame captured"}
        
        logger.info(f"[Layer 1] Stream capture - Quality: {session.best_quality:.1f}")
        
        # Process through pipeline
        return self._process_captured_image(session.best_frame, session)
    
    def _process_captured_image(self, image: np.ndarray, session: StreamSession) -> dict:
        """
        Process a captured image through the pipeline.
        
        Args:
            image: Captured image (already perspective-corrected)
            session: StreamSession with quality metrics
            
        Returns:
            dict: Processing result with MRZ data
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        session_id = session.session_id
        
        try:
            # Layer 2: Image Enhancer (passthrough or enhancements)
            logger.info("[Layer 2] Processing through enhancer...")
            processed_image = self.image_enhancer.process(image)
            logger.info("[Layer 2] Enhancer processing complete")
            
            # Save processed image
            image_filename = f"{timestamp}_{session_id}.jpg"
            image_path = os.path.join(self.captured_images_dir, image_filename)
            cv2.imwrite(image_path, processed_image)
            logger.info(f"[Layer 2] Image saved: {image_path}")
            
            # Layer 3: MRZ Extraction
            logger.info("[Layer 3] Extracting MRZ...")
            mrz_data = self.mrz_extractor.extract(image_path)
            
            # Prepare result
            result_data = {
                "session_id": session_id,
                "timestamp": timestamp,
                "image_path": image_path,
                "capture_mode": "webrtc_stream",
                "status": "extracted",
                "mrz_data": mrz_data,
                "quality": session.best_quality,
                "is_edited": False
            }
            
            # Save JSON
            json_filename = f"{timestamp}_{session_id}.json"
            json_path = os.path.join(self.captured_json_dir, json_filename)
            with open(json_path, 'w') as f:
                json.dump(result_data, f, indent=2)
            logger.info(f"[Layer 3] JSON saved: {json_path}")
            
            logger.info("[Pipeline] Stream capture complete!")
            logger.info("=" * 60)
            
            return {
                "success": True,
                "session_id": session_id,
                "data": mrz_data,
                "image_path": image_path,
                "timestamp": timestamp,
                "quality": session.best_quality,
                "message": "MRZ extracted. Call /api/mrz/update to finalize."
            }
            
        except Exception as e:
            logger.error(f"[Pipeline] Processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "PROCESSING_FAILED"
            }
    
    def process_image(self, image_data, filename="upload.jpg"):
        """
        Process an uploaded image and extract MRZ data.
        Used for web upload mode (not camera capture).
        
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
            
            # Assess quality of uploaded image
            quality_metrics = self.quality_assessor.assess(raw_frame)
            acceptable, reason = self.quality_assessor.is_acceptable(quality_metrics)
            
            if not acceptable:
                logger.warning(f"Image quality issue: {reason}")
                # Continue anyway but log warning
            
            # Generate session_id for tracking
            session_id = str(uuid.uuid4())
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # Layer 2: Process through bridge
            logger.info("[Layer 2] Processing through bridge...")
            processed_frame = self.image_enhancer.process(raw_frame)
            logger.info("[Layer 2] Bridge processing complete")
            
            # Layer 3: Save image and extract MRZ
            logger.info("[Layer 3] Saving image...")
            
            # Save to captured_images with session_id in filename
            image_filename = f"{timestamp}_{session_id}.jpg"
            image_path = os.path.join(self.captured_images_dir, image_filename)
            cv2.imwrite(image_path, processed_frame)
            logger.info(f"[Layer 3] Image saved to: {image_path}")
            
            logger.info("[Layer 3] Extracting MRZ...")
            mrz_data = self.mrz_extractor.extract(image_path)
            
            # Prepare result data
            result_data = {
                "session_id": session_id,
                "timestamp": timestamp,
                "image_path": image_path,
                "image_filename": filename,
                "capture_mode": "upload",
                "status": "extracted",
                "mrz_data": mrz_data,
                "quality": quality_metrics.to_dict(),
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
                "quality": quality_metrics.to_dict(),
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
            original_mrz: Original MRZ data from extraction (uses MRZ field names)
            new_guest_data: New guest data from update request (may use UI field names)
            
        Returns:
            dict: Comparison result with is_edited flag and changed_fields list
        """
        # Helper to get value from guest_data with fallback aliases
        def get_guest_value(primary_key: str, *fallback_keys: str) -> str:
            """Get value from guest_data, trying primary key first then fallbacks."""
            value = new_guest_data.get(primary_key)
            if not value:
                for key in fallback_keys:
                    value = new_guest_data.get(key)
                    if value:
                        break
            return (value or '').strip().upper()
        
        # Fields to compare: (mrz_field, display_name, primary_guest_key, *fallback_keys)
        # MRZ extractor provides: surname, given_name, nationality_code, issuer_code, document_number, etc.
        # UI/kiosk may send: name, nationality, country instead
        field_comparisons = [
            ('surname', 'surname', 'surname'),
            ('given_name', 'given_name', 'given_name', 'name', 'first_name'),
            ('nationality_code', 'nationality_code', 'nationality_code', 'nationality'),
            ('document_number', 'passport_number', 'passport_number', 'document_number'),
            ('birth_date', 'date_of_birth', 'date_of_birth', 'birth_date'),
            ('sex', 'sex', 'sex', 'gender'),
            ('expiry_date', 'expiry_date', 'expiry_date'),
            ('issuer_code', 'issuer_code', 'issuer_code', 'country', 'issuing_country'),
        ]
        
        changed_fields = []
        
        for comparison in field_comparisons:
            mrz_field = comparison[0]
            display_name = comparison[1]
            primary_key = comparison[2]
            fallback_keys = comparison[3:] if len(comparison) > 3 else ()
            
            original_value = (original_mrz.get(mrz_field, '') or '').strip().upper()
            new_value = get_guest_value(primary_key, *fallback_keys)
            
            if original_value != new_value:
                # Get the actual key that had the value for better logging
                actual_new_value = new_guest_data.get(primary_key)
                if not actual_new_value:
                    for key in fallback_keys:
                        actual_new_value = new_guest_data.get(key)
                        if actual_new_value:
                            break
                
                changed_fields.append({
                    'field': display_name,
                    'original': original_mrz.get(mrz_field, ''),
                    'new': actual_new_value or ''
                })
                logger.info(f"[MRZ Compare] Field '{display_name}' changed: '{original_mrz.get(mrz_field, '')}' -> '{actual_new_value or ''}'")
        
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
        Detect if a document is present in the image.
        Uses YOLO model for corner detection if available.
        
        Args:
            image_data: Raw image bytes or base64 encoded string
            
        Returns:
            dict: Detection result with confidence and quality metrics
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
            
            # Assess quality
            quality = self.quality_assessor.assess(frame)
            acceptable, reason = self.quality_assessor.is_acceptable(quality)
            
            # Use YOLO detection if model is loaded
            if self._model_loaded:
                corners, confidence = self._detect_corners(frame)
                
                if corners:
                    return {
                        "detected": True,
                        "confidence": confidence,
                        "corners": corners,
                        "quality": quality.to_dict(),
                        "quality_acceptable": acceptable,
                        "ready_for_capture": acceptable and confidence > 0.5
                    }
            
            # Fallback: just return quality info
            return {
                "detected": acceptable,
                "confidence": quality.overall_score / 100,
                "quality": quality.to_dict(),
                "quality_acceptable": acceptable,
                "ready_for_capture": acceptable
            }
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return {"detected": False, "error": str(e)}


# Initialize backend service
logger.info("Starting MRZ Backend Service v3.1 initialization")

service = MRZBackendService(
    tessdata_path=TESSDATA_PATH,
    captured_images_dir=CAPTURED_IMAGES_DIR,
    captured_json_dir=CAPTURED_JSON_DIR,
    template_path=TEMPLATE_PATH,
    document_mrz_dir=DOCUMENT_MRZ_DIR,
    document_filled_dir=DOCUMENT_FILLED_DIR,
    model_path=MODEL_PATH
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.before_request
def decompress_request():
    """Decompress gzip-encoded request bodies for faster network transfer."""
    if request.content_encoding == 'gzip':
        try:
            request._cached_data = gzip.decompress(request.get_data())
        except Exception as e:
            logger.warning(f"Failed to decompress gzip request: {e}")

def get_json_data():
    """Get JSON data from request, handling gzip compression."""
    if hasattr(request, '_cached_data'):
        return json.loads(request._cached_data)
    return request.get_json()

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for service discovery and load balancers"""
    return jsonify({
        "status": "healthy",
        "service": "mrz-backend",
        "version": "3.3.0",
        "mode": "websocket_stream",
        "target_fps": VIDEO_TARGET_FPS,
        "websocket_enabled": True,
        "capabilities": [
            "websocket_stream_24fps",
            "video_stream_24fps",
            "frame_batch_processing",
            "video_chunk_splitting",
            "document_detection",
            "mrz_extraction", 
            "quality_assessment",
            "document_filling"
        ],
        "model_loaded": service._model_loaded,
        "active_sessions": len(service.stream_sessions)
    })


# ============================================================================
# WebRTC Stream Endpoints (Layer 1)
# ============================================================================

@app.route("/api/stream/session", methods=["POST"])
def api_create_stream_session():
    """
    Create a new WebRTC stream session.
    Call this before sending frames.
    
    Response:
        {
            "success": true,
            "session_id": "uuid-here",
            "message": "Stream session created"
        }
    """
    logger.info("Creating new stream session")
    
    # Cleanup old sessions first
    service.cleanup_old_sessions()
    
    session_id = service.create_stream_session()
    
    return jsonify({
        "success": True,
        "session_id": session_id,
        "message": "Stream session created. Send frames to /api/stream/frame"
    })


@app.route("/api/stream/session/<session_id>", methods=["DELETE"])
def api_close_stream_session(session_id):
    """
    Close a stream session.
    
    Response:
        {
            "success": true,
            "message": "Session closed"
        }
    """
    logger.info(f"Closing stream session: {session_id}")
    
    service.close_stream_session(session_id)
    
    return jsonify({
        "success": True,
        "message": "Session closed"
    })


@app.route("/api/stream/frame", methods=["POST"])
def api_process_stream_frame():
    """
    Process a frame from WebRTC stream.
    Browser sends frames, backend detects document and tracks stability.
    Supports gzip-compressed requests for faster network transfer.
    
    Request (application/json, optionally gzip compressed):
        {
            "session_id": "uuid-here",
            "image": "base64-encoded-frame"
        }
        
    Response:
        {
            "detected": true,
            "confidence": 0.95,
            "corners": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
            "stable_count": 5,
            "stable_required": 8,
            "ready_for_capture": false,
            "quality_score": 72.5
        }
    """
    # Handle both gzip-compressed and regular JSON
    try:
        data = get_json_data()
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {e}", "detected": False}), 400
    
    if not data:
        return jsonify({"error": "JSON body required", "detected": False}), 400
    
    session_id = data.get('session_id')
    image_data = data.get('image')
    
    if not session_id:
        return jsonify({"error": "session_id required", "detected": False}), 400
    
    if not image_data:
        return jsonify({"error": "image required", "detected": False}), 400
    
    result = service.process_stream_frame(session_id, image_data)
    return jsonify(result)


@app.route("/api/stream/capture", methods=["POST"])
def api_capture_from_stream():
    """
    Capture the best frame from stream session.
    Call this when ready_for_capture is true.
    
    Request (application/json):
        {
            "session_id": "uuid-here"
        }
        
    Response:
        {
            "success": true,
            "session_id": "uuid-here",
            "data": { ... MRZ fields ... },
            "quality": 85.2,
            "timestamp": "20231231_120000",
            "message": "MRZ extracted. Call /api/mrz/update to finalize."
        }
    """
    logger.info("Stream capture request received")
    
    if not request.is_json:
        return jsonify({"success": False, "error": "JSON body required"}), 400
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({"success": False, "error": "session_id required"}), 400
    
    result = service.capture_from_stream(session_id)
    
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 422


# ============================================================================
# Video Stream Endpoints (24 FPS - Backend Frame Splitting)
# ============================================================================

@app.route("/api/stream/video", methods=["POST"])
def api_process_video_chunk():
    """
    Process a video chunk from the kiosk (24fps video stream).
    Backend splits the video into frames and processes them.
    
    Request (multipart/form-data):
        - 'video': Video chunk file (WebM/MP4)
        - 'session_id': Stream session ID
        - 'chunk_index': Optional chunk sequence number
        
    Response:
        {
            "detected": true,
            "confidence": 0.95,
            "corners": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
            "stable_count": 5,
            "stable_required": 8,
            "ready_for_capture": false,
            "quality_score": 72.5,
            "frames_processed": 24,
            "chunk_index": 0
        }
    """
    session_id = request.form.get('session_id')
    chunk_index = int(request.form.get('chunk_index', 0))
    
    if not session_id:
        return jsonify({"error": "session_id required", "detected": False}), 400
    
    if 'video' not in request.files:
        return jsonify({"error": "video file required", "detected": False}), 400
    
    video_file = request.files['video']
    video_data = video_file.read()
    
    if not video_data:
        return jsonify({"error": "empty video file", "detected": False}), 400
    
    logger.info(f"[Video] Received chunk {chunk_index} ({len(video_data)} bytes)")
    
    result = service.process_video_chunk(session_id, video_data, chunk_index)
    return jsonify(result)


@app.route("/api/stream/video/frames", methods=["POST"])
def api_process_video_frames():
    """
    Process multiple frames from a video stream (24fps batch).
    Kiosk sends a batch of base64-encoded frames.
    
    Request (application/json):
        {
            "session_id": "uuid-here",
            "frames": ["base64-frame-1", "base64-frame-2", ...]
        }
        
    Response:
        {
            "detected": true,
            "confidence": 0.95,
            "corners": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
            "stable_count": 5,
            "stable_required": 8,
            "ready_for_capture": false,
            "quality_score": 72.5,
            "frames_processed": 24,
            "total_frames": 120
        }
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required", "detected": False}), 400
    
    data = request.get_json()
    session_id = data.get('session_id')
    frames = data.get('frames', [])
    
    if not session_id:
        return jsonify({"error": "session_id required", "detected": False}), 400
    
    if not frames:
        return jsonify({"error": "frames array required", "detected": False}), 400
    
    logger.debug(f"[Video] Processing batch of {len(frames)} frames")
    
    result = service.process_video_stream_base64(session_id, frames)
    return jsonify(result)


# ============================================================================
# WebSocket Real-Time Video Stream (24 FPS - Zero HTTP Overhead)
# ============================================================================

@sock.route('/api/stream/ws')
def websocket_video_stream(ws):
    """
    WebSocket endpoint for real-time video streaming at 24fps.
    Eliminates HTTP overhead for maximum frame rate.
    
    Protocol:
    1. Client sends JSON: {"action": "init", "session_id": "uuid"}
    2. Client sends binary JPEG/WebP frames continuously
    3. Server sends JSON detection results for each frame
    4. Client sends JSON: {"action": "capture"} to capture best frame
    5. Server sends JSON with MRZ data
    6. Client sends JSON: {"action": "close"} to end session
    """
    session_id = None
    frame_count = 0
    start_time = time.time()
    
    logger.info("[WebSocket] New connection")
    
    try:
        while True:
            message = ws.receive()
            
            if message is None:
                break
            
            # Binary data = video frame
            if isinstance(message, bytes):
                if not session_id:
                    ws.send(json.dumps({"error": "Session not initialized", "detected": False}))
                    continue
                
                frame_count += 1
                
                # Decode frame directly from bytes (JPEG/WebP)
                try:
                    nparr = np.frombuffer(message, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is None:
                        ws.send(json.dumps({"error": "Invalid frame", "detected": False}))
                        continue
                    
                    # Process frame using existing service
                    # Convert to base64 for compatibility with existing method
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    frame_b64 = base64.b64encode(buffer).decode('utf-8')
                    
                    result = service.process_stream_frame(session_id, frame_b64)
                    result['frame_num'] = frame_count
                    
                    ws.send(json.dumps(result))
                    
                except Exception as e:
                    logger.error(f"[WebSocket] Frame processing error: {e}")
                    ws.send(json.dumps({"error": str(e), "detected": False}))
            
            # Text data = JSON command
            else:
                try:
                    data = json.loads(message)
                    action = data.get('action')
                    
                    if action == 'init':
                        req_session_id = data.get('session_id')
                        if not req_session_id:
                            # Create new session (generates its own ID)
                            session_id = service.create_stream_session()
                        elif req_session_id not in service.stream_sessions:
                            # Requested session doesn't exist, create new one
                            session_id = service.create_stream_session()
                        else:
                            # Use existing session
                            session_id = req_session_id
                        
                        logger.info(f"[WebSocket] Session initialized: {session_id}")
                        ws.send(json.dumps({
                            "action": "init_ok",
                            "session_id": session_id,
                            "message": "Session ready. Send binary frames."
                        }))
                    
                    elif action == 'capture':
                        if not session_id:
                            ws.send(json.dumps({"success": False, "error": "No session"}))
                            continue
                        
                        result = service.capture_from_stream(session_id)
                        result['action'] = 'capture_result'
                        ws.send(json.dumps(result))
                        
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed if elapsed > 0 else 0
                        logger.info(f"[WebSocket] Capture requested. Processed {frame_count} frames at {fps:.1f} fps")
                    
                    elif action == 'close':
                        if session_id:
                            service.close_stream_session(session_id)
                        ws.send(json.dumps({"action": "closed"}))
                        break
                    
                    elif action == 'ping':
                        ws.send(json.dumps({"action": "pong"}))
                    
                    else:
                        ws.send(json.dumps({"error": f"Unknown action: {action}"}))
                
                except json.JSONDecodeError as e:
                    ws.send(json.dumps({"error": f"Invalid JSON: {e}"}))
    
    except Exception as e:
        logger.error(f"[WebSocket] Connection error: {e}")
    
    finally:
        if session_id:
            try:
                service.close_stream_session(session_id)
            except:
                pass
        
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        logger.info(f"[WebSocket] Connection closed. Processed {frame_count} frames in {elapsed:.1f}s ({fps:.1f} fps)")


# ============================================================================
# Legacy Upload Endpoint (Web Upload Mode)
# ============================================================================


@app.route("/api/extract", methods=["POST"])
def api_extract_from_image():
    """
    Extract MRZ data from an uploaded image (web upload mode).
    NOTE: For camera capture, use /api/capture instead.
    
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
            "quality": { ... quality metrics ... },
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
        "version": "3.3.0",
        "mode": "websocket_stream",
        "target_fps": VIDEO_TARGET_FPS,
        "websocket_enabled": True,
        "model_loaded": service._model_loaded,
        "document_filler_available": service.document_filler is not None,
        "active_stream_sessions": len(service.stream_sessions),
        "tessdata_path": TESSDATA_PATH,
        "model_path": MODEL_PATH,
        "directories": {
            "captured_images": CAPTURED_IMAGES_DIR,
            "captured_json": CAPTURED_JSON_DIR,
            "document_mrz": DOCUMENT_MRZ_DIR,
            "document_filled": DOCUMENT_FILLED_DIR
        },
        "endpoints": {
            "health": "/health",
            "websocket_stream": "/api/stream/ws",
            "stream_session": "/api/stream/session",
            "stream_video_frames": "/api/stream/video/frames",
            "stream_video_chunk": "/api/stream/video",
            "stream_frame": "/api/stream/frame",
            "stream_capture": "/api/stream/capture",
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
                "given_name": "JOHN",  // Use given_name (from MRZ)
                "nationality_code": "USA",  // 3-letter code from MRZ
                "issuer_code": "USA",  // 3-letter issuing country code from MRZ
                "passport_number": "AB1234567",
                "date_of_birth": "1990-01-15",
                "expiry_date": "2030-01-15",
                "sex": "M",
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
    
    Handles both formats:
    - Direct MRZ fields: given_name, nationality_code, issuer_code, document_number
    - Legacy/UI fields: name/first_name, nationality, country, passport_number
    - Additional form fields: profession, hometown, email, phone, checkout, checkin
    """
    # Get nationality_code - prefer direct code, fallback to extracting from full name
    nationality_code = guest_data.get('nationality_code', '')
    if not nationality_code and guest_data.get('nationality'):
        # If nationality is a full name, it should already be a code from MRZ
        nat = guest_data.get('nationality', '')
        nationality_code = nat[:3].upper() if len(nat) <= 3 else nat
    
    # Get issuer_code - prefer direct code, fallback to country field
    issuer_code = guest_data.get('issuer_code', '')
    if not issuer_code:
        country = guest_data.get('country', guest_data.get('issuing_country', ''))
        if country:
            issuer_code = country[:3].upper() if len(country) <= 3 else country
    
    return {
        # Core MRZ fields
        'surname': guest_data.get('surname', ''),
        'given_name': guest_data.get('given_name', guest_data.get('name', guest_data.get('first_name', ''))),
        'nationality_code': nationality_code,
        'document_number': guest_data.get('passport_number', guest_data.get('document_number', '')),
        'birth_date': guest_data.get('date_of_birth', guest_data.get('birth_date', '')),
        'expiry_date': guest_data.get('expiry_date', ''),
        'issuer_code': issuer_code,
        # Additional guest form fields - MUST be passed to filler
        'profession': guest_data.get('profession', ''),
        'hometown': guest_data.get('hometown', ''),
        'email': guest_data.get('email', ''),
        'phone': guest_data.get('phone', ''),
        'checkout': guest_data.get('checkout', ''),
        'checkin': guest_data.get('checkin', ''),
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
    print("MRZ BACKEND MICROSERVICE v3.3.0 (WebSocket + Video Stream)")
    print("=" * 60)
    print("\n📁 Architecture:")
    print("  Layer 1: Video Stream (24fps WebSocket, zero HTTP overhead)")
    print("  Layer 2: Image Enhancer (passthrough, future: filters)")
    print("  Layer 3: MRZ Extraction (OCR, field parsing)")
    print("  Layer 4: Document Filling (PDF generation)")
    print("\n📂 Directory Structure:")
    print(f"  Logs/captured_passports/")
    print(f"    ├── captured_images/  - Processed passport images")
    print(f"    └── captured_json/    - Initial MRZ extraction JSON")
    print(f"  Logs/document_filling/")
    print(f"    ├── document_mrz/     - Finalized MRZ data (after edit)")
    print(f"    └── document_filled/  - Filled PDF documents")
    print("\n📡 API Flow (WebSocket Mode - 24fps Real-Time):")
    print("  1. WS  /api/stream/ws             - Connect WebSocket")
    print("  2. Send: {'action': 'init'}       - Initialize session")
    print("  3. Send: <binary frame>           - Send JPEG/WebP frames")
    print("  4. Recv: detection results        - Real-time feedback")
    print("  5. Send: {'action': 'capture'}    - Capture best frame")
    print("  6. Recv: MRZ data                 - Get extracted data")
    print("  7. Send: {'action': 'close'}      - Close session")
    print("\n📡 API Flow (HTTP Fallback Mode):")
    print("  1. POST /api/stream/session       - Create stream session")
    print("  2. POST /api/stream/frame         - Send single frames (loop)")
    print("  3. POST /api/stream/capture       - Capture best frame")
    print("  4. POST /api/mrz/update           - Finalize & fill document")
    print("  5. DELETE /api/stream/session     - Close session")
    print("\n📡 All Endpoints:")
    print("  GET  /health                      - Health check")
    print("  GET  /api/status                  - Service status")
    print("  WS   /api/stream/ws               - WebSocket video stream (24fps)")
    print("  POST /api/stream/session          - Create stream session")
    print("  POST /api/stream/video/frames     - Process frame batch")
    print("  POST /api/stream/frame            - Process single frame")
    print("  POST /api/stream/capture          - Capture from stream")
    print("  DEL  /api/stream/session/:id      - Close stream session")
    print("  POST /api/extract                 - Extract MRZ from upload")
    print("  POST /api/detect                  - Detect document in image")
    print("  POST /api/mrz/update              - Update MRZ & trigger doc filling")
    print("\n🧪 Test Frontend:")
    print("  GET  /                       - Test frontend with browser camera")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
