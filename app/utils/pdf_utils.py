import os
import logging
from datetime import datetime
from io import BytesIO
from fpdf import FPDF

# Configurer le logging
logger = logging.getLogger(__name__)

class InvoicePDF(FPDF):
    """
    Classe personnalisée pour générer des PDF de devis et factures
    """
    def __init__(self, document_data):
        super().__init__()
        self.doc_data = document_data
        self.set_margin(10)
        self.add_page()
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        # Logo et titre
        self.set_font('Arial', 'B', 16)
        doc_type = "DEVIS" if self.doc_data['type'] == 'devis' else "FACTURE"
        self.cell(0, 10, doc_type, 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 10, f"N° {self.doc_data['id']} - {self.format_date(self.doc_data['date'])}", 0, 1, 'C')
        self.ln(10)
        
    def footer(self):
        # Pied de page
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
        
    def format_date(self, date_str):
        """Formate une date ISO en format lisible"""
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date_obj.strftime('%d/%m/%Y')
        except:
            return date_str
        
    def format_amount(self, amount):
        """Formate un montant en euros"""
        return f"{amount:.2f} €"
        
    def add_company_info(self):
        """Ajoute les informations du freelance"""
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'ÉMETTEUR', 0, 1)
        self.set_font('Arial', '', 10)
        
        # Données du freelance (à remplacer par les vraies données)
        self.cell(0, 5, self.doc_data.get('freelance_name', 'Nom du freelance'), 0, 1)
        self.cell(0, 5, self.doc_data.get('freelance_email', 'Email du freelance'), 0, 1)
        self.ln(5)
        
    def add_client_info(self):
        """Ajoute les informations du client"""
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'CLIENT', 0, 1)
        self.set_font('Arial', '', 10)
        
        # Données du client
        self.cell(0, 5, self.doc_data.get('client_name', 'Nom du client'), 0, 1)
        self.cell(0, 5, self.doc_data.get('client_email', 'Email du client'), 0, 1)
        self.ln(15)
        
    def add_document_details(self):
        """Ajoute les détails du document (date, échéance, etc.)"""
        self.set_font('Arial', 'B', 10)
        
        # Date du document
        self.cell(40, 7, 'Date d\'émission:', 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 7, self.format_date(self.doc_data['date']), 0, 1)
        
        # Date d'échéance si disponible
        if self.doc_data.get('due_date'):
            self.set_font('Arial', 'B', 10)
            self.cell(40, 7, 'Date d\'échéance:', 0)
            self.set_font('Arial', '', 10)
            self.cell(0, 7, self.format_date(self.doc_data['due_date']), 0, 1)
        
        # Statut du document
        self.set_font('Arial', 'B', 10)
        self.cell(40, 7, 'Statut:', 0)
        self.set_font('Arial', '', 10)
        
        # Traduire le statut pour l'affichage
        status_map = {
            'en_attente': 'En attente',
            'envoyé': 'Envoyé',
            'payé': 'Payé',
            'annulé': 'Annulé'
        }
        status = status_map.get(self.doc_data.get('status', 'en_attente'), 'En attente')
        self.cell(0, 7, status, 0, 1)
        
        self.ln(10)
        
    def add_document_lines(self):
        """Ajoute les lignes du document (prestations, produits, etc.)"""
        self.set_font('Arial', 'B', 10)
        
        # Entête du tableau
        col_widths = [10, 85, 20, 25, 15, 35]  # No, Description, Quantité, Prix HT, TVA, Total TTC
        self.cell(col_widths[0], 10, 'N°', 1, 0, 'C')
        self.cell(col_widths[1], 10, 'Description', 1, 0, 'C')
        self.cell(col_widths[2], 10, 'Quantité', 1, 0, 'C')
        self.cell(col_widths[3], 10, 'Prix HT', 1, 0, 'C')
        self.cell(col_widths[4], 10, 'TVA %', 1, 0, 'C')
        self.cell(col_widths[5], 10, 'Total TTC', 1, 1, 'C')
        
        self.set_font('Arial', '', 9)
        
        # Lignes du document
        lignes = self.doc_data.get('lignes', [])
        for i, ligne in enumerate(lignes):
            # Si la description est longue, la découper en plusieurs lignes
            description = ligne.get('description', '')
            
            # Numéro de ligne
            self.cell(col_widths[0], 10, str(i+1), 1, 0, 'C')
            
            # Description (potentiellement sur plusieurs lignes)
            self.multi_cell(col_widths[1], 10, description, 1, 'L')
            
            # Revenir en position pour continuer la ligne
            current_y = self.get_y()
            current_x = self.get_x() + col_widths[0] + col_widths[1]
            self.set_xy(current_x, current_y - 10)
            
            # Quantité
            qte = ligne.get('quantite', 1)
            self.cell(col_widths[2], 10, str(qte), 1, 0, 'R')
            
            # Prix unitaire HT
            prix_ht = ligne.get('prix_unitaire_ht', 0)
            self.cell(col_widths[3], 10, self.format_amount(prix_ht), 1, 0, 'R')
            
            # TVA
            tva = ligne.get('tva', 20)
            self.cell(col_widths[4], 10, f"{tva}%", 1, 0, 'R')
            
            # Total TTC
            total_ht = qte * prix_ht
            total_ttc = total_ht * (1 + tva/100)
            self.cell(col_widths[5], 10, self.format_amount(total_ttc), 1, 1, 'R')
        
        self.ln(10)
        
    def add_totals(self):
        """Ajoute les totaux du document"""
        self.set_font('Arial', 'B', 10)
        
        # Totaux HT, TVA et TTC
        self.cell(150, 7, 'Total HT:', 0, 0, 'R')
        self.set_font('Arial', '', 10)
        self.cell(0, 7, self.format_amount(float(self.doc_data.get('total_ht', 0))), 0, 1, 'R')
        
        self.set_font('Arial', 'B', 10)
        self.cell(150, 7, 'Total TVA:', 0, 0, 'R')
        self.set_font('Arial', '', 10)
        self.cell(0, 7, self.format_amount(float(self.doc_data.get('total_tva', 0))), 0, 1, 'R')
        
        self.set_font('Arial', 'B', 12)
        self.cell(150, 10, 'Total TTC:', 0, 0, 'R')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.format_amount(float(self.doc_data.get('total_ttc', 0))), 0, 1, 'R')
        
        self.ln(15)
        
    def add_notes(self):
        """Ajoute les notes ou commentaires du document"""
        if self.doc_data.get('notes'):
            self.set_font('Arial', 'B', 10)
            self.cell(0, 7, 'Notes:', 0, 1)
            self.set_font('Arial', '', 10)
            self.multi_cell(0, 7, self.doc_data.get('notes', ''))
            self.ln(10)
        
    def add_payment_info(self):
        """Ajoute les informations de paiement"""
        self.set_font('Arial', 'B', 10)
        self.cell(0, 7, 'Conditions de paiement:', 0, 1)
        self.set_font('Arial', '', 10)
        
        # Détecter si c'est un devis ou une facture
        if self.doc_data['type'] == 'devis':
            self.cell(0, 7, 'Ce devis est valable 30 jours à compter de sa date d\'émission.', 0, 1)
        else:  # facture
            due_date = self.format_date(self.doc_data.get('due_date', ''))
            self.cell(0, 7, f'Paiement à réception de facture. Date d\'échéance: {due_date}', 0, 1)
            
        self.ln(5)
        
    def generate(self):
        """Génère le PDF complet"""
        self.alias_nb_pages()
        self.add_company_info()
        self.add_client_info()
        self.add_document_details()
        self.add_document_lines()
        self.add_totals()
        self.add_notes()
        self.add_payment_info()
        
        return self.output(dest='S')

def generate_invoice_pdf(document_data):
    """
    Génère un PDF pour un devis ou une facture
    
    Args:
        document_data: Données du document (dict)
        
    Returns:
        bytes: Contenu du PDF
    """
    try:
        pdf = InvoicePDF(document_data)
        pdf_bytes = pdf.generate()
        return pdf_bytes
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise