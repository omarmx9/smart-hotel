"""
Layer 2 – Image Readjustment
Responsibility: Document detection, perspective correction, MRZ region isolation
Output: Preprocessed image optimized for OCR
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Advanced document image preprocessing for passport MRZ extraction
    """
    
    def __init__(self, 
                 min_area=50000,
                 max_area=2000000,
                 enhance_contrast=True,
                 preview_scale=0.5):
        """
        Initialize document processor
        
        Args:
            min_area: Minimum contour area for document detection
            max_area: Maximum contour area for document detection
            enhance_contrast: Apply contrast enhancement (default: True)
            preview_scale: Scale factor for preview detection (0.5 = 50% size for speed)
        """
        self.min_area = min_area
        self.max_area = max_area
        self.enhance_contrast = enhance_contrast
        self.preview_scale = preview_scale
        
        logger.info("DocumentProcessor initialized")
        logger.debug(f"  Min area: {min_area}")
        logger.debug(f"  Max area: {max_area}")
        logger.debug(f"  Enhance contrast: {enhance_contrast}")
        logger.debug(f"  Preview scale: {preview_scale}")
    
    def process(self, frame):
        """
        Process document image with full preprocessing pipeline
        
        Args:
            frame: numpy.ndarray from Layer 1 (raw camera capture)
        
        Returns:
            numpy.ndarray: Preprocessed image ready for MRZ extraction
            
        Pipeline:
        1. Document detection
        2. Perspective correction
        3. Contrast enhancement
        4. Denoising
        """
        logger.info("Starting document processing pipeline")
        
        try:
            # Step 1: Detect document boundaries
            logger.debug("Step 1: Detecting document boundaries")
            contour = self._detect_document(frame)
            
            if contour is None:
                logger.warning("Document detection failed, using full frame")
                processed = frame
            else:
                # Step 2: Apply perspective correction
                logger.debug("Step 2: Applying perspective correction")
                processed = self._correct_perspective(frame, contour)
            
            # Step 3: Enhance contrast for better OCR
            if self.enhance_contrast:
                logger.debug("Step 3: Enhancing contrast")
                processed = self._enhance_contrast(processed)
            
            # Step 4: Denoise
            logger.debug("Step 4: Applying denoising")
            processed = self._denoise(processed)
            
            logger.info("✓ Document processing completed successfully")
            logger.debug(f"  Output shape: {processed.shape}")
            
            return processed
            
        except Exception as e:
            logger.error(f"Error in processing pipeline: {e}")
            logger.exception("Full traceback:")
            # Return original frame as fallback
            return frame
    
    def _detect_document_fast(self, frame):
        """
        Fast document detection optimized for real-time preview
        Uses downscaled image and simplified processing
        
        Args:
            frame: Input image (full resolution)
            
        Returns:
            numpy.ndarray: Document contour (4 corners) scaled back to original size, or None
        """
        # Downscale for speed
        height, width = frame.shape[:2]
        small_width = int(width * self.preview_scale)
        small_height = int(height * self.preview_scale)
        small_frame = cv2.resize(frame, (small_width, small_height))
        
        # Convert to grayscale
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        
        # Simple blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection with relaxed parameters
        edges = cv2.Canny(blurred, 30, 100)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Sort by area
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        
        # Adjust area thresholds for scaled image
        scaled_min_area = self.min_area * (self.preview_scale ** 2)
        scaled_max_area = self.max_area * (self.preview_scale ** 2)
        
        # Find document contour
        for contour in contours[:5]:  # Check top 5 only
            area = cv2.contourArea(contour)
            
            if scaled_min_area < area < scaled_max_area:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                if len(approx) == 4:
                    # Scale contour back to original size
                    scale_factor = 1.0 / self.preview_scale
                    scaled_contour = (approx * scale_factor).astype(np.int32)
                    return scaled_contour
        
        return None
    
    def _detect_document(self, frame):
        """
        Detect passport document boundaries using edge detection and contour analysis
        
        Args:
            frame: Input image
            
        Returns:
            numpy.ndarray: Document contour (4 corners) or None if not found
        """
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection
        edges = cv2.Canny(blurred, 50, 150)
        
        # Dilate edges to close gaps
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Sort contours by area (largest first)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        
        # Find the largest rectangular contour (likely the passport)
        for contour in contours[:10]:  # Check top 10 largest contours
            area = cv2.contourArea(contour)
            
            # Check if area is within expected range
            if self.min_area < area < self.max_area:
                # Approximate contour to polygon
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # Passport should have 4 corners
                if len(approx) == 4:
                    logger.debug(f"Document detected with area: {area:.0f}")
                    return approx
        
        logger.debug("No suitable document contour found")
        return None
    
    def _correct_perspective(self, frame, contour):
        """
        Apply 4-point perspective transform to correct document angle
        
        Args:
            frame: Input image
            contour: Document contour (4 corners)
            
        Returns:
            numpy.ndarray: Perspective-corrected image
        """
        # Get the 4 corner points
        points = contour.reshape(4, 2)
        
        # Order points: top-left, top-right, bottom-right, bottom-left
        rect = self._order_points(points)
        (tl, tr, br, bl) = rect
        
        # Calculate width of the new image
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))
        
        # Calculate height of the new image
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))
        
        # Destination points for the transform
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]
        ], dtype="float32")
        
        # Compute perspective transform matrix
        M = cv2.getPerspectiveTransform(rect, dst)
        
        # Apply the transform
        warped = cv2.warpPerspective(frame, M, (maxWidth, maxHeight))
        
        logger.debug(f"Perspective corrected to {maxWidth}x{maxHeight}")
        return warped
    
    def _order_points(self, pts):
        """
        Order points in consistent order: top-left, top-right, bottom-right, bottom-left
        
        Args:
            pts: Array of 4 points
            
        Returns:
            numpy.ndarray: Ordered points
        """
        rect = np.zeros((4, 2), dtype="float32")
        
        # Sum and difference to find corners
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)
        
        rect[0] = pts[np.argmin(s)]      # Top-left (smallest sum)
        rect[2] = pts[np.argmax(s)]      # Bottom-right (largest sum)
        rect[1] = pts[np.argmin(diff)]   # Top-right (smallest difference)
        rect[3] = pts[np.argmax(diff)]   # Bottom-left (largest difference)
        
        return rect
    
    def _enhance_contrast(self, frame):
        """
        Enhance image contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        
        Args:
            frame: Input image
            
        Returns:
            numpy.ndarray: Contrast-enhanced image
        """
        # Convert to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_clahe = clahe.apply(l)
        
        # Merge channels
        lab_clahe = cv2.merge([l_clahe, a, b])
        
        # Convert back to BGR
        enhanced = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2BGR)
        
        return enhanced
    
    def _denoise(self, frame):
        """
        Apply denoising to reduce background noise
        
        Args:
            frame: Input image
            
        Returns:
            numpy.ndarray: Denoised image
        """
        # Use fastNlMeansDenoisingColored for color images
        denoised = cv2.fastNlMeansDenoisingColored(
            frame,
            None,
            h=10,              # Filter strength for luminance
            hColor=10,         # Filter strength for color
            templateWindowSize=7,
            searchWindowSize=21
        )
        
        return denoised
    
    def get_preview_with_overlay(self, frame):
        """
        Generate live preview with document detection overlay (FAST VERSION)
        Optimized for real-time 30fps performance
        
        Args:
            frame: Input image
            
        Returns:
            tuple: (overlay_frame, detection_info)
                - overlay_frame: Frame with visual overlay
                - detection_info: Dict with detection status and metrics
        """
        overlay_frame = frame.copy()
        
        # Use fast detection for preview
        contour = self._detect_document_fast(frame)
        
        detection_info = {
            "detected": False,
            "area": 0,
            "area_percentage": 0.0,
            "corners": 4 if contour is not None else 0
        }
        
        if contour is not None:
            # Calculate area metrics
            area = cv2.contourArea(contour)
            frame_area = frame.shape[0] * frame.shape[1]
            area_percentage = (area / frame_area) * 100
            
            detection_info.update({
                "detected": True,
                "area": int(area),
                "area_percentage": round(area_percentage, 2),
                "corners": 4
            })
            
            # Draw thick green contour
            cv2.drawContours(overlay_frame, [contour], -1, (0, 255, 0), 6)
            
            # Draw corner circles
            for point in contour.reshape(-1, 2):
                cv2.circle(overlay_frame, tuple(point), 12, (0, 255, 0), -1)
                cv2.circle(overlay_frame, tuple(point), 12, (255, 255, 255), 2)
            
            # Add semi-transparent overlay effect (optional)
            overlay = overlay_frame.copy()
            cv2.fillPoly(overlay, [contour], (0, 255, 0))
            cv2.addWeighted(overlay, 0.1, overlay_frame, 0.9, 0, overlay_frame)
            
            # Status text with background
            status_text = f"DOCUMENT DETECTED - {area_percentage:.1f}%"
            text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
            
            # Draw background rectangle
            cv2.rectangle(overlay_frame, (10, 10), (text_size[0] + 30, 60), 
                         (0, 255, 0), -1)
            cv2.rectangle(overlay_frame, (10, 10), (text_size[0] + 30, 60), 
                         (255, 255, 255), 2)
            
            # Draw text
            cv2.putText(overlay_frame, status_text, (20, 45), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
            
        else:
            # No document - minimal text
            status_text = "Position passport in frame"
            text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
            
            # Draw background
            cv2.rectangle(overlay_frame, (10, 10), (text_size[0] + 30, 55), 
                         (50, 50, 50), -1)
            cv2.rectangle(overlay_frame, (10, 10), (text_size[0] + 30, 55), 
                         (200, 200, 200), 2)
            
            # Draw text
            cv2.putText(overlay_frame, status_text, (20, 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        return overlay_frame, detection_info
    
    def get_debug_visualization(self, frame):
        """
        Generate visualization showing processing steps (useful for debugging)
        
        Args:
            frame: Input image
            
        Returns:
            numpy.ndarray: Visualization with processing steps
        """
        # Use the overlay method
        overlay_frame, _ = self.get_preview_with_overlay(frame)
        return overlay_frame