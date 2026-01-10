"""
Layer 1 — Auto-Capture
Production-level document auto-capture with YOLO model.
Handles camera, detection, stability tracking, quality assessment, 
and returns only the single best-quality image per session.
"""
from .auto_capture import AutoCaptureEngine, CaptureConfig, CaptureResult
from .quality import QualityAssessor, QualityMetrics
from .camera import CameraHandler

__all__ = [
    'AutoCaptureEngine', 
    'CaptureConfig', 
    'CaptureResult',
    'QualityAssessor', 
    'QualityMetrics',
    'CameraHandler'
]
