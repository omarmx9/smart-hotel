"""
Overlay coordinate grid directly on template PDF
This makes it much easier to find exact coordinates
"""
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io

def create_grid_overlay_on_template(template_path, output_path="template_with_grid.pdf"):
    """
    Overlay a coordinate grid directly on the template PDF
    """
    print("\n" + "="*60)
    print("CREATING TEMPLATE WITH COORDINATE GRID OVERLAY")
    print("="*60)
    
    # Read template
    template_pdf = PdfReader(template_path)
    template_page = template_pdf.pages[0]
    
    # Create grid overlay
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    width, height = A4
    
    # Draw semi-transparent grid
    can.setStrokeColorRGB(1, 0, 0, alpha=0.3)  # Red, semi-transparent
    can.setFont("Helvetica", 7)
    
    # Vertical lines every 50 points with labels
    for x in range(0, int(width), 50):
        can.setStrokeColorRGB(1, 0, 0, alpha=0.3)
        can.line(x, 0, x, height)
        # Label at top and bottom
        can.setFillColorRGB(1, 0, 0, alpha=0.8)
        can.drawString(x + 2, height - 15, f"x={x}")
        can.drawString(x + 2, 5, f"x={x}")
    
    # Horizontal lines every 50 points with labels
    for y in range(0, int(height), 50):
        can.setStrokeColorRGB(1, 0, 0, alpha=0.3)
        can.line(0, y, width, y)
        # Label at left and right
        can.setFillColorRGB(1, 0, 0, alpha=0.8)
        can.drawString(5, y + 2, f"y={y}")
        can.drawString(width - 35, y + 2, f"y={y}")
    
    # Add finer grid every 10 points (lighter)
    can.setStrokeColorRGB(1, 0.5, 0.5, alpha=0.2)
    for x in range(0, int(width), 10):
        if x % 50 != 0:  # Skip the major gridlines
            can.line(x, 0, x, height)
    for y in range(0, int(height), 10):
        if y % 50 != 0:
            can.line(0, y, width, y)
    
    can.save()
    packet.seek(0)
    
    # Overlay grid on template
    overlay_pdf = PdfReader(packet)
    overlay_page = overlay_pdf.pages[0]
    template_page.merge_page(overlay_page)
    
    # Save result
    output = PdfWriter()
    output.add_page(template_page)
    
    with open(output_path, 'wb') as f:
        output.write(f)
    
    print(f"\n✓ Template with grid overlay created: {output_path}")
    print("\nInstructions:")
    print("1. Open the file: template_with_grid.pdf")
    print("2. You'll see your template with a RED coordinate grid overlay")
    print("3. Look at where the dotted lines start after each label")
    print("4. Note the X and Y coordinates from the red grid")
    print("5. Major grid lines every 50 points")
    print("6. Minor grid lines every 10 points")
    print("\nExample: If '*Surname:' label ends at x=95 and y=658,")
    print("         then the data should start around x=100, y=658")
    print("\n" + "="*60)


def quick_reference_guide():
    """Print a quick reference for common field positions"""
    print("\n" + "="*60)
    print("QUICK REFERENCE GUIDE")
    print("="*60)
    print("\nFields to map (in order from top to bottom):")
    print("\n1. *From: (date field, top section)")
    print("   Look for: The space after '*From: ......../........ / 20.......'")
    print("   This is where today's date goes")
    print("\n2. *Surname: (left column)")
    print("   Look for: The dotted line after '*Surname:'")
    print("\n3. *Name: (right column, same row as Surname)")
    print("   Look for: The dotted line after '*Name:'")
    print("\n4. *Nationality: (left column)")
    print("   Look for: The dotted line after '*Nationality:'")
    print("\n5. *Passport No.: (right column, same row as Nationality)")
    print("   Look for: The dotted line after '*Passport No.:'")
    print("\n6. *Date of Birth: (left column)")
    print("   Look for: The dotted line after '*Date of Birth:'")
    print("\n7. *Country: (right column, NOT same row as Date of Birth)")
    print("   Look for: The dotted line after '*Country:'")
    print("\nTIP: Focus on the X coordinate of where dots START")
    print("     and the Y coordinate of the text baseline")
    print("="*60)


if __name__ == "__main__":
    template_path = "templates/DWA_Registration_Card.pdf"
    
    print("\n" + "="*70)
    print(" "*15 + "TEMPLATE GRID OVERLAY TOOL")
    print("="*70)
    
    quick_reference_guide()
    
    input("\nPress ENTER to create template with grid overlay...")
    
    create_grid_overlay_on_template(template_path)
    
    print("\n✓ Done! Open 'template_with_grid.pdf' to see coordinates")
    print("\nOnce you have the coordinates, run this command:")
    print("  python find_coordinates.py")
    print("Then select option 3 to enter your coordinates.\n")