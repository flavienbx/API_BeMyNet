from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from sqlalchemy import func

from app.database import get_db
from app.models.users import User
from app.models.clients import Client
from app.models.sales import Vente
from app.schemas.clients import ClientCreate, ClientUpdate, ClientResponse, ClientWithSalesResponse
from app.dependencies import get_current_user, get_current_active_user, check_admin_role

router = APIRouter()

@router.post("/", response_model=ClientResponse)
async def create_client(
    client_data: ClientCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new client
    """
    # Check if client with same email exists for this user
    existing_client = db.query(Client).filter(
        Client.email == client_data.email,
        Client.created_by_user == current_user.id
    ).first()
    
    if existing_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client with this email already exists"
        )
    
    # Create new client
    new_client = Client(
        **client_data.dict(),
        created_by_user=current_user.id
    )
    
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    
    return new_client

@router.get("/", response_model=List[ClientResponse])
async def get_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of clients for the current user
    """
    query = db.query(Client)
    
    # Filter by creator unless admin
    if current_user.role != "admin":
        query = query.filter(Client.created_by_user == current_user.id)
    
    # Apply search filter
    if search:
        query = query.filter(
            (Client.full_name.ilike(f"%{search}%")) |
            (Client.email.ilike(f"%{search}%")) |
            (Client.company_name.ilike(f"%{search}%"))
        )
    
    # Apply pagination
    total = query.count()
    clients = query.order_by(Client.id).offset(skip).limit(limit).all()
    
    return clients

@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get client by ID
    """
    # Get client
    client = db.query(Client).filter(Client.id == client_id).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Check permissions
    if client.created_by_user != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return client

@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    client_data: ClientUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update client information
    """
    # Get client
    client = db.query(Client).filter(Client.id == client_id).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Check permissions
    if client.created_by_user != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update client attributes
    for key, value in client_data.dict(exclude_unset=True).items():
        setattr(client, key, value)
    
    db.commit()
    db.refresh(client)
    
    return client

@router.delete("/{client_id}", response_model=Dict[str, str])
async def delete_client(
    client_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete client
    """
    # Get client
    client = db.query(Client).filter(Client.id == client_id).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Check permissions
    if client.created_by_user != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Check if client has associated sales
    sales_count = db.query(Vente).filter(Vente.client_id == client_id).count()
    if sales_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete client with associated sales"
        )
    
    # Delete client
    db.delete(client)
    db.commit()
    
    return {"message": "Client deleted successfully"}

@router.get("/{client_id}/with-sales", response_model=ClientWithSalesResponse)
async def get_client_with_sales(
    client_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get client with sales information
    """
    # Get client
    client = db.query(Client).filter(Client.id == client_id).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Check permissions
    if client.created_by_user != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get sales for this client
    sales = db.query(Vente).filter(Vente.client_id == client_id).all()
    
    # Calculate total sales amount
    total_amount = db.query(func.sum(Vente.montant)).filter(Vente.client_id == client_id).scalar() or 0
    
    # Prepare response
    response = client.__dict__.copy()
    response.update({
        "total_sales": len(sales),
        "total_amount": total_amount,
        "sales": [
            {
                "id": sale.id,
                "date": sale.date,
                "montant": sale.montant,
                "statut_paiement": sale.statut_paiement
            }
            for sale in sales
        ]
    })
    
    return response
