"""
Test script to fill the template PDF with sample MRZ data
and find the correct positions for each field
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import io

# Sample MRZ data for testing
sample_mrz = {
    "surname": "SUDARSAN",
    "given_name": "HENERT",
    "nationality_code": "GBR",
    "document_number": "707797979",
    "birth_date": "1995-05-20",
    "expiry_date": "2017-06-22",
    "issuer_code": "GBR"
}

def format_date(date_str):
    """Convert YYYY-MM-DD to DD/MM/YYYY"""
    if not date_str:
        return ''
    try:
        if '-' in date_str:
            parts = date_str.split('-')
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return date_str
    except:
        return date_str

def get_country_name(code):
    """Convert country code to name"""
    countries = {
        'GBR': 'United Kingdom', 'EGY': 'Egypt', 'USA': 'United States',
        'DEU': 'Germany', 'FRA': 'France'
    }
    return countries.get(code, code)

# First, let's check template dimensions
template_path = "template_with_grid.pdf"
reader = PdfReader(template_path)
page = reader.pages[0]

# Get page dimensions
width = float(page.mediabox.width)
height = float(page.mediabox.height)
print(f"Template size: {width} x {height} pts")
print(f"Template size in mm: {width/72*25.4:.1f} x {height/72*25.4:.1f} mm")

# Create overlay with test data
packet = io.BytesIO()
c = canvas.Canvas(packet, pagesize=(width, height))

# Use a clear font
c.setFont("Helvetica", 10)

# Prepare data
surname = sample_mrz['surname']
given_name = sample_mrz['given_name']
nationality = get_country_name(sample_mrz['nationality_code'])
passport_no = sample_mrz['document_number']
birth_date = format_date(sample_mrz['birth_date'])
expiry_date = format_date(sample_mrz['expiry_date'])
issuer_country = get_country_name(sample_mrz['issuer_code'])

# Break today's date into components for From field
today_day = "30"
today_month = "12"
today_year = "25"  # Just last 2 digits

# Field positions based on the grid overlay in template_with_grid.pdf
# Page is Letter size: 612 x 792 pts
# Y=0 is bottom, Y=792 is top

# ADJUSTMENT GUIDE:
# - Increase X = move RIGHT
# - Decrease X = move LEFT  
# - Increase Y = move UP
# - Decrease Y = move DOWN

# Adjusted positions (tweak these values):
fields = {
    # Format: (x, y, value)
    # Top date field - *From: broken into day/month/year
    "From Day": (75, 679, today_day),
    "From Month": (100, 679, today_month),
    "From Year": (141, 679, today_year),
    
    # Expiry date field - *Ex.:
    "Expiry Date": (80, 646, expiry_date),
    
    # Row 1: *Surname / *Name
    "Surname": (150, 619, surname),
    "Given Name": (400, 619, given_name),
    
    # Row 2: *Nationality / *Passport No.
    "Nationality": (150, 590, nationality),
    "Passport No": (430, 590, passport_no),
    
    # Row 3: *Date of Birth / *Profession (leave blank)
    "Birth Date": (150, 561, birth_date),
    
    # Row 4: *Hometown (leave blank) / *Country
    "Country": (420, 533, issuer_country),
}

# Date fields that need larger font
date_fields = {"From Day", "From Month", "From Year", "Expiry Date", "Birth Date"}

# Draw all fields
for label, (x, y, value) in fields.items():
    c.setFillColorRGB(0, 0, 0)  # Black text
    if label in date_fields:
        c.setFont("Helvetica", 12)  # Larger font for dates
    else:
        c.setFont("Helvetica", 10)  # Normal font
    c.drawString(x, y, str(value))
    print(f"Placed '{label}': '{value}' at ({x}, {y})")

c.save()
packet.seek(0)

# Merge with template
overlay = PdfReader(packet)
output_page = reader.pages[0]
output_page.merge_page(overlay.pages[0])

# Write result
writer = PdfWriter()
writer.add_page(output_page)

output_path = "filled_documents/test_filled_template.pdf"
os.makedirs("filled_documents", exist_ok=True)
with open(output_path, 'wb') as f:
    writer.write(f)

print(f"\n✓ Test filled PDF saved to: {output_path}")
print("Please check the PDF and tell me which fields need position adjustments!")
