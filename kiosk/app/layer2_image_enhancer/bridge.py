"""
Layer 2 — Image Bridge
Passthrough layer with optional quality enhancements.

This layer sits between auto-capture (Layer 1) and MRZ extraction (Layer 3).
Currently acts as a passthrough with minimal processing.

Future Enhancement Options:
- High-resolution upscaling using INTER_LANCZOS4
- Subtle sharpening with unsharp mask
- CLAHE contrast enhancement
- Bilateral filtering for noise reduction
- Color space optimization for OCR
"""
import cv2
import numpy as np
import logging
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EnhancementConfig:
    """Configuration for image enhancements."""
    # Upscaling
    enable_upscaling: bool = False
    target_width: int = 1800        # Target width for upscaling
    upscale_method: int = cv2.INTER_LANCZOS4  # Best quality interpolation
    
    # Sharpening
    enable_sharpening: bool = False
    sharpen_amount: float = 0.3     # Subtle sharpening (0.0 - 1.0)
    sharpen_radius: float = 1.0     # Gaussian blur radius for unsharp mask
    
    # Contrast enhancement
    enable_contrast: bool = False
    clahe_clip_limit: float = 2.0   # CLAHE clip limit
    clahe_grid_size: Tuple[int, int] = (8, 8)
    
    # Denoising
    enable_denoise: bool = False
    denoise_strength: int = 10      # fastNlMeans h parameter


class ImageBridge:
    """
    Image processing bridge between capture and MRZ extraction.
    
    Acts as passthrough by default. Enable enhancements as needed.
    All enhancements are designed to preserve document quality for OCR.
    """
    
    def __init__(self, config: Optional[EnhancementConfig] = None):
        """
        Initialize image bridge.
        
        Args:
            config: Enhancement configuration (passthrough if None)
        """
        self.config = config or EnhancementConfig()
        self._enhancement_stats = {
            'images_processed': 0,
            'enhancements_applied': []
        }
        
        logger.info("ImageBridge initialized")
        logger.debug(f"Enhancements enabled: upscale={self.config.enable_upscaling}, "
                    f"sharpen={self.config.enable_sharpening}, "
                    f"contrast={self.config.enable_contrast}, "
                    f"denoise={self.config.enable_denoise}")
    
    def process(self, image: np.ndarray) -> np.ndarray:
        """
        Process image through the bridge with optional enhancements.
        
        Args:
            image: Input BGR image from Layer 1
            
        Returns:
            Processed image ready for Layer 3 (MRZ extraction)
        """
        if image is None:
            logger.warning("Received None image, returning as-is")
            return image
        
        result = image.copy()
        applied = []
        
        cfg = self.config
        
        # Step 1: Upscaling (if enabled and needed)
        if cfg.enable_upscaling:
            result = self._upscale(result)
            applied.append('upscale')
        
        # Step 2: Contrast enhancement (if enabled)
        if cfg.enable_contrast:
            result = self._enhance_contrast(result)
            applied.append('contrast')
        
        # Step 3: Denoising (if enabled)
        if cfg.enable_denoise:
            result = self._denoise(result)
            applied.append('denoise')
        
        # Step 4: Sharpening (if enabled, always last)
        if cfg.enable_sharpening:
            result = self._sharpen(result)
            applied.append('sharpen')
        
        # Track statistics
        self._enhancement_stats['images_processed'] += 1
        if applied:
            self._enhancement_stats['enhancements_applied'].append(applied)
            logger.debug(f"Applied enhancements: {applied}")
        
        return result
    
    def _upscale(self, image: np.ndarray) -> np.ndarray:
        """
        Upscale image to target width using high-quality interpolation.
        Preserves aspect ratio.
        """
        h, w = image.shape[:2]
        
        if w >= self.config.target_width:
            # Already at or above target size
            return image
        
        scale = self.config.target_width / w
        new_h = int(h * scale)
        new_w = self.config.target_width
        
        upscaled = cv2.resize(
            image,
            (new_w, new_h),
            interpolation=self.config.upscale_method
        )
        
        logger.debug(f"Upscaled: {w}x{h} -> {new_w}x{new_h}")
        return upscaled
    
    def _sharpen(self, image: np.ndarray) -> np.ndarray:
        """
        Apply subtle unsharp mask sharpening.
        Designed to enhance text edges without creating artifacts.
        """
        cfg = self.config
        
        # Create Gaussian blur
        blur = cv2.GaussianBlur(image, (0, 0), cfg.sharpen_radius)
        
        # Unsharp mask: original + amount * (original - blur)
        sharpened = cv2.addWeighted(
            image, 1.0 + cfg.sharpen_amount,
            blur, -cfg.sharpen_amount,
            0
        )
        
        return sharpened
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).
        Enhances local contrast for better text visibility.
        """
        cfg = self.config
        
        # Convert to LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(
            clipLimit=cfg.clahe_clip_limit,
            tileGridSize=cfg.clahe_grid_size
        )
        l_enhanced = clahe.apply(l)
        
        # Merge and convert back
        lab_enhanced = cv2.merge([l_enhanced, a, b])
        result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
        
        return result
    
    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """
        Apply fast non-local means denoising.
        Reduces noise while preserving edges.
        """
        # cv2.fastNlMeansDenoisingColored(src, dst, h, hForColorComponents, templateWindowSize, searchWindowSize)
        # dst=None means output to new array
        denoised = cv2.fastNlMeansDenoisingColored(
            src=image,
            dst=None,
            h=self.config.denoise_strength,
            hColor=self.config.denoise_strength,
            templateWindowSize=7,
            searchWindowSize=21
        )
        
        return denoised
    
    def enable_all_enhancements(self):
        """Enable all enhancement options."""
        self.config.enable_upscaling = True
        self.config.enable_sharpening = True
        self.config.enable_contrast = True
        self.config.enable_denoise = True
        logger.info("All enhancements enabled")
    
    def disable_all_enhancements(self):
        """Disable all enhancements (passthrough mode)."""
        self.config.enable_upscaling = False
        self.config.enable_sharpening = False
        self.config.enable_contrast = False
        self.config.enable_denoise = False
        logger.info("All enhancements disabled (passthrough mode)")
    
    def get_stats(self) -> Dict:
        """Get processing statistics."""
        return self._enhancement_stats.copy()
    
    def passthrough(self, image: np.ndarray) -> np.ndarray:
        """
        Direct passthrough without any processing.
        Use when you want to bypass all enhancements.
        """
        return image
