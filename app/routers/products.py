from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from sqlalchemy import func

from app.database import get_db
from app.models.users import User
from app.models.products import Produit
from app.models.sales import Vente
from app.schemas.products import ProduitCreate, ProduitUpdate, ProduitResponse, ProduitListResponse, ProduitWithStatsResponse
from app.dependencies import get_current_user, get_current_active_user, check_admin_role, check_freelance_role

router = APIRouter()

@router.post("/", response_model=ProduitResponse)
async def create_product(
    product_data: ProduitCreate,
    current_user: User = Depends(check_freelance_role),
    db: Session = Depends(get_db)
):
    """
    Create a new product
    """
    # Create new product
    new_product = Produit(**product_data.dict())
    
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    return new_product

@router.get("/", response_model=ProduitListResponse)
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get list of products
    """
    query = db.query(Produit)
    
    # Apply filters
    if active_only:
        query = query.filter(Produit.actif == True)
    
    if search:
        query = query.filter(
            (Produit.nom.ilike(f"%{search}%")) |
            (Produit.description.ilike(f"%{search}%"))
        )
    
    if category:
        query = query.filter(Produit.category == category)
    
    # Apply pagination
    total = query.count()
    products = query.order_by(Produit.id).offset(skip).limit(limit).all()
    
    return {
        "produits": products,
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit
    }

@router.get("/{product_id}", response_model=ProduitResponse)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get product by ID
    """
    # Get product
    product = db.query(Produit).filter(Produit.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return product

@router.put("/{product_id}", response_model=ProduitResponse)
async def update_product(
    product_id: int,
    product_data: ProduitUpdate,
    current_user: User = Depends(check_freelance_role),
    db: Session = Depends(get_db)
):
    """
    Update product information
    """
    # Get product
    product = db.query(Produit).filter(Produit.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Update product attributes
    for key, value in product_data.dict(exclude_unset=True).items():
        setattr(product, key, value)
    
    db.commit()
    db.refresh(product)
    
    return product

@router.delete("/{product_id}", response_model=Dict[str, str])
async def delete_product(
    product_id: int,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """
    Delete product (admin only)
    """
    # Get product
    product = db.query(Produit).filter(Produit.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if product has associated sales
    sales_count = db.query(Vente).filter(Vente.produit_id == product_id).count()
    if sales_count > 0:
        # Instead of deleting, mark as inactive
        product.actif = False
        db.commit()
        return {"message": "Product marked as inactive due to associated sales"}
    
    # Delete product
    db.delete(product)
    db.commit()
    
    return {"message": "Product deleted successfully"}

@router.get("/{product_id}/stats", response_model=ProduitWithStatsResponse)
async def get_product_stats(
    product_id: int,
    current_user: User = Depends(check_freelance_role),
    db: Session = Depends(get_db)
):
    """
    Get product statistics
    """
    # Get product
    product = db.query(Produit).filter(Produit.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Get sales stats
    sales_count = db.query(func.count(Vente.id)).filter(Vente.produit_id == product_id).scalar() or 0
    total_revenue = db.query(func.sum(Vente.montant)).filter(Vente.produit_id == product_id).scalar() or 0
    
    # Prepare response
    response = product.__dict__.copy()
    response.update({
        "total_sales": sales_count,
        "total_revenue": total_revenue,
        "average_rating": None  # Would require joining with ratings table
    })
    
    return response

@router.get("/categories", response_model=List[str])
async def get_product_categories(
    db: Session = Depends(get_db)
):
    """
    Get all unique product categories
    """
    categories = db.query(Produit.category).distinct().all()
    return [category[0] for category in categories if category[0]]
