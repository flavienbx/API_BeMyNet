from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from sqlalchemy import func

from app.database import get_db
from app.models.users import User
from app.models.clients import Client
from app.models.sales import Vente
from app.models.reviews import AvisFreelance, AvisPlateforme
from app.schemas.reviews import (
    AvisFreelanceCreate, AvisFreelanceUpdate, AvisFreelanceResponse, 
    AvisFreelanceDetailResponse, AvisPlatformeCreate, 
    AvisPlatformeUpdate, AvisPlatformeResponse, AvisListResponse
)
from app.dependencies import get_current_user, get_current_active_user, check_admin_role

router = APIRouter()

@router.post("/freelance", response_model=AvisFreelanceResponse)
async def create_freelance_review(
    review_data: AvisFreelanceCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new review for a freelancer
    """
    # Verify that client exists
    client = db.query(Client).filter(Client.id == review_data.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Verify that freelancer exists
    freelancer = db.query(User).filter(User.id == review_data.user_id).first()
    if not freelancer or freelancer.role != "freelance":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Freelancer not found"
        )
    
    # Verify that the sale exists and is completed
    sale = db.query(Vente).filter(
        Vente.id == review_data.vente_id,
        Vente.user_id == review_data.user_id,
        Vente.client_id == review_data.client_id,
        Vente.statut_paiement == "payé"
    ).first()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed sale found between this freelancer and client"
        )
    
    # Check if review already exists for this sale
    existing_review = db.query(AvisFreelance).filter(
        AvisFreelance.vente_id == review_data.vente_id
    ).first()
    
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review already exists for this sale"
        )
    
    # Create new review
    new_review = AvisFreelance(
        user_id=review_data.user_id,
        client_id=review_data.client_id,
        vente_id=review_data.vente_id,
        note=review_data.note,
        commentaire=review_data.commentaire,
        date=datetime.utcnow(),
        visible=review_data.visible
    )
    
    db.add(new_review)
    
    # Update freelancer rating
    reviews = db.query(AvisFreelance).filter(
        AvisFreelance.user_id == review_data.user_id,
        AvisFreelance.visible == True
    ).all()
    
    if reviews:
        # Calculate average rating
        avg_rating = sum(review.note for review in reviews + [new_review]) / (len(reviews) + 1)
        freelancer.rating = avg_rating
    else:
        freelancer.rating = review_data.note
    
    db.commit()
    db.refresh(new_review)
    
    return new_review

@router.get("/freelance", response_model=AvisListResponse)
async def get_freelance_reviews(
    freelance_id: Optional[int] = None,
    client_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get list of reviews for freelancers
    """
    query = db.query(AvisFreelance).filter(AvisFreelance.visible == True)
    
    # Apply filters
    if freelance_id:
        query = query.filter(AvisFreelance.user_id == freelance_id)
    
    if client_id:
        query = query.filter(AvisFreelance.client_id == client_id)
    
    # Calculate average rating
    avg_rating = None
    if freelance_id:
        avg = db.query(func.avg(AvisFreelance.note)).filter(
            AvisFreelance.user_id == freelance_id,
            AvisFreelance.visible == True
        ).scalar()
        avg_rating = float(avg) if avg else None
    
    # Apply pagination
    total = query.count()
    reviews = query.order_by(AvisFreelance.date.desc()).offset(skip).limit(limit).all()
    
    return {
        "avis": reviews,
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit,
        "average_rating": avg_rating
    }

@router.get("/freelance/{review_id}", response_model=AvisFreelanceDetailResponse)
async def get_freelance_review(
    review_id: int,
    db: Session = Depends(get_db)
):
    """
    Get freelance review details by ID
    """
    # Get review
    review = db.query(AvisFreelance).filter(
        AvisFreelance.id == review_id,
        AvisFreelance.visible == True
    ).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Get related entities
    freelance = db.query(User).filter(User.id == review.user_id).first()
    client = db.query(Client).filter(Client.id == review.client_id).first()
    vente = db.query(Vente).filter(Vente.id == review.vente_id).first()
    
    # Prepare detailed response
    response = review.__dict__.copy()
    response.update({
        "freelance": {
            "id": freelance.id,
            "full_name": freelance.full_name,
            "email": freelance.email
        } if freelance else None,
        "client": client.__dict__ if client else None,
        "vente": {
            "id": vente.id,
            "montant": vente.montant,
            "date": vente.date,
            "description": vente.description
        } if vente else None
    })
    
    return response

@router.put("/freelance/{review_id}", response_model=AvisFreelanceResponse)
async def update_freelance_review(
    review_id: int,
    review_data: AvisFreelanceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update freelance review
    """
    # Get review
    review = db.query(AvisFreelance).filter(AvisFreelance.id == review_id).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check permissions (admin or client who created the review)
    client = db.query(Client).filter(Client.id == review.client_id).first()
    if current_user.role != "admin" and (not client or client.created_by_user != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update review attributes
    old_note = review.note
    
    for key, value in review_data.dict(exclude_unset=True).items():
        setattr(review, key, value)
    
    db.flush()
    
    # Update freelancer rating if note changed
    if review_data.note is not None and review_data.note != old_note:
        freelancer = db.query(User).filter(User.id == review.user_id).first()
        if freelancer:
            reviews = db.query(AvisFreelance).filter(
                AvisFreelance.user_id == review.user_id,
                AvisFreelance.visible == True
            ).all()
            
            if reviews:
                # Calculate average rating
                avg_rating = sum(r.note for r in reviews) / len(reviews)
                freelancer.rating = avg_rating
    
    db.commit()
    db.refresh(review)
    
    return review

@router.delete("/freelance/{review_id}", response_model=Dict[str, str])
async def delete_freelance_review(
    review_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete freelance review
    """
    # Get review
    review = db.query(AvisFreelance).filter(AvisFreelance.id == review_id).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check permissions (admin or client who created the review)
    client = db.query(Client).filter(Client.id == review.client_id).first()
    if current_user.role != "admin" and (not client or client.created_by_user != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Delete review
    db.delete(review)
    
    # Update freelancer rating
    freelancer = db.query(User).filter(User.id == review.user_id).first()
    if freelancer:
        reviews = db.query(AvisFreelance).filter(
            AvisFreelance.user_id == review.user_id,
            AvisFreelance.visible == True
        ).all()
        
        if reviews:
            # Calculate average rating
            avg_rating = sum(r.note for r in reviews) / len(reviews)
            freelancer.rating = avg_rating
        else:
            freelancer.rating = None
    
    db.commit()
    
    return {"message": "Review deleted successfully"}

@router.post("/platform", response_model=AvisPlatformeResponse)
async def create_platform_review(
    review_data: AvisPlatformeCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new review for the platform
    """
    # Set author data
    review_data.auteur_id = current_user.id
    review_data.auteur_role = current_user.role
    
    # Create new review
    new_review = AvisPlateforme(
        auteur_id=review_data.auteur_id,
        auteur_role=review_data.auteur_role,
        note=review_data.note,
        commentaire=review_data.commentaire,
        date=datetime.utcnow(),
        visible=review_data.visible,
        version_plateforme=review_data.version_plateforme,
        experience_type=review_data.experience_type
    )
    
    db.add(new_review)
    db.commit()
    db.refresh(new_review)
    
    return new_review

@router.get("/platform", response_model=AvisListResponse)
async def get_platform_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    version: Optional[str] = None,
    experience_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get list of platform reviews
    """
    query = db.query(AvisPlateforme).filter(AvisPlateforme.visible == True)
    
    # Apply filters
    if version:
        query = query.filter(AvisPlateforme.version_plateforme == version)
    
    if experience_type:
        query = query.filter(AvisPlateforme.experience_type == experience_type)
    
    # Calculate average rating
    avg = db.query(func.avg(AvisPlateforme.note)).filter(
        AvisPlateforme.visible == True
    ).scalar()
    avg_rating = float(avg) if avg else None
    
    # Apply pagination
    total = query.count()
    reviews = query.order_by(AvisPlateforme.date.desc()).offset(skip).limit(limit).all()
    
    return {
        "avis": reviews,
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit,
        "average_rating": avg_rating
    }

@router.get("/platform/{review_id}", response_model=AvisPlatformeResponse)
async def get_platform_review(
    review_id: int,
    db: Session = Depends(get_db)
):
    """
    Get platform review by ID
    """
    review = db.query(AvisPlateforme).filter(
        AvisPlateforme.id == review_id,
        AvisPlateforme.visible == True
    ).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    return review

@router.put("/platform/{review_id}", response_model=AvisPlatformeResponse)
async def update_platform_review(
    review_id: int,
    review_data: AvisPlatformeUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update platform review
    """
    # Get review
    review = db.query(AvisPlateforme).filter(AvisPlateforme.id == review_id).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check permissions (admin or author)
    if current_user.role != "admin" and review.auteur_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update review attributes
    for key, value in review_data.dict(exclude_unset=True).items():
        setattr(review, key, value)
    
    db.commit()
    db.refresh(review)
    
    return review

@router.delete("/platform/{review_id}", response_model=Dict[str, str])
async def delete_platform_review(
    review_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete platform review
    """
    # Get review
    review = db.query(AvisPlateforme).filter(AvisPlateforme.id == review_id).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check permissions (admin or author)
    if current_user.role != "admin" and review.auteur_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Delete review
    db.delete(review)
    db.commit()
    
    return {"message": "Review deleted successfully"}

@router.get("/stats/{freelance_id}", response_model=Dict[str, Any])
async def get_freelance_review_stats(
    freelance_id: int,
    db: Session = Depends(get_db)
):
    """
    Get review statistics for a freelancer
    """
    # Check if freelancer exists
    freelancer = db.query(User).filter(
        User.id == freelance_id,
        User.role == "freelance"
    ).first()
    
    if not freelancer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Freelancer not found"
        )
    
    # Get review stats
    reviews_count = db.query(func.count(AvisFreelance.id)).filter(
        AvisFreelance.user_id == freelance_id,
        AvisFreelance.visible == True
    ).scalar() or 0
    
    avg_rating = db.query(func.avg(AvisFreelance.note)).filter(
        AvisFreelance.user_id == freelance_id,
        AvisFreelance.visible == True
    ).scalar() or 0
    
    # Get rating breakdown
    rating_counts = {}
    for i in range(1, 6):
        count = db.query(func.count(AvisFreelance.id)).filter(
            AvisFreelance.user_id == freelance_id,
            AvisFreelance.note == i,
            AvisFreelance.visible == True
        ).scalar() or 0
        rating_counts[str(i)] = count
    
    # Get recent reviews
    recent_reviews = db.query(AvisFreelance).filter(
        AvisFreelance.user_id == freelance_id,
        AvisFreelance.visible == True
    ).order_by(AvisFreelance.date.desc()).limit(5).all()
    
    return {
        "freelance_id": freelance_id,
        "freelance_name": freelancer.full_name,
        "total_reviews": reviews_count,
        "average_rating": float(avg_rating),
        "rating_breakdown": rating_counts,
        "recent_reviews": [
            {
                "id": review.id,
                "note": review.note,
                "commentaire": review.commentaire,
                "date": review.date
            }
            for review in recent_reviews
        ]
    }
