from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from decimal import Decimal

from app.database import get_db
from app.models.users import User
from app.schemas.users import UserCreate, UserUpdate, UserResponse, FreelanceProfileResponse
from app.dependencies import get_current_user, get_current_active_user, check_admin_role
from app.utils.stripe import create_stripe_connect_account, get_stripe_dashboard_link

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[str] = None,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """
    Get list of users (admin only)
    """
    query = db.query(User)
    
    # Apply filters
    if search:
        query = query.filter(
            (User.full_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%")) |
            (User.company_name.ilike(f"%{search}%"))
        )
    
    if role:
        query = query.filter(User.role == role)
    
    # Apply pagination
    total = query.count()
    users = query.order_by(User.id).offset(skip).limit(limit).all()
    
    return users

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user
    """
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_user_me(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update current user information
    """
    # Update user attributes
    for key, value in user_data.dict(exclude_unset=True).items():
        setattr(current_user, key, value)
    
    db.commit()
    db.refresh(current_user)
    
    return current_user

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get user by ID (admin access or own profile)
    """
    # Check permissions
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """
    Update user information (admin only)
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update user attributes
    for key, value in user_data.dict(exclude_unset=True).items():
        setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/stripe/connect", response_model=Dict[str, str])
async def create_stripe_connect(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create Stripe Connect Express account for current user
    """
    # Check if user already has a Stripe account
    if current_user.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a Stripe account"
        )
    
    # Create Stripe account
    stripe_account = create_stripe_connect_account({
        "id": current_user.id,
        "email": current_user.email,
        "country": current_user.country or "FR",
        "website": current_user.website
    })
    
    # Update user with Stripe account info
    current_user.stripe_account_id = stripe_account.get("stripe_account_id")
    current_user.stripe_dashboard_url = stripe_account.get("dashboard_url")
    db.commit()
    
    return {
        "message": "Stripe Connect account created successfully",
        "onboarding_url": stripe_account.get("onboarding_url")
    }

@router.get("/stripe/dashboard", response_model=Dict[str, str])
async def get_stripe_dashboard(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get Stripe dashboard link for current user
    """
    # Check if user has a Stripe account
    if not current_user.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a Stripe account"
        )
    
    # Get dashboard link
    dashboard_url = get_stripe_dashboard_link(current_user.stripe_account_id)
    
    return {"dashboard_url": dashboard_url}

@router.get("/freelance/{user_id}", response_model=FreelanceProfileResponse)
async def get_freelance_profile(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get public freelancer profile by ID
    """
    # Get user with role 'freelance'
    user = db.query(User).filter(
        User.id == user_id,
        User.role == "freelance",
        User.account_status == "active"
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Freelancer not found"
        )
    
    return user

@router.get("/stats/dashboard", response_model=Dict[str, Any])
async def get_freelance_dashboard_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get dashboard statistics for current freelancer
    """
    # Check if user is a freelancer
    if current_user.role != "freelance" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a freelancer account"
        )
    
    # Get sales stats from database
    # This is a simplified version, in a real implementation you would join tables
    # and perform more complex queries
    
    # For this example, we'll return dummy data
    return {
        "total_revenue": current_user.total_revenue or Decimal('0.0'),
        "pending_payouts": Decimal('0.0'),
        "completed_sales": 0,
        "active_sales": 0,
        "average_rating": current_user.rating,
        "recent_activity": []
    }
