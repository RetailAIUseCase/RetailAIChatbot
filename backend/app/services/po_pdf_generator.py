"""
Corporate PO PDF Generator using FPDF - Concurrent Safe & Bulletproof
"""
import io
import os
from typing import Dict, Any, List
from pathlib import Path
from fpdf import FPDF
from datetime import datetime
from app.services.storage_service import storage_service
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

def safe_currency(amount):
    """Safe currency formatting without Unicode issues"""
    try:
        return f"$ {float(amount):,.2f}"
    except:
        return "$ 0.00"

class CorporatePOPDFGenerator(FPDF):
    """Thread-safe PDF generator that creates fresh instances"""
    
    # Corporate Colors (RGB values for FPDF)
    CORPORATE_RED = (180, 30, 45)
    LIGHT_GRAY = (245, 245, 245)
    DARK_GRAY = (80, 80, 80)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)

    def __init__(self):
        super().__init__()
        self.logo_path = self._get_logo_path()
        self.company_details = {}
        self.po_data = {}
        
    def _get_logo_path(self) -> str:
        """Get logo path from multiple possible locations"""
        # possible_paths = [
        #     "../static/images/coca_cola.png",  # Go up one level from services to app, then to static
        #     "app/static/images/coca_cola.png",  # If running from project root
        #     "./app/static/images/coca_cola.png",  # Alternative root path
        #     "static/images/coca_cola.png",  # If current directory is app
        #     "/app/static/images/coca_cola.png",  # Absolute path for containers
        # ]
        
        # for path in possible_paths:
        #     if os.path.exists(path):
        #         return path
        # return None
        try:
            # Go up to app/ then to static/images/
            base_dir = Path(__file__).parent.parent  # Goes from services/ to app/
            logo_path = base_dir / "static" / "images" / "coca_cola.png"
            
            if logo_path.exists():
                logger.info(f"✅ Logo found at: {logo_path}")
                return str(logo_path)
            else:
                logger.warning(f"❌ Logo not found at: {logo_path}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting logo path: {e}")
            return None

    def header(self):
        """Custom header with logo and company info"""
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 10, 6, 40)
            except Exception as e:
                logger.warning(f"Could not load logo: {e}")
                self._draw_text_logo()
        else:
            self._draw_text_logo()

        self.set_font("Arial", 'B', 22)
        self.set_text_color(*self.CORPORATE_RED)
        self.set_xy(120, 15)
        self.cell(80, 10, "PURCHASE ORDER", ln=1, align="R")
        
        self.set_draw_color(*self.CORPORATE_RED)
        self.set_line_width(0.5)
        self.line(10, 30, 200, 30)
        self.ln(15)

    def _draw_text_logo(self):
        """Draw text-based logo when image logo is not available"""
        self.set_xy(10, 15)
        self.set_font("Arial", 'B', 16)
        self.set_text_color(*self.CORPORATE_RED)
        self.cell(0, 8, self.company_details.get('name', 'Company Name'), ln=1)

    def footer(self):
        """Custom footer with contact info"""
        self.set_y(-20)
        self.set_font("Arial", '', size=9)
        self.set_text_color(100, 100, 100)
        
        contact_name = self.company_details.get('contact_name', 'Procurement Department')
        email = self.company_details.get('email', 'procurement@company.com')
        phone = self.company_details.get('phone', '(000) 000-0000')
        
        footer_text = f"If you have questions about this PO, contact {contact_name} at {email} or {phone}"
        self.multi_cell(0, 5, footer_text, align='C')

    def generate_content(self, pdf_data: Dict[str, Any]):
        """Generate all PDF content in one method"""
        
        # Store data for header/footer
        self.company_details = pdf_data.get('company_details', {})
        self.po_data = pdf_data

        # Extract main data
        po_number = pdf_data['po_number']
        vendor = pdf_data['vendor']
        materials = pdf_data['materials']
        total_amount = pdf_data['total_amount']
        order_date = pdf_data['order_date']
        
        # Setup PDF
        self.set_auto_page_break(auto=True, margin=30)
        self.add_page()
        self.set_y(45)

        # Company Information Block
        self.set_xy(10, 35)
        self.set_font("Arial", 'B', 14)
        self.set_text_color(*self.CORPORATE_RED)
        self.cell(0, 7, self.company_details.get('name', 'Company Name'), ln=1)
        
        self.set_font("Arial", size=10)
        self.set_text_color(*self.BLACK)
        
        # Multi-line company address
        address_lines = self.company_details.get('address', '').split('\n')
        for line in address_lines:
            if line.strip():
                self.cell(0, 5, line.strip(), ln=1)
        
        self.cell(0, 5, f"Phone: {self.company_details.get('phone', '')}", ln=1)
        self.cell(0, 5, f"Website: {self.company_details.get('website', '')}", ln=1)
        
        # PO details on right
        self.set_xy(120, 40)
        self.set_font("Arial", 'B', 10)
        self.cell(30, 6, "DATE:")
        self.set_font("Arial", size=10)
        self.cell(40, 6, datetime.now().strftime("%d/%m/%Y"), ln=1)
        
        self.set_x(120)
        self.set_font("Arial", 'B', 10)
        self.cell(30, 6, "PO #:")
        self.set_font("Arial", 'B', 10)
        self.set_text_color(*self.CORPORATE_RED)
        self.cell(40, 6, po_number, ln=1)
        self.set_text_color(*self.BLACK)

        # Vendor and Ship To Section
        self.ln(15)
        self.set_font("Arial", 'B', 12)
        self.set_fill_color(*self.DARK_GRAY)
        self.set_text_color(*self.WHITE)
        self.cell(95, 8, "VENDOR", border=0, fill=True)
        self.cell(95, 8, "SHIP TO", border=0, ln=1, fill=True)
        
        self.set_font("Arial", size=10)
        self.set_text_color(*self.BLACK)
        
        # Row 1: Names
        self.cell(95, 6, vendor.get('vendor_name', 'Vendor Name'), border=0)
        self.cell(95, 6, self.company_details.get('name', 'Company Name'), border=0, ln=1)
        
        # Row 2: Addresses
        vendor_address = vendor.get('vendor_address', '123 Bottle St, Atlanta')
        company_address = self.company_details.get('address', '').split('\n')[0]
        self.cell(95, 6, vendor_address[:40], border=0)
        self.cell(95, 6, company_address, border=0, ln=1)

        # Row 3: Contact info
        vendor_email = vendor.get('vendor_email_id', 'Email on file')
        company_line2 = ""
        address_lines = self.company_details.get('address', '').split('\n')
        if len(address_lines) > 1:
            company_line2 = address_lines[1]
        
        self.cell(95, 6, vendor_email[:40], border=0)
        self.cell(95, 6, company_line2, border=0, ln=1)

        # Materials Table
        self.ln(10)
        self.set_font("Arial", 'B', 10)
        self.set_fill_color(*self.CORPORATE_RED)
        self.set_text_color(*self.WHITE)
        
        # Header row
        self.cell(25, 8, "ITEM #", 1, 0, 'C', fill=True)
        self.cell(65, 8, "DESCRIPTION", 1, 0, 'C', fill=True)
        self.cell(15, 8, "UOM", 1, 0, 'C', fill=True)
        self.cell(20, 8, "QTY", 1, 0, 'C', fill=True)
        self.cell(30, 8, "UNIT PRICE", 1, 0, 'C', fill=True)
        self.cell(25, 8, "TOTAL", 1, 1, 'C', fill=True)
        
        # Table data
        self.set_font("Arial", '', 9)
        self.set_text_color(*self.BLACK)
        self.set_fill_color(*self.WHITE)
        
        for material_option in materials:
            material = material_option['material']
            vendor_info = material_option['vendor']
            total_cost = material_option['total_cost']
            
            # Truncate long descriptions
            description = material['matdesc']
            if len(description) > 30:
                description = description[:27] + "..."
            
            self.cell(25, 8, material['matnr'][:10], 1, 0, 'L')
            self.cell(65, 8, description, 1, 0, 'L')
            self.cell(15, 8, material.get('unit', 'EA'), 1, 0, 'C')
            self.cell(20, 8, str(material['shortfall_qty']), 1, 0, 'C')
            self.cell(30, 8, safe_currency(vendor_info['cost_per_single_unit']), 1, 0, 'R')
            self.cell(25, 8, safe_currency(total_cost), 1, 1, 'R')

        # Totals Section
        self.ln(10)
        subtotal = sum(mat['total_cost'] for mat in pdf_data['materials'])
        tax = pdf_data.get('tax', 0.0)
        shipping = pdf_data.get('shipping', 0.0)
        other_charges = pdf_data.get('other_charges', 0.0)
        
        self.set_font("Arial", 'B', 10)
        self.set_fill_color(*self.LIGHT_GRAY)
        
        # Position on right side
        start_x = 120
        
        # Subtotal
        self.set_xy(start_x, self.get_y())
        self.cell(40, 8, "SUBTOTAL:", 0, 0, 'L')
        self.cell(30, 8, safe_currency(subtotal), 1, 1, 'R', fill=True)
        
        # Tax (if any)
        if tax > 0:
            self.set_x(start_x)
            self.cell(40, 8, "TAX:", 0, 0, 'L')
            self.cell(30, 8, safe_currency(tax), 1, 1, 'R', fill=True)
        
        # Shipping (if any)
        if shipping > 0:
            self.set_x(start_x)
            self.cell(40, 8, "SHIPPING:", 0, 0, 'L')
            self.cell(30, 8, safe_currency(shipping), 1, 1, 'R', fill=True)
        
        # Other charges (if any)
        if other_charges > 0:
            self.set_x(start_x)
            self.cell(40, 8, "OTHER CHARGES:", 0, 0, 'L')
            self.cell(30, 8, safe_currency(other_charges), 1, 1, 'R', fill=True)
        
        # Total
        self.set_x(start_x)
        self.set_fill_color(*self.CORPORATE_RED)
        self.set_text_color(*self.WHITE)
        self.cell(40, 10, "TOTAL:", 0, 0, 'L')
        self.cell(30, 10, safe_currency(total_amount), 1, 1, 'R', fill=True)
        self.set_text_color(*self.BLACK)

        # Comments Section
        self.ln(15)
        self.set_font("Arial", 'B', 10)
        self.cell(0, 6, "Comments or Special Instructions", ln=1)
        
        comments = pdf_data.get('comments', 'Please deliver as per agreed timeline and specifications.')
        self.set_font("Arial", '', 10)
        self.set_fill_color(*self.LIGHT_GRAY)
        
        # Multi-cell for comments with background
        current_y = self.get_y()
        self.rect(10, current_y, 190, 20, 'F')
        self.multi_cell(190, 5, comments, border=0, align='L')

        # Additional Information
        # self.ln(10)
        # order_numbers = pdf_data.get('order_numbers', [])
        # if order_numbers:
        #     self.set_font("Arial", 'B', 10)
        #     self.cell(0, 5, f"Related Orders: {', '.join(map(str, order_numbers))}", ln=1)
        #     self.ln(5)
        
        # High-value approval notice
        # approval_threshold = settings.PO_APPROVAL_THRESHOLD
        # if approval_threshold and total_amount > approval_threshold:
        #     self.set_font("Arial", 'B', 8)
        #     self.set_text_color(*self.CORPORATE_RED)
        #     self.multi_cell(0, 5, 
        #         f"HIGH-VALUE PO: This purchase order requires Finance Manager approval due to amount exceeding ${approval_threshold:,.0f} threshold.",
        #         border=0, align='L')

    async def create_po_pdf(self, pdf_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create PDF with bulletproof error handling"""
        
        try:
            po_number = pdf_data['po_number']
            logger.info(f"📄 Creating PDF for PO: {po_number}")
            
            # Generate all content
            self.generate_content(pdf_data)
            
            # Get PDF output with robust handling
            filename = f"{po_number}.pdf"
            
            try:
                pdf_output = self.output(dest='S')
                
                # Handle different output types
                if isinstance(pdf_output, str):
                    pdf_content = pdf_output.encode('latin1')
                elif isinstance(pdf_output, (bytes, bytearray)):
                    pdf_content = bytes(pdf_output)
                else:
                    raise Exception(f"Unexpected PDF output type: {type(pdf_output)}")
                
            except Exception as output_error:
                logger.error(f"PDF output error: {output_error}")
                raise Exception(f"Failed to generate PDF output: {str(output_error)}")
            
            # Validate content
            if not pdf_content or len(pdf_content) < 200:
                raise Exception(f"Invalid PDF content: {len(pdf_content) if pdf_content else 0} bytes")
            
            logger.info(f"✅ PDF generated: {len(pdf_content)} bytes")
            
            # Upload to storage
            try:
                upload_result = await storage_service.upload_po_pdf(
                    pdf_content=pdf_content,
                    po_number=po_number,
                    user_id=pdf_data.get('user_id'),
                    project_id=pdf_data.get('project_id'),
                    order_date=pdf_data.get('order_date')
                )
                
                if upload_result.get("file_path"):
                    logger.info(f"✅ Corporate PO PDF uploaded: {filename}")
                    return {
                        "success": True,
                        "pdf_path": upload_result["file_path"],
                        "filename": upload_result.get("filename", filename),
                        "total_amount": pdf_data['total_amount'],
                        "po_number": po_number,
                        "file_size": len(pdf_content)
                    }
                else:
                    raise Exception(f"Upload failed: {upload_result.get('error', 'Unknown upload error')}")
                    
            except Exception as upload_error:
                logger.error(f"Storage upload failed: {upload_error}")
                raise Exception(f"Failed to upload PDF: {str(upload_error)}")
            
        except Exception as e:
            logger.error(f"❌ PDF generation error: {e}")
            return {
                "success": False, 
                "error": str(e),
                "pdf_path": None,
                "filename": None
            }

# **CONCURRENT PDF CREATION FUNCTION**
async def create_po_pdf_safe(pdf_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bulletproof PDF creation that NEVER reuses instances
    Each call gets a completely fresh PDF generator
    """
    generator = None
    try:
        # Create fresh instance
        generator = CorporatePOPDFGenerator()
        
        # Generate PDF
        result = await generator.create_po_pdf(pdf_data)
        
        return result
        
    except Exception as e:
        logger.error(f"Safe PDF creation failed: {e}")
        return {
            "success": False, 
            "error": f"PDF creation failed: {str(e)}",
            "pdf_path": None,
            "filename": None
        }
    finally:
        # Always clean up
        if generator:
            try:
                del generator
            except:
                pass

# **LEGACY SUPPORT - but don't use this for concurrent operations**
po_pdf_generator = CorporatePOPDFGenerator()
