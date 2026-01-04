"""
MRZ Parser Module for Hotel Kiosk
Extracted and adapted from MRZ/app/layer3_mrz for integration with Django kiosk.

This module provides passport MRZ (Machine Readable Zone) extraction functionality
for the hotel check-in kiosk flow.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Flag to track if FastMRZ is available
_fastmrz_available = False
_FastMRZ = None

try:
    from fastmrz import FastMRZ
    _FastMRZ = FastMRZ
    _fastmrz_available = True
except ImportError:
    pass


class MRZExtractionError(Exception):
    """Raised when MRZ extraction fails"""
    def __init__(self, message, details=None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class MRZNotFoundError(MRZExtractionError):
    """Raised when no MRZ data is found in the image"""
    def __init__(self):
        super().__init__(
            message="No MRZ data found in the image",
            details={"suggestion": "Ensure the passport is properly positioned and the image is clear"}
        )


class MRZParser:
    """
    Handles MRZ extraction from passport images.
    
    Falls back to mock data when FastMRZ is not available,
    making the kiosk demo-friendly.
    """
    
    # Default tessdata path relative to kiosk app
    DEFAULT_TESSDATA_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'MRZ', 'app', 'models'
    )
    
    def __init__(self, tessdata_path=None):
        """
        Initialize MRZ parser.
        
        Args:
            tessdata_path: Path to directory containing mrz.traineddata
                          Defaults to MRZ/app/models/
        """
        self.tessdata_path = tessdata_path or self.DEFAULT_TESSDATA_PATH
        self._mrz_extractor = None
        
        if _fastmrz_available:
            try:
                self._mrz_extractor = _FastMRZ(tessdata_path=self.tessdata_path)
            except Exception as e:
                pass  # Will use mock data
        
    @property
    def is_available(self):
        """Check if real MRZ extraction is available"""
        return self._mrz_extractor is not None
    
    def extract(self, image_path):
        """
        Extract MRZ data from a passport image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            dict: Extracted MRZ data with fields:
                - surname: Last name
                - given_name: First name(s)
                - nationality_code: 3-letter country code
                - document_number: Passport number
                - birth_date: Date of birth (YYMMDD or YYYY-MM-DD)
                - expiry_date: Passport expiry date
                - issuer_code: Issuing country code
                - sex: M/F
                
        Raises:
            MRZNotFoundError: If no MRZ data found
            MRZExtractionError: If extraction fails
        """
        if self._mrz_extractor is not None:
            return self._extract_real(image_path)
        else:
            return self._extract_mock(image_path)
    
    def _extract_real(self, image_path):
        """Perform real MRZ extraction using FastMRZ"""
        try:
            mrz_data = self._mrz_extractor.get_details(str(image_path))
            
            if mrz_data:
                return mrz_data
            else:
                raise MRZNotFoundError()
                
        except MRZNotFoundError:
            raise
        except Exception as e:
            raise MRZExtractionError(str(e))
    
    def _extract_mock(self, image_path):
        """Return mock MRZ data for demo purposes"""
        # Generate slightly varied mock data based on image name
        # to simulate different passport scans
        import hashlib
        hash_val = int(hashlib.md5(str(image_path).encode()).hexdigest()[:8], 16)
        
        mock_names = [
            ("John", "Doe"),
            ("Jane", "Smith"),
            ("Carlos", "Garcia"),
            ("Aisha", "Mohammed"),
            ("Yuki", "Tanaka"),
            ("Maria", "Rodriguez"),
        ]
        
        mock_nationalities = ["USA", "GBR", "FRA", "DEU", "JPN", "ESP"]
        
        idx = hash_val % len(mock_names)
        
        return {
            "surname": mock_names[idx][1].upper(),
            "given_name": mock_names[idx][0].upper(),
            "nationality_code": mock_nationalities[idx],
            "document_number": f"P{hash_val % 10000000:07d}",
            "birth_date": f"19{80 + (hash_val % 20):02d}-{(hash_val % 12) + 1:02d}-{(hash_val % 28) + 1:02d}",
            "expiry_date": f"20{28 + (hash_val % 5):02d}-{(hash_val % 12) + 1:02d}-{(hash_val % 28) + 1:02d}",
            "issuer_code": mock_nationalities[idx],
            "sex": "M" if hash_val % 2 == 0 else "F",
        }
    
    def extract_to_kiosk_format(self, image_path):
        """
        Extract MRZ data and convert to kiosk-friendly format.
        
        Returns a dict with keys matching the kiosk form fields:
            - first_name
            - last_name
            - passport_number
            - date_of_birth
            - nationality
            - nationality_code
            - expiry_date
            - sex
        """
        mrz_data = self.extract(image_path)
        
        return {
            "first_name": mrz_data.get("given_name", "").replace("<", " ").strip(),
            "last_name": mrz_data.get("surname", "").strip(),
            "passport_number": mrz_data.get("document_number", "").strip(),
            "date_of_birth": self._format_date(mrz_data.get("birth_date", "")),
            "nationality": self.get_country_name(mrz_data.get("nationality_code", "")),
            "nationality_code": mrz_data.get("nationality_code", ""),
            "expiry_date": self._format_date(mrz_data.get("expiry_date", "")),
            "sex": mrz_data.get("sex", ""),
            "issuer_country": self.get_country_name(mrz_data.get("issuer_code", "")),
            "issuer_code": mrz_data.get("issuer_code", ""),
            # Store raw MRZ data for reference
            "_raw_mrz": mrz_data,
        }
    
    def _format_date(self, date_str):
        """
        Format date from MRZ format (YYMMDD) or ISO format to YYYY-MM-DD.
        """
        if not date_str:
            return ""
        
        # Already in YYYY-MM-DD format
        if "-" in date_str and len(date_str) == 10:
            return date_str
        
        try:
            # YYMMDD format from MRZ
            if len(date_str) == 6 and date_str.isdigit():
                year = int(date_str[0:2])
                # 00-50 -> 2000-2050, 51-99 -> 1951-1999
                if year <= 50:
                    full_year = 2000 + year
                else:
                    full_year = 1900 + year
                month = date_str[2:4]
                day = date_str[4:6]
                return f"{full_year}-{month}-{day}"
            
            return date_str
        except Exception as e:
            logger.warning(f"Could not format date '{date_str}': {e}")
            return date_str
    
    @staticmethod
    def get_country_name(country_code):
        """
        Convert 3-letter ISO country code to full country name.
        """
        if not country_code:
            return ""
        
        country_map = {
            "EGY": "Egypt",
            "USA": "United States",
            "GBR": "United Kingdom",
            "FRA": "France",
            "DEU": "Germany",
            "ITA": "Italy",
            "ESP": "Spain",
            "CAN": "Canada",
            "AUS": "Australia",
            "JPN": "Japan",
            "CHN": "China",
            "IND": "India",
            "BRA": "Brazil",
            "RUS": "Russia",
            "SAU": "Saudi Arabia",
            "ARE": "United Arab Emirates",
            "TUR": "Turkey",
            "NLD": "Netherlands",
            "BEL": "Belgium",
            "CHE": "Switzerland",
            "SWE": "Sweden",
            "NOR": "Norway",
            "DNK": "Denmark",
            "POL": "Poland",
            "GRC": "Greece",
            "PRT": "Portugal",
            "AUT": "Austria",
            "CZE": "Czech Republic",
            "MEX": "Mexico",
            "ARG": "Argentina",
            "ZAF": "South Africa",
            "KOR": "South Korea",
            "SGP": "Singapore",
            "MYS": "Malaysia",
            "THA": "Thailand",
            "IDN": "Indonesia",
            "PHL": "Philippines",
            "VNM": "Vietnam",
            "NZL": "New Zealand",
            "IRL": "Ireland",
            "FIN": "Finland",
            "ISR": "Israel",
            "LBN": "Lebanon",
            "JOR": "Jordan",
            "KWT": "Kuwait",
            "QAT": "Qatar",
            "BHR": "Bahrain",
            "OMN": "Oman",
            "PAK": "Pakistan",
            "BGD": "Bangladesh",
            "LKA": "Sri Lanka",
            "MAR": "Morocco",
            "DZA": "Algeria",
            "TUN": "Tunisia",
            "SDN": "Sudan",
            "YEM": "Yemen",
            "SYR": "Syria",
            "IRQ": "Iraq",
            "IRN": "Iran",
            "AFG": "Afghanistan",
        }
        
        return country_map.get(country_code.upper(), country_code)


# Singleton instance for convenience
_parser_instance = None

def get_mrz_parser():
    """Get the singleton MRZ parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = MRZParser()
    return _parser_instance


def extract_passport_data(image_path):
    """
    Convenience function to extract passport data from an image.
    
    Returns data in kiosk-friendly format.
    """
    parser = get_mrz_parser()
    return parser.extract_to_kiosk_format(image_path)
