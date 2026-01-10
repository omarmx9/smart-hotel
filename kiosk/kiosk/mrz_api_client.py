"""
MRZ API Client
Communicates with the MRZ backend microservice for passport MRZ extraction.

NOTE: The MRZ backend is now a pure API service. Camera capture is handled
by the browser (WebRTC) and images are sent to this service for processing.
"""

import logging
import os
import requests
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Default MRZ service URL - can be overridden via environment variable
MRZ_SERVICE_URL = os.environ.get('MRZ_SERVICE_URL', 'http://mrz-backend:5000')


class MRZAPIError(Exception):
    """Raised when MRZ API request fails"""
    def __init__(self, message, error_code=None, details=None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class MRZAPIClient:
    """
    Client for communicating with the MRZ backend microservice.
    
    The MRZ backend handles:
    - Document detection (for auto-capture)
    - MRZ extraction from images
    - Document filling (PDF)
    
    NOTE: Camera capture is handled by the browser, not the backend.
    """
    
    def __init__(self, base_url: str = None, timeout: int = 30):
        """
        Initialize MRZ API client.
        
        Args:
            base_url: Base URL of the MRZ service. Defaults to MRZ_SERVICE_URL env var.
            timeout: Request timeout in seconds.
        """
        self.base_url = (base_url or MRZ_SERVICE_URL).rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        logger.info(f"MRZ API Client initialized with base URL: {self.base_url}")
    
    def health_check(self) -> bool:
        """
        Check if the MRZ service is healthy.
        
        Returns:
            bool: True if service is healthy, False otherwise.
        """
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"MRZ service health check failed: {e}")
            return False
    
    def detect_document(self, image_data: str) -> dict:
        """
        Detect if a document is present in the image.
        Used for auto-capture functionality.
        
        Args:
            image_data: Base64 encoded image data.
        
        Returns:
            dict: Detection result with 'detected', 'confidence', 'ready_for_capture'.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/detect",
                json={'image': image_data},
                timeout=self.timeout
            )
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to detect document: {e}")
            return {'detected': False, 'error': str(e)}
    
    def extract_from_base64(self, image_data: str, filename: str = "passport.jpg") -> dict:
        """
        Extract MRZ data from a base64 encoded image.
        
        Args:
            image_data: Base64 encoded image data.
            filename: Original filename for logging.
        
        Returns:
            dict: Extracted MRZ data.
        
        Raises:
            MRZAPIError: If extraction fails.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/extract",
                json={'image': image_data, 'filename': filename},
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                error_code = result.get('error_code')
                details = result.get('details', {})
                raise MRZAPIError(error_msg, error_code, details)
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to extract from base64 image: {e}")
            raise MRZAPIError(f"Failed to extract from base64 image: {e}")
    
    def extract_from_image(self, image_data: bytes, filename: str = "passport.jpg") -> dict:
        """
        Extract MRZ data from an uploaded image (bytes).
        
        Args:
            image_data: Raw image bytes.
            filename: Original filename.
        
        Returns:
            dict: Extracted MRZ data.
        
        Raises:
            MRZAPIError: If extraction fails.
        """
        try:
            files = {'image': (filename, image_data, 'image/jpeg')}
            response = self.session.post(
                f"{self.base_url}/api/extract",
                files=files,
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                error_code = result.get('error_code')
                details = result.get('details', {})
                raise MRZAPIError(error_msg, error_code, details)
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to extract from image: {e}")
            raise MRZAPIError(f"Failed to extract from image: {e}")
    
    def extract_from_file(self, file_path: str) -> dict:
        """
        Extract MRZ data from a local file.
        
        Args:
            file_path: Path to the image file.
        
        Returns:
            dict: Extracted MRZ data.
        
        Raises:
            MRZAPIError: If extraction fails.
        """
        with open(file_path, 'rb') as f:
            image_data = f.read()
        filename = os.path.basename(file_path)
        return self.extract_from_image(image_data, filename)


# Singleton instance
_mrz_client: Optional[MRZAPIClient] = None


def get_mrz_client() -> MRZAPIClient:
    """
    Get the singleton MRZ API client instance.
    
    Returns:
        MRZAPIClient: The client instance.
    """
    global _mrz_client
    if _mrz_client is None:
        _mrz_client = MRZAPIClient()
    return _mrz_client


def convert_mrz_to_kiosk_format(mrz_data: dict) -> dict:
    """
    Convert MRZ API response data to kiosk format.
    
    Args:
        mrz_data: Raw MRZ data from API.
    
    Returns:
        dict: Kiosk-formatted data with fields:
            - first_name
            - last_name
            - passport_number
            - date_of_birth
            - nationality
            - gender
    """
    # Handle date format conversion
    dob = mrz_data.get('birth_date', '')
    if len(dob) == 6:  # YYMMDD format
        year = int(dob[:2])
        # Assume 00-30 is 2000s, 31-99 is 1900s
        century = 20 if year <= 30 else 19
        dob = f"{century}{dob[:2]}-{dob[2:4]}-{dob[4:6]}"
    
    return {
        'first_name': mrz_data.get('given_name', '').replace('<', ' ').strip(),
        'last_name': mrz_data.get('surname', '').replace('<', ' ').strip(),
        'passport_number': mrz_data.get('document_number', ''),
        'date_of_birth': dob,
        'nationality': mrz_data.get('nationality_code', ''),
        'nationality_code': mrz_data.get('nationality_code', ''),
        'gender': mrz_data.get('sex', ''),
        'issuer_country': mrz_data.get('issuer_code', ''),
    }


class MRZDocumentClient:
    """
    Client for document management operations via MRZ backend.
    
    Handles:
    - Sending edited guest information to MRZ backend
    - SVG signature submission
    - Document preview retrieval
    - Physical signature submission to front desk
    """
    
    def __init__(self, base_url: str = None, timeout: int = 30):
        """
        Initialize MRZ Document client.
        
        Args:
            base_url: Base URL of the MRZ service. Defaults to MRZ_SERVICE_URL env var.
            timeout: Request timeout in seconds.
        """
        self.base_url = (base_url or MRZ_SERVICE_URL).rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def update_document(self, session_id: str, guest_data: dict, accompanying_guests: list = None) -> dict:
        """
        Send guest information to MRZ backend and trigger document filling.
        Calls /api/mrz/update endpoint which generates the PDF.
        
        Args:
            session_id: Unique session identifier
            guest_data: Dictionary with guest information
            accompanying_guests: List of accompanying guest dicts (optional)
        
        Returns:
            dict: Response with:
                - success: bool
                - session_id: str
                - filled_document: {path, filename}
                - guest_data: dict
        
        Raises:
            MRZAPIError: If update fails
        """
        try:
            payload = {
                'session_id': session_id,
                'guest_data': guest_data
            }
            if accompanying_guests:
                payload['accompanying_guests'] = accompanying_guests
            
            response = self.session.post(
                f"{self.base_url}/api/mrz/update",
                json=payload,
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                raise MRZAPIError(
                    result.get('error', 'Update failed'),
                    result.get('error_code')
                )
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to update document: {e}")
            raise MRZAPIError(f"Failed to update document: {e}")
    
    def get_pdf_url(self, session_id: str, filename: str) -> str:
        """
        Get the URL to fetch the generated PDF from MRZ backend.
        
        Args:
            session_id: Unique session identifier
            filename: PDF filename from update_document response
        
        Returns:
            str: Full URL to fetch the PDF
        """
        return f"{self.base_url}/api/document/pdf/{session_id}?file={filename}"
    
    def get_pdf_content(self, session_id: str, filename: str) -> bytes:
        """
        Fetch the generated PDF content from MRZ backend.
        
        Args:
            session_id: Unique session identifier
            filename: PDF filename from update_document response
        
        Returns:
            bytes: PDF file content
        
        Raises:
            MRZAPIError: If PDF fetch fails
        """
        try:
            url = self.get_pdf_url(session_id, filename)
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code != 200:
                raise MRZAPIError(
                    f"Failed to fetch PDF: {response.status_code}",
                    'PDF_FETCH_FAILED'
                )
            
            return response.content
        except requests.RequestException as e:
            logger.error(f"Failed to fetch PDF: {e}")
            raise MRZAPIError(f"Failed to fetch PDF: {e}")
    
    def get_document_preview(self, session_id: str, guest_data: dict = None) -> dict:
        """
        Get document preview for legal review before signing.
        
        Args:
            session_id: Unique session identifier
            guest_data: Optional guest data (uses stored data if not provided)
        
        Returns:
            dict: Response with preview_html and fields
        
        Raises:
            MRZAPIError: If preview fails
        """
        try:
            payload = {'session_id': session_id}
            if guest_data:
                payload['guest_data'] = guest_data
            
            response = self.session.post(
                f"{self.base_url}/api/document/preview",
                json=payload,
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                raise MRZAPIError(
                    result.get('error', 'Preview failed'),
                    result.get('error_code')
                )
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to get document preview: {e}")
            raise MRZAPIError(f"Failed to get document preview: {e}")
    
    def sign_document_digital(self, session_id: str, guest_data: dict, signature_svg: str) -> dict:
        """
        Submit digital signature (SVG) and store signed document.
        
        Args:
            session_id: Unique session identifier
            guest_data: Guest information
            signature_svg: SVG signature content
        
        Returns:
            dict: Response with document_id and storage confirmation
        
        Raises:
            MRZAPIError: If signing fails
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/document/sign",
                json={
                    'session_id': session_id,
                    'guest_data': guest_data,
                    'signature_svg': signature_svg,
                    'signature_type': 'digital'
                },
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                raise MRZAPIError(
                    result.get('error', 'Signing failed'),
                    result.get('error_code')
                )
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to sign document: {e}")
            raise MRZAPIError(f"Failed to sign document: {e}")
    
    def submit_physical_signature(self, session_id: str, guest_data: dict, 
                                   reservation_id: int = None, room_number: str = None) -> dict:
        """
        Submit document for physical signature at front desk.
        
        Args:
            session_id: Unique session identifier
            guest_data: Guest information
            reservation_id: Optional reservation ID
            room_number: Optional room number
        
        Returns:
            dict: Response with submission_id and front desk notification status
        
        Raises:
            MRZAPIError: If submission fails
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/document/submit-physical",
                json={
                    'session_id': session_id,
                    'guest_data': guest_data,
                    'reservation_id': reservation_id,
                    'room_number': room_number
                },
                timeout=self.timeout
            )
            result = response.json()
            
            if not result.get('success'):
                raise MRZAPIError(
                    result.get('error', 'Submission failed'),
                    result.get('error_code')
                )
            
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to submit for physical signature: {e}")
            raise MRZAPIError(f"Failed to submit for physical signature: {e}")


# Singleton instance for document client
_document_client: Optional[MRZDocumentClient] = None


def get_document_client() -> MRZDocumentClient:
    """
    Get the singleton MRZ Document client instance.
    
    Returns:
        MRZDocumentClient: The client instance.
    """
    global _document_client
    if _document_client is None:
        _document_client = MRZDocumentClient()
    return _document_client
