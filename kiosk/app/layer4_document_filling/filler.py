"""
Layer 4 — Document Filling (PDF)
Responsibility: Automatically fill PDF templates with extracted MRZ data by overlaying text
Output: Filled PDF document (.pdf)
"""
import logging
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os
import io

logger = logging.getLogger(__name__)


class DocumentFillingError(Exception):
    """Base exception for document filling errors"""
    def __init__(self, message, details=None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class TemplateNotFoundError(DocumentFillingError):
    """Template file not found"""
    def __init__(self, template_path):
        super().__init__(
            message=f"Template file not found: {template_path}",
            details={
                "template_path": template_path,
                "suggestion": "Check that the template file exists in the templates/ directory"
            }
        )


class TemplateSaveError(DocumentFillingError):
    """Failed to save filled document"""
    def __init__(self, output_path, reason):
        super().__init__(
            message=f"Failed to save document to {output_path}",
            details={
                "output_path": output_path,
                "reason": str(reason),
                "suggestion": "Check disk space and write permissions"
            }
        )


class DocumentFiller:
    """Handles automatic filling of registration card templates by overlaying on PDF"""
    
    def __init__(self, template_path, output_dir="filled_documents"):
        """
        Initialize PDF document filler
        
        Args:
            template_path: Path to the blank PDF template
            output_dir: Directory to save filled documents
            
        Raises:
            TemplateNotFoundError: If template file doesn't exist
        """
        self.template_path = template_path
        self.output_dir = output_dir
        
        # Verify template exists
        if not os.path.exists(template_path):
            logger.error(f"Template not found: {template_path}")
            raise TemplateNotFoundError(template_path)
        
        # Create output directory if needed
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                logger.info(f"Created output directory: {output_dir}")
            except Exception as e:
                logger.error(f"Failed to create output directory: {e}")
                raise
        
        # Register fonts (fallback to Helvetica if custom fonts unavailable)
        try:
            pdfmetrics.registerFont(TTFont('CustomBold', 'fonts/Arial-Bold.ttf'))
            pdfmetrics.registerFont(TTFont('CustomRegular', 'fonts/Arial.ttf'))
            self.font_bold = 'CustomBold'
            self.font_regular = 'CustomRegular'
        except:
            self.font_bold = 'Helvetica-Bold'
            self.font_regular = 'Helvetica'
            logger.debug("Using built-in Helvetica fonts")
        
        logger.info("DocumentFiller initialized (PDF overlay mode)")
        logger.debug(f"  Template: {template_path}")
        logger.debug(f"  Output dir: {output_dir}")
    
    def fill_registration_card(self, mrz_data, timestamp=None):
        """
        Fill the DWA Registration Card with MRZ data by overlaying on template
        
        Args:
            mrz_data: Dictionary containing extracted MRZ information
            timestamp: Optional timestamp for filename (uses current if None)
            
        Returns:
            dict: Contains output_path, output_filename, and timestamp
            
        Raises:
            DocumentFillingError: If document filling fails
            TemplateSaveError: If document save fails
        """
        logger.info("Starting PDF document filling process")
        
        try:
            # Extract and validate MRZ data
            surname = mrz_data.get('surname', '').strip()
            given_name = mrz_data.get('given_name', '').replace('<', ' ').strip()
            nationality = self._get_country_name(mrz_data.get('nationality_code', ''))
            passport_no = mrz_data.get('document_number', '').strip()
            birth_date = self._format_date(mrz_data.get('birth_date', ''))
            expiry_date = self._format_date(mrz_data.get('expiry_date', ''))
            issuer_country = self._get_country_name(mrz_data.get('issuer_code', ''))
            
            # Validate critical fields
            if not surname or not given_name:
                raise DocumentFillingError(
                    "Missing critical data: surname or given name",
                    details={"mrz_data": mrz_data}
                )
            
            logger.debug(f"Processing data for: {given_name} {surname}")
            
            # Generate output filename
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            safe_name = f"{surname}_{given_name}".replace(' ', '_')[:50]
            output_filename = f"registration_card_{timestamp}_{safe_name}.pdf"
            output_path = os.path.join(self.output_dir, output_filename)
            
            # Fill PDF by overlaying on template
            self._overlay_data_on_template(
                output_path,
                surname=surname,
                given_name=given_name,
                nationality=nationality,
                passport_no=passport_no,
                birth_date=birth_date,
                expiry_date=expiry_date,
                issuer_country=issuer_country
            )
            
            logger.info(f"✓ PDF document filled and saved: {output_filename}")
            
            return {
                "output_path": output_path,
                "output_filename": output_filename,
                "timestamp": timestamp
            }
            
        except DocumentFillingError:
            raise
        except Exception as e:
            logger.error(f"Error filling document: {e}")
            logger.exception("Full traceback:")
            raise DocumentFillingError(
                f"Document filling failed: {str(e)}",
                details={"error_type": type(e).__name__}
            )
    
    def _overlay_data_on_template(self, output_path, surname, given_name, 
                                   nationality, passport_no, birth_date, 
                                   expiry_date, issuer_country):
        """
        Overlay MRZ data on the blank PDF template
        
        Args:
            output_path: Path to save the filled PDF
            surname: Guest surname
            given_name: Guest given name
            nationality: Guest nationality
            passport_no: Passport number
            birth_date: Date of birth (DD/MM/YYYY)
            expiry_date: Passport expiry date (DD/MM/YYYY)
            issuer_country: Passport issuing country
        """
        try:
            # Read the template PDF
            template_pdf = PdfReader(self.template_path)
            template_page = template_pdf.pages[0]
            
            # Get actual page dimensions from template
            width = float(template_page.mediabox.width)
            height = float(template_page.mediabox.height)
            
            # Create overlay with text
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(width, height))
            
            # Get today's date components for From field
            now = datetime.now()
            today_day = now.strftime('%d')
            today_month = now.strftime('%m')
            today_year = now.strftime('%y')  # Just last 2 digits (25, 26, etc.)
            
            # Field positions (x, y from bottom-left) - finalized coordinates
            # Page is Letter size: 612 x 792 pts
            
            # Draw date fields with larger font (size 12)
            can.setFont(self.font_regular, 12)
            
            # *From: broken into day/month/year
            can.drawString(75, 679, today_day)
            can.drawString(100, 679, today_month)
            can.drawString(141, 679, today_year)
            
            # *Ex.: expiry date
            can.drawString(80, 646, expiry_date)
            
            # *Date of Birth
            can.drawString(150, 561, birth_date)
            
            # Draw other fields with normal font (size 10)
            can.setFont(self.font_regular, 10)
            
            # *Surname / *Name
            can.drawString(150, 619, surname)
            can.drawString(400, 619, given_name)
            
            # *Nationality / *Passport No.
            can.drawString(150, 590, nationality)
            can.drawString(430, 590, passport_no)
            
            # *Country
            can.drawString(420, 533, issuer_country)
            
            # Save the overlay
            can.save()
            packet.seek(0)
            
            # Read the overlay
            overlay_pdf = PdfReader(packet)
            overlay_page = overlay_pdf.pages[0]
            
            # Merge overlay onto template
            template_page.merge_page(overlay_page)
            
            # Write output
            output = PdfWriter()
            output.add_page(template_page)
            
            with open(output_path, 'wb') as output_file:
                output.write(output_file)
            
        except Exception as e:
            logger.error(f"Failed to overlay data on PDF: {e}")
            raise TemplateSaveError(output_path, str(e))
    
    def _get_today_date(self):
        """Get today's date in DD/MM/YYYY format"""
        return datetime.now().strftime('%d/%m/%Y')
    
    def _format_date(self, date_str):
        """
        Format date from YYMMDD or YYYY-MM-DD to DD/MM/YYYY
        
        Args:
            date_str: Date string in YYMMDD or YYYY-MM-DD format
            
        Returns:
            str: Formatted date DD/MM/YYYY
        """
        if not date_str:
            return ''
        
        try:
            if '-' in date_str:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            elif len(date_str) == 6:
                year = int(date_str[0:2])
                if year <= 50:
                    full_year = 2000 + year
                else:
                    full_year = 1900 + year
                month = date_str[2:4]
                day = date_str[4:6]
                date_obj = datetime.strptime(f"{full_year}{month}{day}", '%Y%m%d')
            else:
                return date_str
            
            return date_obj.strftime('%d/%m/%Y')
        except Exception as e:
            logger.warning(f"Could not format date '{date_str}': {e}")
            return date_str
    
    def _get_country_name(self, country_code):
        """Convert 3-letter country code to full name"""
        if not country_code:
            return ''
        
        country_map = {
            'EGY': 'Egypt', 'USA': 'United States', 'GBR': 'United Kingdom',
            'FRA': 'France', 'DEU': 'Germany', 'ITA': 'Italy', 'ESP': 'Spain',
            'CAN': 'Canada', 'AUS': 'Australia', 'JPN': 'Japan', 'CHN': 'China',
            'IND': 'India', 'BRA': 'Brazil', 'RUS': 'Russia', 'SAU': 'Saudi Arabia',
            'ARE': 'United Arab Emirates', 'TUR': 'Turkey', 'NLD': 'Netherlands',
            'BEL': 'Belgium', 'CHE': 'Switzerland', 'SWE': 'Sweden', 'NOR': 'Norway',
            'DNK': 'Denmark', 'POL': 'Poland', 'GRC': 'Greece', 'PRT': 'Portugal',
            'AUT': 'Austria', 'CZE': 'Czech Republic', 'MEX': 'Mexico',
            'ARG': 'Argentina', 'ZAF': 'South Africa', 'KOR': 'South Korea',
            'SGP': 'Singapore', 'MYS': 'Malaysia', 'THA': 'Thailand',
            'IDN': 'Indonesia', 'PHL': 'Philippines', 'VNM': 'Vietnam',
            'NZL': 'New Zealand', 'IRL': 'Ireland', 'FIN': 'Finland',
            'ISR': 'Israel', 'LBN': 'Lebanon', 'JOR': 'Jordan', 'KWT': 'Kuwait',
            'QAT': 'Qatar', 'BHR': 'Bahrain', 'OMN': 'Oman', 'PAK': 'Pakistan',
            'BGD': 'Bangladesh', 'LKA': 'Sri Lanka', 'MAR': 'Morocco',
            'DZA': 'Algeria', 'TUN': 'Tunisia', 'SDN': 'Sudan', 'YEM': 'Yemen',
            'SYR': 'Syria', 'IRQ': 'Iraq', 'IRN': 'Iran', 'AFG': 'Afghanistan',
        }
        
        result = country_map.get(country_code.upper(), country_code)
        
        if result == country_code:
            logger.debug(f"Unknown country code: {country_code}")
        
        return result