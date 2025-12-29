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
                 min_area_percentage=8.0,
                 max_area_percentage=85.0,
                 enhance_contrast=True,
                 preview_scale=0.5,
                 output_width=1200,
                 output_height=800):
        """
        Initialize document processor
        
        Args:
            min_area_percentage: Minimum document area as % of frame (default: 8%)
            max_area_percentage: Maximum document area as % of frame (default: 85%)
            enhance_contrast: Apply contrast enhancement (default: True)
            preview_scale: Scale factor for preview detection (0.5 = 50% size for speed)
            output_width: Width of warped output document (default: 1200px, A4-like aspect)
            output_height: Height of warped output document (default: 800px)
        """
        self.min_area_percentage = min_area_percentage
        self.max_area_percentage = max_area_percentage
        self.enhance_contrast = enhance_contrast
        self.preview_scale = preview_scale
        self.output_width = output_width
        self.output_height = output_height
        
        logger.info("DocumentProcessor initialized")
        logger.debug(f"  Min area percentage: {min_area_percentage}%")
        logger.debug(f"  Max area percentage: {max_area_percentage}%")
        logger.debug(f"  Enhance contrast: {enhance_contrast}")
        logger.debug(f"  Preview scale: {preview_scale}")
        logger.debug(f"  Output dimensions: {output_width}x{output_height}")
    
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
        Fast document detection using HYBRID approach:
        1. Color-based segmentation (passports have distinct colors)
        2. Edge detection as backup
        3. Contour finding and quadrilateral extraction
        
        Args:
            frame: Input image (full resolution)
            
        Returns:
            numpy.ndarray: Document contour (4 corners) scaled back to original size, or None
        """
        # Downscale for speed
        height, width = frame.shape[:2]
        frame_area = height * width
        small_width = int(width * self.preview_scale)
        small_height = int(height * self.preview_scale)
        small_frame = cv2.resize(frame, (small_width, small_height))
        small_area = small_width * small_height
        
        # METHOD 1: Try color-based detection first (passports are usually dark blue/red/green)
        hsv = cv2.cvtColor(small_frame, cv2.COLOR_BGR2HSV)
        
        # Create mask for common passport colors
        # Blue passports (most common)
        lower_blue = np.array([90, 30, 30])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Red passports
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
        
        # Green passports
        lower_green = np.array([35, 40, 40])
        upper_green = np.array([85, 255, 255])
        mask_green = cv2.inRange(hsv, lower_green, upper_green)
        
        # Combine all color masks
        color_mask = mask_blue | mask_red | mask_green
        
        # Clean up the mask
        kernel = np.ones((5, 5), np.uint8)
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel, iterations=2)
        
        # Find contours from color mask
        contours_color, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # METHOD 2: Edge-based detection as backup
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 20, 80)
        
        # Aggressive dilation
        kernel_large = np.ones((7, 7), np.uint8)
        dilated = cv2.dilate(edges, kernel_large, iterations=3)
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel_large, iterations=2)
        
        contours_edge, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Combine both methods
        all_contours = list(contours_color) + list(contours_edge)
        
        if not all_contours:
            return None
        
        # Sort by area
        all_contours = sorted(all_contours, key=cv2.contourArea, reverse=True)
        
        # Lower threshold for detection
        min_area = small_area * (self.min_area_percentage / 100.0)
        max_area = small_area * (self.max_area_percentage / 100.0)
        
        # Find quadrilateral
        for contour in all_contours[:20]:
            area = cv2.contourArea(contour)
            
            if area < min_area or area > max_area:
                continue
            
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)  # Tighter approximation
            
            if len(approx) == 4:
                if self._is_valid_quadrilateral_lenient(approx):
                    scale_factor = 1.0 / self.preview_scale
                    scaled_contour = (approx * scale_factor).astype(np.int32)
                    return scaled_contour
        
        return None
    
    def _is_valid_quadrilateral_lenient(self, quad):
        """
        More precise quadrilateral validation for better accuracy
        
        Args:
            quad: 4-point contour
            
        Returns:
            bool: True if valid rectangular shape
        """
        points = quad.reshape(4, 2)
        
        # Calculate angles between consecutive edges
        angles = []
        for i in range(4):
            p1 = points[i]
            p2 = points[(i + 1) % 4]
            p3 = points[(i + 2) % 4]
            
            v1 = p1 - p2
            v2 = p3 - p2
            
            cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
            angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
            angles.append(np.degrees(angle))
        
        # Tighter validation: angles between 60-120 degrees (more rectangular)
        for angle in angles:
            if angle < 60 or angle > 120:
                return False
        
        # Check aspect ratio (passports are roughly 1.4:1)
        # Calculate width and height
        widths = [
            np.linalg.norm(points[1] - points[0]),
            np.linalg.norm(points[2] - points[3])
        ]
        heights = [
            np.linalg.norm(points[3] - points[0]),
            np.linalg.norm(points[2] - points[1])
        ]
        
        avg_width = np.mean(widths)
        avg_height = np.mean(heights)
        
        if avg_width == 0 or avg_height == 0:
            return False
        
        aspect_ratio = max(avg_width, avg_height) / min(avg_width, avg_height)
        
        # Passport aspect ratio should be between 1.2 and 1.8
        if aspect_ratio < 1.2 or aspect_ratio > 1.8:
            return False
        
        return True
    
    def _is_valid_quadrilateral(self, quad):
        """
        Strict quadrilateral validation for capture processing
        Ensures high-quality rectangular detection
        
        Args:
            quad: 4-point contour
            
        Returns:
            bool: True if valid
        """
        points = quad.reshape(4, 2)
        
        # Calculate angles between consecutive edges
        angles = []
        for i in range(4):
            p1 = points[i]
            p2 = points[(i + 1) % 4]
            p3 = points[(i + 2) % 4]
            
            v1 = p1 - p2
            v2 = p3 - p2
            
            cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
            angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
            angles.append(np.degrees(angle))
        
        # Strict: angles between 70-110 degrees (very rectangular)
        for angle in angles:
            if angle < 70 or angle > 110:
                return False
        
        # Check aspect ratio
        widths = [
            np.linalg.norm(points[1] - points[0]),
            np.linalg.norm(points[2] - points[3])
        ]
        heights = [
            np.linalg.norm(points[3] - points[0]),
            np.linalg.norm(points[2] - points[1])
        ]
        
        avg_width = np.mean(widths)
        avg_height = np.mean(heights)
        
        if avg_width == 0 or avg_height == 0:
            return False
        
        aspect_ratio = max(avg_width, avg_height) / min(avg_width, avg_height)
        
        # Stricter aspect ratio for capture: 1.3-1.6 (typical passport)
        if aspect_ratio < 1.3 or aspect_ratio > 1.6:
            return False
        
        return True
    
    def _detect_document(self, frame):
        """
        Full-quality document detection for capture processing
        More aggressive edge linking to capture full passport boundary
        
        Args:
            frame: Input image (full resolution)
            
        Returns:
            numpy.ndarray: Document contour (4 corners) or None if not found
        """
        height, width = frame.shape[:2]
        frame_area = height * width
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply bilateral filter
        filtered = cv2.bilateralFilter(gray, 11, 100, 100)
        
        # More aggressive edge detection (lower thresholds)
        edges = cv2.Canny(filtered, 30, 120)
        
        # AGGRESSIVE dilation to connect broken passport edges
        kernel = np.ones((9, 9), np.uint8)  # Large kernel
        dilated = cv2.dilate(edges, kernel, iterations=4)  # Many iterations
        
        # Close operation to fill gaps
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel, iterations=3)
        
        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.debug("No contours found")
            return None
        
        # Sort contours by area (largest first)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        
        # Calculate area thresholds
        min_area = frame_area * (self.min_area_percentage / 100.0)
        max_area = frame_area * (self.max_area_percentage / 100.0)
        
        logger.debug(f"Searching {len(contours)} contours, area range: {min_area:.0f}-{max_area:.0f}")
        
        # Find the largest valid quadrilateral
        for idx, contour in enumerate(contours[:15]):  # Check top 15
            area = cv2.contourArea(contour)
            
            if area < min_area:
                logger.debug(f"Contour {idx+1}: area {area:.0f} too small")
                continue
            if area > max_area:
                logger.debug(f"Contour {idx+1}: area {area:.0f} too large")
                continue
            
            # Polygon approximation with slightly higher tolerance
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
            
            logger.debug(f"Contour {idx+1}: area {area:.0f} ({(area/frame_area)*100:.1f}%), {len(approx)} corners")
            
            # Must be quadrilateral
            if len(approx) == 4:
                if self._is_valid_quadrilateral(approx):
                    logger.debug(f"✓ Valid quadrilateral found!")
                    return approx
                else:
                    logger.debug(f"  Rejected: angles too extreme")
        
        logger.debug("No valid quadrilateral found")
        return None
    
    def _correct_perspective(self, frame, contour):
        """
        Apply 4-point perspective transform to create flat A4-like document
        MOST IMPORTANT: Warps skewed document to perfect rectangular view
        
        Args:
            frame: Input image
            contour: Document contour (4 corners)
            
        Returns:
            numpy.ndarray: Perspective-corrected flat document
        """
        # Get the 4 corner points
        points = contour.reshape(4, 2).astype(np.float32)
        
        # Order points consistently: top-left, top-right, bottom-right, bottom-left
        rect = self._order_points(points)
        (tl, tr, br, bl) = rect
        
        # Calculate the width of the new image
        # Use maximum of top and bottom edge lengths
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))
        
        # Calculate the height of the new image
        # Use maximum of left and right edge lengths
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))
        
        # Override with fixed output dimensions for consistent A4-like output
        # This ensures all warped documents have the same size
        output_width = self.output_width
        output_height = self.output_height
        
        # Destination points for perfect rectangle
        dst = np.array([
            [0, 0],                                    # Top-left
            [output_width - 1, 0],                    # Top-right
            [output_width - 1, output_height - 1],    # Bottom-right
            [0, output_height - 1]                    # Bottom-left
        ], dtype=np.float32)
        
        # Compute perspective transform matrix
        M = cv2.getPerspectiveTransform(rect, dst)
        
        # Apply warp perspective to get flat, rectangular document
        warped = cv2.warpPerspective(frame, M, (output_width, output_height))
        
        logger.debug(f"Perspective corrected: {maxWidth}x{maxHeight} → {output_width}x{output_height} (A4-like)")
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