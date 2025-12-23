"""
Layer 3 — MRZ Extraction
Component: MRZ extractor
Responsibility: Extract and validate MRZ data from images
"""
import logging
from fastmrz import FastMRZ

logger = logging.getLogger(__name__)


class MRZExtractor:
    """Handles MRZ extraction from passport images"""
    
    def __init__(self, tessdata_path):
        """
        Initialize MRZ extractor
        
        Args:
            tessdata_path: Path to Tesseract data files
        """
        logger.info("Initializing MRZExtractor")
        logger.debug(f"Tessdata path: {tessdata_path}")
        
        self.fast_mrz = FastMRZ(tessdata_path=tessdata_path)
        logger.info("MRZExtractor initialized successfully")
    
    def extract(self, image_path):
        """
        Extract MRZ data from image
        
        Args:
            image_path: Path to the image file
        
        Returns:
            dict: Extracted MRZ data, or None if extraction failed
        """
        logger.info("Starting MRZ extraction...")
        logger.debug(f"Image path: {image_path}")
        
        try:
            mrz_data = self.fast_mrz.get_details(image_path)
            
            if mrz_data:
                logger.info("✓ MRZ extraction successful!")
                logger.info("Extracted data:")
                for key, value in mrz_data.items():
                    logger.info(f"  {key}: {value}")
                
                return mrz_data
            else:
                logger.warning("No MRZ data found in image")
                return None
                
        except Exception as e:
            logger.error(f"Error during MRZ extraction: {e}")
            logger.exception("Full traceback:")
            raise