from fpdf import FPDF
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import base64
from decimal import Decimal
import tempfile
from uuid import uuid4

class InvoicePDF(FPDF):
    """Custom PDF class for generating invoices and quotes"""
    
    def __init__(self, document_type="facture"):
        super().__init__()
        self.document_type = document_type.upper()
        self.add_font('DejaVu', '', os.path.join(os.path.dirname(__file__), 'DejaVuSansCondensed.ttf'), uni=True)
        self.add_font('DejaVu', 'B', os.path.join(os.path.dirname(__file__), 'DejaVuSansCondensed-Bold.ttf'), uni=True)
        self.set_margins(15, 15, 15)
    
    def header(self):
        """Generate header with logo and company info"""
        # Logo (commented out as images are not supported as per requirement)
        # self.image('logo.png', 15, 15, 50)
        
        # Header text (Company info)
        self.set_font('DejaVu', 'B', 15)
        self.cell(0, 10, 'BeMyNet SAS', 0, 1, 'R')
        self.set_font('DejaVu', '', 10)
        self.cell(0, 5, '123 Avenue des Freelances', 0, 1, 'R')
        self.cell(0, 5, '75001 Paris, France', 0, 1, 'R')
        self.cell(0, 5, 'SIRET: 123 456 789 00010', 0, 1, 'R')
        self.cell(0, 5, 'TVA: FR12345678900', 0, 1, 'R')
        self.cell(0, 5, 'contact@bemynet.fr', 0, 1, 'R')
        self.ln(10)
    
    def footer(self):
        """Generate footer with page number and legal info"""
        self.set_y(-25)
        self.set_font('DejaVu', '', 8)
        self.cell(0, 5, 'BeMyNet SAS - Tous droits réservés', 0, 1, 'C')
        self.cell(0, 5, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
    
    def document_title(self, document_number):
        """Add document title section (invoice or quote)"""
        self.set_font('DejaVu', 'B', 18)
        
        # Blue background rectangle
        self.set_fill_color(41, 128, 185)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, f"{self.document_type} #{document_number}", 0, 1, 'C', True)
        
        # Reset text color
        self.set_text_color(0, 0, 0)
        self.ln(10)
    
    def client_info(self, client_data):
        """Add client information section"""
        self.set_font('DejaVu', 'B', 11)
        self.cell(0, 7, 'Client:', 0, 1)
        
        self.set_font('DejaVu', '', 11)
        self.cell(0, 5, client_data.get('full_name', ''), 0, 1)
        
        if client_data.get('company_name'):
            self.cell(0, 5, client_data.get('company_name', ''), 0, 1)
        
        if client_data.get('siret'):
            self.cell(0, 5, f"SIRET: {client_data.get('siret', '')}", 0, 1)
            
        if client_data.get('vat_number'):
            self.cell(0, 5, f"TVA: {client_data.get('vat_number', '')}", 0, 1)
        
        self.cell(0, 5, client_data.get('email', ''), 0, 1)
        self.cell(0, 5, client_data.get('phone_number', ''), 0, 1)
        self.ln(5)
    
    def document_info(self, document_data):
        """Add document information (dates, payment terms, etc.)"""
        self.set_font('DejaVu', 'B', 11)
        
        # Create a table with document info
        col_width = 90
        line_height = 7
        
        # Document date
        self.cell(col_width, line_height, 'Date d\'émission:', 0)
        self.set_font('DejaVu', '', 11)
        self.cell(0, line_height, document_data.get('date', ''), 0, 1)
        
        # Due date if available
        if document_data.get('due_date'):
            self.set_font('DejaVu', 'B', 11)
            self.cell(col_width, line_height, 'Date d\'échéance:', 0)
            self.set_font('DejaVu', '', 11)
            self.cell(0, line_height, document_data.get('due_date', ''), 0, 1)
        
        # Payment method if available
        if document_data.get('payment_method'):
            self.set_font('DejaVu', 'B', 11)
            self.cell(col_width, line_height, 'Méthode de paiement:', 0)
            self.set_font('DejaVu', '', 11)
            self.cell(0, line_height, document_data.get('payment_method', ''), 0, 1)
            
        self.ln(10)
    
    def items_table(self, items):
        """Add table with line items"""
        # Table header
        self.set_fill_color(240, 240, 240)
        self.set_font('DejaVu', 'B', 10)
        
        # Column widths
        w_desc = 80
        w_qty = 20
        w_price = 30
        w_tva = 20
        w_total = 35
        
        # Header
        self.cell(w_desc, 10, 'Description', 1, 0, 'C', True)
        self.cell(w_qty, 10, 'Qté', 1, 0, 'C', True)
        self.cell(w_price, 10, 'Prix HT', 1, 0, 'C', True)
        self.cell(w_tva, 10, 'TVA %', 1, 0, 'C', True)
        self.cell(w_total, 10, 'Total HT', 1, 1, 'C', True)
        
        # Items
        self.set_font('DejaVu', '', 10)
        for item in items:
            # Check if we need a page break
            if self.get_y() > 250:
                self.add_page()
            
            # Handle multi-line descriptions
            desc = item.get('description', '')
            lines = self.multi_cell_prep(desc, w_desc)
            
            # First line with all columns
            self.cell(w_desc, 8, lines[0] if lines else '', 'LR', 0)
            self.cell(w_qty, 8, str(item.get('quantite', '')), 'LR', 0, 'C')
            self.cell(w_price, 8, f"{item.get('prix_unitaire_ht', 0):.2f} €", 'LR', 0, 'R')
            self.cell(w_tva, 8, f"{item.get('tva', 0):.1f}%", 'LR', 0, 'C')
            self.cell(w_total, 8, f"{item.get('total_ht', 0):.2f} €", 'LR', 1, 'R')
            
            # Additional description lines if any
            for i in range(1, len(lines)):
                self.cell(w_desc, 8, lines[i], 'LR', 0)
                self.cell(w_qty, 8, '', 'LR', 0)
                self.cell(w_price, 8, '', 'LR', 0)
                self.cell(w_tva, 8, '', 'LR', 0)
                self.cell(w_total, 8, '', 'LR', 1)
        
        # Table footer line
        self.cell(w_desc + w_qty + w_price + w_tva + w_total, 0, '', 'T', 1)
        self.ln(5)
    
    def totals_section(self, totals):
        """Add totals section"""
        self.set_font('DejaVu', 'B', 10)
        w1 = 150
        w2 = 35
        
        # Total HT
        self.cell(w1, 8, 'Total HT:', 0, 0, 'R')
        self.cell(w2, 8, f"{totals.get('total_ht', 0):.2f} €", 0, 1, 'R')
        
        # TVA
        self.cell(w1, 8, 'Total TVA:', 0, 0, 'R')
        self.cell(w2, 8, f"{totals.get('total_tva', 0):.2f} €", 0, 1, 'R')
        
        # Total TTC
        self.set_font('DejaVu', 'B', 12)
        self.cell(w1, 10, 'Total TTC:', 0, 0, 'R')
        self.cell(w2, 10, f"{totals.get('total_ttc', 0):.2f} €", 0, 1, 'R')
        
        self.ln(10)
    
    def notes_section(self, notes):
        """Add notes section if notes are provided"""
        if notes:
            self.set_font('DejaVu', 'B', 11)
            self.cell(0, 8, 'Notes:', 0, 1)
            
            self.set_font('DejaVu', '', 10)
            self.multi_cell(0, 6, notes)
            self.ln(5)
    
    def payment_instructions(self):
        """Add payment instructions"""
        self.set_font('DejaVu', 'B', 11)
        self.cell(0, 8, 'Conditions de paiement:', 0, 1)
        
        self.set_font('DejaVu', '', 10)
        if self.document_type == "FACTURE":
            self.multi_cell(0, 6, 'Paiement exigible à réception de la facture.\nVeuillez effectuer le paiement dans les 30 jours suivant la date de la facture.')
        else:
            self.multi_cell(0, 6, 'Ce devis est valable pour une durée de 30 jours à compter de sa date d\'émission.')
    
    def multi_cell_prep(self, txt, w):
        """Prepare text for multi-line cell"""
        # Store current position
        x = self.get_x()
        y = self.get_y()
        
        # Calculate how many lines the text will take
        self.set_xy(0, 0)  # Move to dummy position
        self.multi_cell(w, 5, txt)
        lines = self.get_y() / 5
        
        # Reset position
        self.set_xy(x, y)
        
        # Split text into lines
        result = []
        start = 0
        for i in range(int(lines)):
            length = len(txt) // int(lines)
            while start + length < len(txt) and txt[start + length] != ' ':
                length += 1
            result.append(txt[start:start + length])
            start += length
            while start < len(txt) and txt[start] == ' ':
                start += 1
                
        return result or [""]


def generate_invoice_pdf(
    document_data: Dict[str, Any],
    client_data: Dict[str, Any],
    items: List[Dict[str, Any]],
    custom_note: Optional[str] = None
) -> str:
    """
    Generate a PDF invoice or quote
    
    Args:
        document_data: Document information (type, number, dates, etc.)
        client_data: Client information
        items: List of line items
        custom_note: Optional custom note to add to the document
        
    Returns:
        Path to the generated PDF file
    """
    # Create PDF object
    pdf = InvoicePDF(document_data.get('type', 'facture'))
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Add document information
    document_number = str(document_data.get('id', '0001'))
    pdf.document_title(document_number)
    pdf.client_info(client_data)
    
    # Format dates
    formatted_dates = {
        'date': document_data.get('date', datetime.now()).strftime('%d/%m/%Y'),
    }
    
    if document_data.get('due_date'):
        formatted_dates['due_date'] = document_data.get('due_date').strftime('%d/%m/%Y')
    
    doc_info = {**document_data, **formatted_dates}
    pdf.document_info(doc_info)
    
    # Add items table
    pdf.items_table(items)
    
    # Add totals
    totals = {
        'total_ht': document_data.get('total_ht', 0),
        'total_tva': document_data.get('total_tva', 0),
        'total_ttc': document_data.get('total_ttc', 0)
    }
    pdf.totals_section(totals)
    
    # Add notes
    notes = custom_note or document_data.get('notes', '')
    pdf.notes_section(notes)
    
    # Add payment instructions
    pdf.payment_instructions()
    
    # Generate temporary file path
    file_name = f"{document_data.get('type', 'document')}_{document_number}_{uuid4().hex[:8]}.pdf"
    file_path = os.path.join(tempfile.gettempdir(), file_name)
    
    # Save PDF
    pdf.output(file_path)
    
    return file_path
