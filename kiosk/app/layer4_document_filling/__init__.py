"""
Layer 4 — Document Filling
Handles automated filling of registration card templates
"""
from .filler import (
    DocumentFiller,
    DocumentFillingError,
    TemplateNotFoundError,
    TemplateSaveError
)

__all__ = [
    'DocumentFiller',
    'DocumentFillingError',
    'TemplateNotFoundError',
    'TemplateSaveError'
]