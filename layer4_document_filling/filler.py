"""
Layer 4 — Document Filling (PDF)
Responsibility: Automatically fill PDF templates with extracted MRZ data
Output: Filled PDF document (.pdf)
"""
import logging
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os

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
    """Handles automatic filling of registration card templates as PDF"""
    
    def __init__(self, template_path=None, output_dir="filled_documents"):
        """
        Initialize PDF document filler
        
        Args:
            output_dir: Directory to save filled documents
        """
        self.output_dir = output_dir
        
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
            # Try to register custom fonts if available
            pdfmetrics.registerFont(TTFont('CustomBold', 'fonts/Arial-Bold.ttf'))
            pdfmetrics.registerFont(TTFont('CustomRegular', 'fonts/Arial.ttf'))
            self.font_bold = 'CustomBold'
            self.font_regular = 'CustomRegular'
        except:
            # Fallback to built-in fonts
            self.font_bold = 'Helvetica-Bold'
            self.font_regular = 'Helvetica'
            logger.debug("Using built-in Helvetica fonts")
        
        logger.info("DocumentFiller initialized (PDF mode)")
        logger.debug(f"  Template path: {template_path} (not used for PDF)")
        logger.debug(f"  Output dir: {output_dir}")
    
    def fill_registration_card(self, mrz_data, timestamp=None):
        """
        Fill the DWA Registration Card with MRZ data
        
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
            
            # Create PDF
            self._create_registration_pdf(
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
    
    def _create_registration_pdf(self, output_path, surname, given_name, 
                                 nationality, passport_no, birth_date, 
                                 expiry_date, issuer_country):
        """
        Create a registration card PDF from scratch
        
        Args:
            output_path: Path to save the PDF
            surname: Guest surname
            given_name: Guest given name
            nationality: Guest nationality
            passport_no: Passport number
            birth_date: Date of birth (DD/MM/YYYY)
            expiry_date: Passport expiry date (DD/MM/YYYY)
            issuer_country: Passport issuing country
        """
        try:
            c = canvas.Canvas(output_path, pagesize=A4)
            width, height = A4
            
            # Define margins and positions
            margin_left = 40
            margin_top = height - 50
            line_height = 20
            
            # Title
            c.setFont(self.font_bold, 16)
            c.drawString(margin_left, margin_top, "DWA REGISTRATION CARD")
            
            # Draw a line under title
            c.line(margin_left, margin_top - 5, width - margin_left, margin_top - 5)
            
            y_pos = margin_top - 40
            
            # Personal Information Section
            c.setFont(self.font_bold, 12)
            c.drawString(margin_left, y_pos, "PERSONAL INFORMATION")
            y_pos -= line_height * 1.5
            
            c.setFont(self.font_regular, 10)
            
            # Field helper function
            def draw_field(label, value, y):
                c.setFont(self.font_bold, 10)
                c.drawString(margin_left, y, label)
                c.setFont(self.font_regular, 10)
                c.drawString(margin_left + 150, y, value)
                # Draw underline for value
                c.line(margin_left + 150, y - 2, width - margin_left, y - 2)
            
            # Draw all fields
            draw_field("Surname:", surname, y_pos)
            y_pos -= line_height
            
            draw_field("Given Name:", given_name, y_pos)
            y_pos -= line_height
            
            draw_field("Nationality:", nationality, y_pos)
            y_pos -= line_height
            
            draw_field("Date of Birth:", birth_date, y_pos)
            y_pos -= line_height
            
            # Passport Information Section
            y_pos -= line_height
            c.setFont(self.font_bold, 12)
            c.drawString(margin_left, y_pos, "PASSPORT INFORMATION")
            y_pos -= line_height * 1.5
            
            draw_field("Passport Number:", passport_no, y_pos)
            y_pos -= line_height
            
            draw_field("Issuing Country:", issuer_country, y_pos)
            y_pos -= line_height
            
            draw_field("Expiry Date:", expiry_date, y_pos)
            y_pos -= line_height
            
            # Stay Information Section
            y_pos -= line_height
            c.setFont(self.font_bold, 12)
            c.drawString(margin_left, y_pos, "STAY INFORMATION")
            y_pos -= line_height * 1.5
            
            today_date = self._get_today_date()
            draw_field("Check-in Date:", today_date, y_pos)
            y_pos -= line_height
            
            draw_field("Expected Check-out:", "", y_pos)
            y_pos -= line_height
            
            # Additional Information Section (blank for manual entry)
            y_pos -= line_height
            c.setFont(self.font_bold, 12)
            c.drawString(margin_left, y_pos, "ADDITIONAL INFORMATION")
            y_pos -= line_height * 1.5
            
            draw_field("Profession:", "", y_pos)
            y_pos -= line_height
            
            draw_field("Hometown:", "", y_pos)
            y_pos -= line_height
            
            draw_field("Email:", "", y_pos)
            y_pos -= line_height
            
            draw_field("Phone Number:", "", y_pos)
            y_pos -= line_height
            
            draw_field("Cabin Number:", "", y_pos)
            y_pos -= line_height * 2
            
            # Signature Section
            y_pos -= line_height
            c.setFont(self.font_regular, 10)
            c.drawString(margin_left, y_pos, "Guest Signature:")
            c.line(margin_left + 100, y_pos - 2, margin_left + 250, y_pos - 2)
            
            c.drawString(width - 200, y_pos, "Date:")
            c.line(width - 160, y_pos - 2, width - margin_left, y_pos - 2)
            
            # Footer
            y_pos = 50
            c.setFont(self.font_regular, 8)
            c.drawString(margin_left, y_pos, 
                        f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            c.drawString(width - 150, y_pos, "DWA Automated System")
            
            # Save PDF
            c.save()
            
        except Exception as e:
            logger.error(f"Failed to create PDF: {e}")
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