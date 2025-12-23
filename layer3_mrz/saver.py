"""
Layer 3 — MRZ Extraction
Component: Image and JSON saver
Responsibility: Save captured images and extraction results for traceability
"""
import os
import json
import cv2
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ImageSaver:
    """Handles saving captured images and extraction results"""
    
    def __init__(self, base_dir="captured_passports"):
        """
        Initialize saver with new directory structure
        
        Args:
            base_dir: Base directory (default: "captured_passports")
        
        Directory structure:
            captured_passports/
            ├── captured_images/  # JPG files
            └── captured_json/    # JSON files
        """
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, "captured_images")
        self.json_dir = os.path.join(base_dir, "captured_json")
        
        # Create directories if they don't exist
        self._ensure_directories()
        
        logger.info(f"ImageSaver initialized")
        logger.debug(f"  Base dir: {base_dir}")
        logger.debug(f"  Images dir: {self.images_dir}")
        logger.debug(f"  JSON dir: {self.json_dir}")
    
    def _ensure_directories(self):
        """Create directory structure if it doesn't exist"""
        for directory in [self.base_dir, self.images_dir, self.json_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"Created directory: {directory}")
    
    def save_image(self, frame, prefix="passport"):
        """
        Save image frame to captured_images/ folder
        
        Args:
            frame: numpy.ndarray image to save
            prefix: Filename prefix (default: "passport")
        
        Returns:
            dict: Contains timestamp, filepath, filename
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.jpg"
        filepath = os.path.join(self.images_dir, filename)
        
        logger.info(f"Saving image to: {filepath}")
        cv2.imwrite(filepath, frame)
        logger.info("Image saved successfully")
        
        return {
            "timestamp": timestamp,
            "filepath": filepath,
            "filename": filename
        }
    
    def save_result_json(self, result_data, timestamp):
        """
        Save extraction result to captured_json/ folder
        
        Args:
            result_data: Dictionary containing extraction results
            timestamp: Timestamp string for filename
        
        Returns:
            str: Path to saved JSON file
        """
        json_filename = f"passport_{timestamp}.json"
        json_filepath = os.path.join(self.json_dir, json_filename)
        
        # Add metadata
        full_data = {
            **result_data,
            "capture_time": datetime.now().isoformat()
        }
        
        logger.info(f"Saving JSON to: {json_filepath}")
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)
        
        logger.info("JSON saved successfully")
        return json_filepath