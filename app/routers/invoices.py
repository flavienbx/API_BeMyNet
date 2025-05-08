from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import os
from fastapi.responses import FileResponse

from app.database import get_db
from app.models.users import User
from app.models.clients import Client
from app.models.invoices import DevisFacture, DevisFactureLigne
from app.schemas.invoices import (
    DevisFactureCreate, DevisFactureUpdate, DevisFactureResponse, 
    DevisFactureDetailResponse, DevisFactureListResponse, LigneCreate,
    LigneUpdate, LigneResponse, DocumentType, DocumentStatus,
    PDFGenerateRequest
)
from app.dependencies import get_current_user, get_current_active_user, check_admin_role
from app.utils.pdf import generate_invoice_pdf

router = APIRouter()

@router.post("/", response_model=DevisFactureDetailResponse)
async def create_devis_facture(
    document_data: DevisFactureCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new quote or invoice
    """
    # Validate user_id (must be current user or admin)
    if document_data.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create documents for your own account"
        )
    
    # Check if client exists
    client = db.query(Client).filter(Client.id == document_data.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Set default due date (30 days from now)
    if not document_data.due_date:
        document_data.due_date = datetime.utcnow() + timedelta(days=30)
    
    # Calculate totals from line items
    total_ht = Decimal('0.0')
    total_tva = Decimal('0.0')
    total_ttc = Decimal('0.0')
    
    for ligne in document_data.lignes:
        # Calculate line totals
        ligne_total_ht = ligne.quantite * ligne.prix_unitaire_ht
        ligne_total_tva = ligne_total_ht * (ligne.tva / 100)
        ligne_total_ttc = ligne_total_ht + ligne_total_tva
        
        # Add to document totals
        total_ht += ligne_total_ht
        total_tva += ligne_total_tva
        total_ttc += ligne_total_ttc
    
    # Create new document
    new_document = DevisFacture(
        user_id=document_data.user_id,
        client_id=document_data.client_id,
        type=document_data.type,
        status=document_data.status,
        date=datetime.utcnow(),
        due_date=document_data.due_date,
        payment_method=document_data.payment_method,
        total_ht=total_ht,
        total_tva=total_tva,
        total_ttc=total_ttc,
        notes=document_data.notes
    )
    
    db.add(new_document)
    db.flush()
    
    # Create line items
    lignes = []
    for i, ligne_data in enumerate(document_data.lignes):
        ligne = DevisFactureLigne(
            devis_id=new_document.id,
            ordre=i + 1,
            type_ligne=ligne_data.type_ligne,
            description=ligne_data.description,
            quantite=ligne_data.quantite,
            prix_unitaire_ht=ligne_data.prix_unitaire_ht,
            tva=ligne_data.tva
        )
        db.add(ligne)
        lignes.append(ligne)
    
    db.commit()
    db.refresh(new_document)
    
    # Prepare response
    response = new_document.__dict__.copy()
    response.update({
        "lignes": lignes,
        "client": client.__dict__,
        "freelance": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email
        }
    })
    
    return response

@router.get("/", response_model=DevisFactureListResponse)
async def get_devis_factures(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    type: Optional[str] = None,
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of quotes and invoices
    """
    query = db.query(DevisFacture)
    
    # Filter by role
    if current_user.role != "admin":
        query = query.filter(DevisFacture.user_id == current_user.id)
    
    # Apply filters
    if type:
        query = query.filter(DevisFacture.type == type)
    
    if status:
        query = query.filter(DevisFacture.status == status)
    
    if client_id:
        query = query.filter(DevisFacture.client_id == client_id)
    
    # Apply pagination
    total = query.count()
    documents = query.order_by(DevisFacture.date.desc()).offset(skip).limit(limit).all()
    
    return {
        "documents": documents,
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit
    }

@router.get("/{document_id}", response_model=DevisFactureDetailResponse)
async def get_devis_facture(
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get quote or invoice details by ID
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get related entities
    client = db.query(Client).filter(Client.id == document.client_id).first()
    freelance = db.query(User).filter(User.id == document.user_id).first()
    lignes = db.query(DevisFactureLigne).filter(DevisFactureLigne.devis_id == document_id).order_by(DevisFactureLigne.ordre).all()
    
    # Add computed fields to line items
    for ligne in lignes:
        ligne.__dict__["total_ht"] = ligne.quantite * ligne.prix_unitaire_ht
        ligne.__dict__["total_tva"] = ligne.__dict__["total_ht"] * (ligne.tva / 100)
        ligne.__dict__["total_ttc"] = ligne.__dict__["total_ht"] + ligne.__dict__["total_tva"]
    
    # Prepare detailed response
    response = document.__dict__.copy()
    response.update({
        "lignes": lignes,
        "client": client.__dict__ if client else None,
        "freelance": {
            "id": freelance.id,
            "full_name": freelance.full_name,
            "email": freelance.email
        } if freelance else None
    })
    
    return response

@router.put("/{document_id}", response_model=DevisFactureResponse)
async def update_devis_facture(
    document_id: int,
    document_data: DevisFactureUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update quote or invoice information
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update document attributes
    for key, value in document_data.dict(exclude_unset=True).items():
        setattr(document, key, value)
    
    db.commit()
    db.refresh(document)
    
    return document

@router.delete("/{document_id}", response_model=Dict[str, str])
async def delete_devis_facture(
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete quote or invoice
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Check if document is already paid
    if document.status == "payé":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a paid document"
        )
    
    # Delete line items (cascade should handle this automatically)
    db.query(DevisFactureLigne).filter(DevisFactureLigne.devis_id == document_id).delete()
    
    # Delete document
    db.delete(document)
    db.commit()
    
    return {"message": "Document deleted successfully"}

@router.post("/{document_id}/lines", response_model=LigneResponse)
async def add_line_to_document(
    document_id: int,
    line_data: LigneCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Add a new line item to a document
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get max order
    max_order = db.query(DevisFactureLigne).filter(
        DevisFactureLigne.devis_id == document_id
    ).order_by(DevisFactureLigne.ordre.desc()).first()
    
    next_order = 1
    if max_order:
        next_order = max_order.ordre + 1
    
    # Create new line item
    new_line = DevisFactureLigne(
        devis_id=document_id,
        ordre=line_data.ordre or next_order,
        type_ligne=line_data.type_ligne,
        description=line_data.description,
        quantite=line_data.quantite,
        prix_unitaire_ht=line_data.prix_unitaire_ht,
        tva=line_data.tva
    )
    
    db.add(new_line)
    db.flush()
    
    # Update document totals
    ligne_total_ht = new_line.quantite * new_line.prix_unitaire_ht
    ligne_total_tva = ligne_total_ht * (new_line.tva / 100)
    ligne_total_ttc = ligne_total_ht + ligne_total_tva
    
    document.total_ht += ligne_total_ht
    document.total_tva += ligne_total_tva
    document.total_ttc += ligne_total_ttc
    
    db.commit()
    db.refresh(new_line)
    
    # Add computed fields to response
    new_line.__dict__["total_ht"] = ligne_total_ht
    new_line.__dict__["total_tva"] = ligne_total_tva
    new_line.__dict__["total_ttc"] = ligne_total_ttc
    
    return new_line

@router.put("/lines/{line_id}", response_model=LigneResponse)
async def update_line(
    line_id: int,
    line_data: LigneUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update a line item
    """
    # Get line
    line = db.query(DevisFactureLigne).filter(DevisFactureLigne.id == line_id).first()
    
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line not found"
        )
    
    # Get document to check permissions
    document = db.query(DevisFacture).filter(DevisFacture.id == line.devis_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Calculate old totals
    old_total_ht = line.quantite * line.prix_unitaire_ht
    old_total_tva = old_total_ht * (line.tva / 100)
    old_total_ttc = old_total_ht + old_total_tva
    
    # Update line attributes
    for key, value in line_data.dict(exclude_unset=True).items():
        setattr(line, key, value)
    
    db.flush()
    
    # Calculate new totals
    new_total_ht = line.quantite * line.prix_unitaire_ht
    new_total_tva = new_total_ht * (line.tva / 100)
    new_total_ttc = new_total_ht + new_total_tva
    
    # Update document totals
    document.total_ht = document.total_ht - old_total_ht + new_total_ht
    document.total_tva = document.total_tva - old_total_tva + new_total_tva
    document.total_ttc = document.total_ttc - old_total_ttc + new_total_ttc
    
    db.commit()
    db.refresh(line)
    
    # Add computed fields to response
    line.__dict__["total_ht"] = new_total_ht
    line.__dict__["total_tva"] = new_total_tva
    line.__dict__["total_ttc"] = new_total_ttc
    
    return line

@router.delete("/lines/{line_id}", response_model=Dict[str, str])
async def delete_line(
    line_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a line item
    """
    # Get line
    line = db.query(DevisFactureLigne).filter(DevisFactureLigne.id == line_id).first()
    
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line not found"
        )
    
    # Get document to check permissions
    document = db.query(DevisFacture).filter(DevisFacture.id == line.devis_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Calculate line totals
    line_total_ht = line.quantite * line.prix_unitaire_ht
    line_total_tva = line_total_ht * (line.tva / 100)
    line_total_ttc = line_total_ht + line_total_tva
    
    # Update document totals
    document.total_ht -= line_total_ht
    document.total_tva -= line_total_tva
    document.total_ttc -= line_total_ttc
    
    # Delete line
    db.delete(line)
    db.commit()
    
    return {"message": "Line deleted successfully"}

@router.post("/{document_id}/pdf", response_model=Dict[str, str])
async def generate_pdf(
    document_id: int,
    pdf_data: PDFGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate PDF for a quote or invoice
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get related entities
    client = db.query(Client).filter(Client.id == document.client_id).first()
    lignes = db.query(DevisFactureLigne).filter(
        DevisFactureLigne.devis_id == document_id
    ).order_by(DevisFactureLigne.ordre).all()
    
    # Prepare data for PDF generation
    document_data = document.__dict__.copy()
    client_data = client.__dict__ if client else {}
    
    # Prepare line items with calculated totals
    items = []
    for ligne in lignes:
        total_ht = ligne.quantite * ligne.prix_unitaire_ht
        items.append({
            "description": ligne.description,
            "quantite": ligne.quantite,
            "prix_unitaire_ht": ligne.prix_unitaire_ht,
            "tva": ligne.tva,
            "total_ht": total_ht,
            "total_tva": total_ht * (ligne.tva / 100),
            "total_ttc": total_ht * (1 + (ligne.tva / 100))
        })
    
    # Generate PDF
    pdf_path = generate_invoice_pdf(
        document_data=document_data,
        client_data=client_data,
        items=items,
        custom_note=pdf_data.custom_note
    )
    
    # Update document with PDF URL
    document.pdf_url = pdf_path
    db.commit()
    
    return {"pdf_url": pdf_path, "message": "PDF generated successfully"}

@router.get("/{document_id}/pdf", response_class=FileResponse)
async def download_pdf(
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Download the PDF for a quote or invoice
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Check if PDF exists
    if not document.pdf_url or not os.path.exists(document.pdf_url):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not found, generate it first"
        )
    
    # Return file
    return FileResponse(
        document.pdf_url,
        filename=f"{document.type}_{document.id}.pdf",
        media_type="application/pdf"
    )

@router.post("/{document_id}/mark-as-paid", response_model=DevisFactureResponse)
async def mark_as_paid(
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Mark a document as paid
    """
    # Get document
    document = db.query(DevisFacture).filter(DevisFacture.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update status and payment date
    document.status = "payé"
    document.payment_date = datetime.utcnow()
    db.commit()
    db.refresh(document)
    
    return document
