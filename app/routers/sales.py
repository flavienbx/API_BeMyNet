from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.models.users import User
from app.models.sales import Vente, Affiliation
from app.models.products import Produit
from app.models.clients import Client
from app.models.partners import Commercial, Partenaire
from app.schemas.sales import (
    VenteCreate, VenteUpdate, VenteResponse, VenteDetailResponse, 
    VenteListResponse, CommissionResponse, VenteCalculateCommission
)
from app.dependencies import get_current_user, get_current_active_user, check_admin_role, check_freelance_role
from app.utils.stripe import calculate_commissions_with_partners

router = APIRouter()

@router.post("/", response_model=VenteResponse)
async def create_sale(
    sale_data: VenteCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new sale
    """
    # Validate user_id (must be current user or admin)
    if sale_data.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create sales for your own account"
        )
    
    # Check if client exists
    client = db.query(Client).filter(Client.id == sale_data.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Check if product exists
    product = db.query(Produit).filter(Produit.id == sale_data.produit_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if product is active
    if not product.actif:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product is not active"
        )
    
    # Get commercial commission rate if applicable
    commercial_rate = None
    if sale_data.commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == sale_data.commercial_id).first()
        if not commercial:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Commercial not found"
            )
        commercial_rate = commercial.pourcentage / 100 if commercial.pourcentage else None
    
    # Get partner commission rate if applicable
    partner_rate = None
    if sale_data.partenaire_id:
        partner = db.query(Partenaire).filter(Partenaire.id == sale_data.partenaire_id).first()
        if not partner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Partner not found"
            )
        partner_rate = partner.pourcentage / 100 if partner.pourcentage else None
    
    # Calculate commissions
    commission_data = calculate_commissions_with_partners(
        amount=sale_data.montant,
        discount=sale_data.discount_applied or Decimal('0.0'),
        commercial_rate=commercial_rate,
        partner_rate=partner_rate
    )
    
    # Create new sale with calculated commissions
    new_sale = Vente(
        user_id=sale_data.user_id,
        client_id=sale_data.client_id,
        produit_id=sale_data.produit_id,
        montant=sale_data.montant,
        discount_applied=sale_data.discount_applied or Decimal('0.0'),
        description=sale_data.description,
        date=datetime.utcnow(),
        source=sale_data.source,
        commission_plateforme=commission_data['platform_fee'],
        commission_commerciale=commission_data['commercial_commission'],
        commission_partenaire=commission_data['partner_commission'],
        montant_net_freelance=commission_data['net_amount'],
        commercial_id=sale_data.commercial_id,
        partenaire_id=sale_data.partenaire_id,
        statut_paiement="en_attente"
    )
    
    db.add(new_sale)
    db.commit()
    db.refresh(new_sale)
    
    # Update client lifetime value
    client.lifetime_value = (client.lifetime_value or Decimal('0.0')) + sale_data.montant
    client.last_purchase_date = datetime.utcnow()
    
    # Update freelancer revenue
    freelancer = db.query(User).filter(User.id == sale_data.user_id).first()
    if freelancer:
        freelancer.total_revenue = (freelancer.total_revenue or Decimal('0.0')) + commission_data['net_amount']
    
    db.commit()
    
    # Create affiliations if needed
    if sale_data.commercial_id:
        affiliation = Affiliation(
            source_type="commercial",
            source_id=sale_data.commercial_id,
            vente_id=new_sale.id,
            commission=commission_data['commercial_commission']
        )
        db.add(affiliation)
    
    if sale_data.partenaire_id:
        affiliation = Affiliation(
            source_type="partenaire",
            source_id=sale_data.partenaire_id,
            vente_id=new_sale.id,
            commission=commission_data['partner_commission']
        )
        db.add(affiliation)
    
    db.commit()
    
    return new_sale

@router.get("/", response_model=VenteListResponse)
async def get_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status: Optional[str] = None,
    freelance_id: Optional[int] = None,
    client_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of sales (filtered by user role)
    """
    query = db.query(Vente)
    
    # Filter by role
    if current_user.role == "admin":
        # Admin can see all sales
        pass
    elif current_user.role == "freelance":
        # Freelancers can only see their own sales
        query = query.filter(Vente.user_id == current_user.id)
    else:
        # Other roles can see sales related to them
        # For example, commercials can see sales with their commission
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Apply filters
    if status:
        query = query.filter(Vente.statut_paiement == status)
    
    if freelance_id and current_user.role == "admin":
        query = query.filter(Vente.user_id == freelance_id)
    
    if client_id:
        query = query.filter(Vente.client_id == client_id)
    
    # Apply pagination
    total = query.count()
    sales = query.order_by(Vente.date.desc()).offset(skip).limit(limit).all()
    
    return {
        "ventes": sales,
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit
    }

@router.get("/{sale_id}", response_model=VenteDetailResponse)
async def get_sale(
    sale_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get sale details by ID
    """
    # Get sale
    sale = db.query(Vente).filter(Vente.id == sale_id).first()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    # Check permissions
    if sale.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get related entities
    client = db.query(Client).filter(Client.id == sale.client_id).first()
    freelance = db.query(User).filter(User.id == sale.user_id).first()
    product = db.query(Produit).filter(Produit.id == sale.produit_id).first()
    commercial = None
    partenaire = None
    
    if sale.commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == sale.commercial_id).first()
    
    if sale.partenaire_id:
        partenaire = db.query(Partenaire).filter(Partenaire.id == sale.partenaire_id).first()
    
    # Prepare detailed response
    response = sale.__dict__.copy()
    response.update({
        "client": client.__dict__ if client else None,
        "freelance": {
            "id": freelance.id,
            "full_name": freelance.full_name,
            "email": freelance.email
        } if freelance else None,
        "produit": product.__dict__ if product else None,
        "commercial": commercial.__dict__ if commercial else None,
        "partenaire": partenaire.__dict__ if partenaire else None
    })
    
    return response

@router.put("/{sale_id}", response_model=VenteResponse)
async def update_sale(
    sale_id: int,
    sale_data: VenteUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update sale information
    """
    # Get sale
    sale = db.query(Vente).filter(Vente.id == sale_id).first()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    # Check permissions
    if sale.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update sale attributes (limited fields)
    for key, value in sale_data.dict(exclude_unset=True).items():
        setattr(sale, key, value)
    
    db.commit()
    db.refresh(sale)
    
    return sale

@router.delete("/{sale_id}", response_model=Dict[str, str])
async def delete_sale(
    sale_id: int,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """
    Delete sale (admin only)
    """
    # Get sale
    sale = db.query(Vente).filter(Vente.id == sale_id).first()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    # Delete associated affiliations
    db.query(Affiliation).filter(Affiliation.vente_id == sale_id).delete()
    
    # Delete sale
    db.delete(sale)
    db.commit()
    
    return {"message": "Sale deleted successfully"}

@router.post("/calculate-commission", response_model=CommissionResponse)
async def calculate_sale_commission(
    commission_data: VenteCalculateCommission,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Calculate commissions for a potential sale
    """
    # Validate user_id (must be current user or admin)
    if commission_data.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only calculate commissions for your own account"
        )
    
    # Get commercial commission rate if applicable
    commercial_rate = None
    if commission_data.commercial_id:
        commercial = db.query(Commercial).filter(Commercial.id == commission_data.commercial_id).first()
        if commercial:
            commercial_rate = commercial.pourcentage / 100 if commercial.pourcentage else None
    
    # Get partner commission rate if applicable
    partner_rate = None
    if commission_data.partenaire_id:
        partner = db.query(Partenaire).filter(Partenaire.id == commission_data.partenaire_id).first()
        if partner:
            partner_rate = partner.pourcentage / 100 if partner.pourcentage else None
    
    # Calculate commissions
    commission_result = calculate_commissions_with_partners(
        amount=commission_data.montant,
        discount=commission_data.discount_applied or Decimal('0.0'),
        commercial_rate=commercial_rate,
        partner_rate=partner_rate
    )
    
    # Prepare response
    return {
        "montant_brut": commission_result['gross_amount'],
        "discount_applied": commission_result['discount'],
        "montant_apres_remise": commission_result['discounted_amount'],
        "commission_plateforme": commission_result['platform_fee'],
        "commission_commerciale": commission_result['commercial_commission'],
        "commission_partenaire": commission_result['partner_commission'],
        "montant_net_freelance": commission_result['net_amount'],
        "details": commission_result
    }
