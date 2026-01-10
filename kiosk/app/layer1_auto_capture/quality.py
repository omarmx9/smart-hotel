"""
Layer 1 — Quality Assessment
Production-level image quality metrics for selecting the best frame.
Evaluates sharpness, contrast, brightness, and overall quality score.
"""
import cv2
import numpy as np
import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Container for image quality metrics."""
    sharpness: float      # Laplacian variance (higher = sharper)
    contrast: float       # Standard deviation of luminance
    brightness: float     # Mean luminance (0-255)
    edge_density: float   # Percentage of strong edges
    noise_level: float    # Estimated noise (lower = better)
    overall_score: float  # Weighted combined score
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'sharpness': round(self.sharpness, 2),
            'contrast': round(self.contrast, 2),
            'brightness': round(self.brightness, 2),
            'edge_density': round(self.edge_density, 4),
            'noise_level': round(self.noise_level, 2),
            'overall_score': round(self.overall_score, 2)
        }


class QualityAssessor:
    """
    Production-level image quality assessment.
    Evaluates multiple metrics to determine the best frame from a burst.
    """
    
    # Quality thresholds for acceptable images
    THRESHOLDS = {
        'min_sharpness': 100.0,      # Minimum Laplacian variance
        'min_contrast': 30.0,         # Minimum luminance std dev
        'optimal_brightness': 128.0,  # Target brightness (mid-gray)
        'brightness_tolerance': 60.0, # Acceptable deviation from optimal
        'min_edge_density': 0.01,     # Minimum edge percentage
        'max_noise': 15.0,            # Maximum acceptable noise level
    }
    
    # Weights for overall score calculation
    WEIGHTS = {
        'sharpness': 0.35,     # Most important for OCR
        'contrast': 0.25,      # Important for text visibility
        'brightness': 0.15,    # Moderate importance
        'edge_density': 0.15,  # Document structure indicator
        'noise': 0.10,         # Less critical but affects OCR
    }
    
    def __init__(self, thresholds: Optional[Dict] = None, weights: Optional[Dict] = None):
        """
        Initialize quality assessor.
        
        Args:
            thresholds: Optional custom thresholds
            weights: Optional custom weights for scoring
        """
        self.thresholds = {**self.THRESHOLDS, **(thresholds or {})}
        self.weights = {**self.WEIGHTS, **(weights or {})}
        logger.debug("QualityAssessor initialized")
    
    def assess(self, image: np.ndarray) -> QualityMetrics:
        """
        Assess image quality and return metrics.
        
        Args:
            image: BGR image (numpy array)
            
        Returns:
            QualityMetrics: Comprehensive quality metrics
        """
        # Convert to grayscale for analysis
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Calculate individual metrics
        sharpness = self._calculate_sharpness(gray)
        contrast = self._calculate_contrast(gray)
        brightness = self._calculate_brightness(gray)
        edge_density = self._calculate_edge_density(gray)
        noise_level = self._calculate_noise(gray)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(
            sharpness, contrast, brightness, edge_density, noise_level
        )
        
        return QualityMetrics(
            sharpness=sharpness,
            contrast=contrast,
            brightness=brightness,
            edge_density=edge_density,
            noise_level=noise_level,
            overall_score=overall_score
        )
    
    def _calculate_sharpness(self, gray: np.ndarray) -> float:
        """
        Calculate image sharpness using Laplacian variance.
        Higher values indicate sharper images.
        """
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        return float(variance)
    
    def _calculate_contrast(self, gray: np.ndarray) -> float:
        """
        Calculate contrast as standard deviation of luminance.
        Higher values indicate more contrast.
        """
        return float(np.std(gray))
    
    def _calculate_brightness(self, gray: np.ndarray) -> float:
        """
        Calculate mean brightness (0-255).
        Optimal is around 128 (mid-gray).
        """
        return float(np.mean(gray))
    
    def _calculate_edge_density(self, gray: np.ndarray) -> float:
        """
        Calculate percentage of strong edges in the image.
        Good indicator of document structure visibility.
        """
        edges = cv2.Canny(gray, 50, 150)
        edge_pixels = np.count_nonzero(edges)
        total_pixels = gray.shape[0] * gray.shape[1]
        return edge_pixels / total_pixels
    
    def _calculate_noise(self, gray: np.ndarray) -> float:
        """
        Estimate image noise level using Laplacian method.
        Lower values indicate cleaner images.
        """
        # Use median absolute deviation of Laplacian
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sigma = np.median(np.abs(laplacian)) / 0.6745
        return float(sigma)
    
    def _calculate_overall_score(
        self,
        sharpness: float,
        contrast: float,
        brightness: float,
        edge_density: float,
        noise_level: float
    ) -> float:
        """
        Calculate weighted overall quality score (0-100).
        """
        w = self.weights
        t = self.thresholds
        
        # Normalize each metric to 0-100 scale
        
        # Sharpness: logarithmic scale, capped at 1000
        sharpness_norm = min(100, (np.log10(max(sharpness, 1)) / 3) * 100)
        
        # Contrast: linear scale, capped at 80 std dev
        contrast_norm = min(100, (contrast / 80) * 100)
        
        # Brightness: penalty for deviation from optimal
        brightness_deviation = abs(brightness - t['optimal_brightness'])
        brightness_norm = max(0, 100 - (brightness_deviation / t['brightness_tolerance']) * 50)
        
        # Edge density: linear scale, good range 0.01-0.1
        edge_norm = min(100, (edge_density / 0.1) * 100)
        
        # Noise: inverse relationship, lower is better
        noise_norm = max(0, 100 - (noise_level / t['max_noise']) * 100)
        
        # Weighted sum
        score = (
            w['sharpness'] * sharpness_norm +
            w['contrast'] * contrast_norm +
            w['brightness'] * brightness_norm +
            w['edge_density'] * edge_norm +
            w['noise'] * noise_norm
        )
        
        return score
    
    def is_acceptable(self, metrics: QualityMetrics) -> Tuple[bool, str]:
        """
        Check if image quality meets minimum thresholds.
        
        Args:
            metrics: Quality metrics to evaluate
            
        Returns:
            Tuple of (is_acceptable, reason_if_rejected)
        """
        t = self.thresholds
        
        if metrics.sharpness < t['min_sharpness']:
            return False, f"Image too blurry (sharpness: {metrics.sharpness:.1f} < {t['min_sharpness']})"
        
        if metrics.contrast < t['min_contrast']:
            return False, f"Low contrast (contrast: {metrics.contrast:.1f} < {t['min_contrast']})"
        
        brightness_dev = abs(metrics.brightness - t['optimal_brightness'])
        if brightness_dev > t['brightness_tolerance']:
            direction = "dark" if metrics.brightness < t['optimal_brightness'] else "bright"
            return False, f"Image too {direction} (brightness: {metrics.brightness:.1f})"
        
        if metrics.edge_density < t['min_edge_density']:
            return False, f"Insufficient detail (edge density: {metrics.edge_density:.4f})"
        
        if metrics.noise_level > t['max_noise']:
            return False, f"Too much noise (noise: {metrics.noise_level:.1f} > {t['max_noise']})"
        
        return True, "Quality acceptable"
    
    def select_best(self, images: list, min_quality: float = 40.0) -> Tuple[Optional[np.ndarray], Optional[QualityMetrics], int]:
        """
        Select the best quality image from a list.
        
        Args:
            images: List of BGR images
            min_quality: Minimum acceptable overall score
            
        Returns:
            Tuple of (best_image, metrics, index) or (None, None, -1) if none acceptable
        """
        if not images:
            return None, None, -1
        
        best_image = None
        best_metrics = None
        best_index = -1
        best_score = -1
        
        for idx, img in enumerate(images):
            metrics = self.assess(img)
            
            if metrics.overall_score > best_score:
                best_score = metrics.overall_score
                best_image = img
                best_metrics = metrics
                best_index = idx
        
        # Check if best meets minimum quality
        if best_metrics and best_metrics.overall_score < min_quality:
            logger.warning(f"Best image quality {best_metrics.overall_score:.1f} below threshold {min_quality}")
            return None, best_metrics, -1
        
        if best_metrics:
            logger.info(f"Selected image {best_index} with quality score {best_metrics.overall_score:.1f}")
        
        return best_image, best_metrics, best_index
