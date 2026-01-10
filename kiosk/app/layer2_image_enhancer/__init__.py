"""
Layer 2 — Image Enhancer
Passthrough layer for image quality enhancement.

Currently acts as a passthrough - passes images through with minimal processing.
Future enhancements (to be added after testing):
- High-resolution upscaling (INTER_LANCZOS4)
- Adaptive sharpening
- Color correction
- Noise reduction
- Contrast optimization
- Document-specific filters
"""
from .bridge import ImageBridge, EnhancementConfig

__all__ = ['ImageBridge', 'EnhancementConfig']
