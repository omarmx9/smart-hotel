"""
MRZ Backend Microservice v3.1
Production API service for MRZ extraction with WebRTC stream support.

Architecture:
- Layer 1: Auto-Capture (YOLO-based document detection, quality assessment)
- Layer 2: Image Enhancer (passthrough now, filters/enhancers later)
- Layer 3: MRZ Extraction (OCR, field parsing)
- Layer 4: Document Filling (PDF generation)

Provides REST API for:
- WebRTC stream frame processing (browser sends frames via base64)
- Real-time document detection and corner tracking
- MRZ extraction from captured/uploaded images
- Quality assessment and best-frame selection
- Document filling (PDF) - triggered after MRZ confirmation

NOTE: This is a pure BACKEND service. Camera is browser-based via WebRTC.
The frontend captures frames and sends them to this backend for processing.
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
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

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
        logger.info("Initializing MRZBackendService v3.1 (WebRTC Backend)")
        
        # Layer 1: YOLO model for document detection
        self.model = None
        self.model_path = model_path or MODEL_PATH
        self._model_loaded = False
        
        # Stream sessions (keyed by session_id)
        self.stream_sessions: Dict[str, StreamSession] = {}
        
        # Layer 2: Image Enhancer (passthrough for now)
        self.image_enhancer = ImageBridge()
        
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
    
    def _detect_corners(self, frame: np.ndarray) -> Tuple[Optional[List[Tuple[float, float]]], float]:
        """
        Detect document corners using YOLO model.
        
        Args:
            frame: BGR image from WebRTC stream
            
        Returns:
            Tuple of (corners, confidence) or (None, 0) if not detected
        """
        if not self._model_loaded or self.model is None:
            return None, 0.0
        
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
            logger.error(f"Detection error: {e}")
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
        Process a frame from WebRTC stream.
        
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
            
            # Detect corners
            corners, confidence = self._detect_corners(frame)
            
            result = {
                "detected": corners is not None,
                "confidence": confidence,
                "corners": corners,
                "stable_count": session.stable_count,
                "stable_required": STABILITY_FRAMES,
                "ready_for_capture": False
            }
            
            if corners is None:
                session.reset_stability()
                return result
            
            # Check stability
            if self._corners_stable(corners, session.prev_corners):
                session.stable_count += 1
                
                # Collect burst frame only when approaching stability
                # This avoids expensive quality assessment on every frame
                if session.stable_count >= STABILITY_FRAMES // 2:
                    warped = self._perspective_crop(frame, corners)
                    quality = self.quality_assessor.assess(warped)
                    
                    if quality.overall_score > session.best_quality:
                        session.best_quality = quality.overall_score
                        session.best_frame = warped
                    
                    # Only keep burst frames if under limit
                    if len(session.burst_frames) < MAX_BURST_FRAMES:
                        session.burst_frames.append(warped)
                
                if session.stable_count >= STABILITY_FRAMES:
                    result["ready_for_capture"] = True
            else:
                # Reset on instability
                session.stable_count = 0
                session.burst_frames.clear()  # More efficient than creating new list
                session.best_frame = None
                session.best_quality = 0.0
            
            session.prev_corners = corners
            result["stable_count"] = session.stable_count
            result["quality_score"] = session.best_quality
            
            return result
            
        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return {"error": str(e), "detected": False}
    
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

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for service discovery and load balancers"""
    return jsonify({
        "status": "healthy",
        "service": "mrz-backend",
        "version": "3.1.0",
        "mode": "webrtc",
        "capabilities": [
            "webrtc_stream",
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
    
    Request (application/json):
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
    if not request.is_json:
        return jsonify({"error": "JSON body required", "detected": False}), 400
    
    data = request.get_json()
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
        "version": "3.1.0",
        "mode": "webrtc",
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
            "stream_session": "/api/stream/session",
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
    print("MRZ BACKEND MICROSERVICE v3.1.0 (WebRTC Mode)")
    print("=" * 60)
    print("\n📁 Architecture:")
    print("  Layer 1: WebRTC Stream (browser camera, YOLO detection)")
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
    print("\n📡 API Flow (WebRTC Stream Mode):")
    print("  1. POST /api/stream/session   - Create stream session")
    print("  2. POST /api/stream/frame     - Send frames (loop)")
    print("  3. Wait for ready_for_capture = true")
    print("  4. POST /api/stream/capture   - Capture best frame")
    print("  5. [User can edit MRZ in frontend]")
    print("  6. POST /api/mrz/update       - Finalize & fill document")
    print("  7. DELETE /api/stream/session - Close session")
    print("\n📡 API Flow (Web Upload Mode):")
    print("  1. POST /api/extract         - Extract MRZ from uploaded image")
    print("  2. [User can edit MRZ in frontend]")
    print("  3. POST /api/mrz/update      - Finalize & fill document")
    print("\n📡 All Endpoints:")
    print("  GET  /health                 - Health check")
    print("  GET  /api/status             - Service status")
    print("  POST /api/stream/session     - Create stream session")
    print("  POST /api/stream/frame       - Process stream frame")
    print("  POST /api/stream/capture     - Capture from stream")
    print("  DEL  /api/stream/session/:id - Close stream session")
    print("  POST /api/extract            - Extract MRZ from upload (web)")
    print("  POST /api/detect             - Detect document in image")
    print("  POST /api/mrz/update         - Update MRZ & trigger doc filling")
    print("  POST /api/document/preview   - Get document preview HTML")
    print("\n🧪 Test Frontend:")
    print("  GET  /                       - Test frontend with browser camera")
    print("\n" + "=" * 60)
    print("Server starting... Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    logger.info("Flask server starting")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
