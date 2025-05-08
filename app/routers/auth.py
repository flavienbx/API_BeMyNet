from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import urllib.parse
import json
import jwt

from app.database import get_db
from app.models.users import User
from app.models.auth import Authentification
from app.schemas.auth import (
    Token, TokenData, LoginRequest, RefreshTokenRequest, 
    SocialAuthRedirectResponse, SocialAuthCallbackRequest,
    PasswordChangeRequest, PasswordResetRequest, PasswordResetConfirm
)
from app.schemas.users import UserCreate, UserResponse
from app.utils.auth import (
    verify_password, get_password_hash, create_tokens,
    generate_oauth_redirect_uri, exchange_code_for_token,
    get_google_user_info, get_discord_user_info
)
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    new_user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        role="client",
        account_status="active",
        phone_number=user_data.phone_number,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.flush()

    hashed_password = get_password_hash(user_data.password)
    auth = Authentification(
        user_id=new_user.id,
        provider="email",
        email=user_data.email,
        password_hash=hashed_password,
        created_at=datetime.utcnow(),
        last_login_at=datetime.utcnow()
    )
    db.add(auth)
    db.commit()

    tokens = create_tokens(
        new_user.id,
        name=new_user.full_name,
        email=new_user.email,
        role=new_user.role
    )
    
    return tokens

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth = db.query(Authentification).filter(
        Authentification.user_id == user.id,
        Authentification.provider == "email"
    ).first()
    
    if not auth or not verify_password(form_data.password, auth.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.utcnow()
    auth.last_login_at = datetime.utcnow()
    db.commit()

    tokens = create_tokens(
        user.id,
        name=user.full_name,
        email=user.email,
        role=user.role
    )
    
    return tokens

@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    auth = db.query(Authentification).filter(
        Authentification.user_id == user.id,
        Authentification.provider == "email"
    ).first()
    
    if not auth or not verify_password(login_data.password, auth.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    user.last_login_at = datetime.utcnow()
    auth.last_login_at = datetime.utcnow()
    db.commit()

    tokens = create_tokens(
        user.id,
        name=user.full_name,
        email=user.email,
        role=user.role
    )

    return tokens

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            refresh_data.refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        if payload.get("type") != "refresh_token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        user_id = int(payload.get("sub"))
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        tokens = create_tokens(
            user.id,
            name=user.full_name,
            email=user.email,
            role=user.role
        )

        return tokens

    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information
    """
    return current_user

@router.post("/change-password", response_model=Dict[str, str])
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password
    """
    # Get authentication record with password
    auth = db.query(Authentification).filter(
        Authentification.user_id == current_user.id,
        Authentification.provider == "email"
    ).first()
    
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email authentication not found"
        )
    
    # Verify current password
    if not verify_password(password_data.current_password, auth.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    auth.password_hash = get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

@router.get("/google", response_model=SocialAuthRedirectResponse)
async def google_login():
    """
    Get Google OAuth login URL
    """
    auth_url = generate_oauth_redirect_uri("google")
    return {"auth_url": auth_url}

@router.get("/discord", response_model=SocialAuthRedirectResponse)
async def discord_login():
    """
    Get Discord OAuth login URL
    """
    auth_url = generate_oauth_redirect_uri("discord")
    return {"auth_url": auth_url}

@router.get("/google/callback")
async def google_callback(
    code: str,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        token_data = await exchange_code_for_token("google", code)
        user_info = await get_google_user_info(token_data.get("access_token"))
        user = await find_or_create_social_user(
            db=db,
            provider="google",
            provider_user_id=user_info.get("provider_user_id"),
            email=user_info.get("email"),
            full_name=user_info.get("full_name")
        )

        tokens = create_tokens(
            user.id,
            name=user.full_name,
            email=user.email,
            role=user.role
        )

        redirect_url = f"https://bemynet.fr/auth/oauth.php?access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}&token_type=bearer"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"{settings.FRONTEND_URL}?message={error_message}")

@router.get("/discord/callback")
async def discord_callback(
    code: str,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        token_data = await exchange_code_for_token("discord", code)
        user_info = await get_discord_user_info(token_data.get("access_token"))
        user = await find_or_create_social_user(
            db=db,
            provider="discord",
            provider_user_id=user_info.get("provider_user_id"),
            email=user_info.get("email"),
            full_name=user_info.get("full_name")
        )

        tokens = create_tokens(
            user.id,
            name=user.full_name,
            email=user.email,
            role=user.role
        )
        print("✅ Redirection vers :", redirect_url)
        redirect_url = f"https://bemynet.fr/auth/oauth.php?access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}&token_type=bearer"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        print("⚠️ Erreur Discord callback:", str(e))  # debug
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"https://google.com?message={error_message}")


@router.post("/reset-password", response_model=Dict[str, str])
async def request_password_reset(
    reset_data: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset (sends email with reset link)
    """
    user = db.query(User).filter(User.email == reset_data.email).first()
    if not user:
        # Don't reveal that email doesn't exist
        return {"message": "If your email is registered, you will receive a password reset link."}
    
    # In a real implementation, send an email with a reset link
    # For this exercise, we'll just return a success message
    
    return {"message": "If your email is registered, you will receive a password reset link."}

# Helper function for social authentication
async def find_or_create_social_user(
    db: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    full_name: Optional[str] = None
) -> User:
    """
    Find or create a user for social authentication
    """
    # Check if authentication record exists
    auth = db.query(Authentification).filter(
        Authentification.provider == provider,
        Authentification.provider_user_id == provider_user_id
    ).first()
    
    if auth:
        # Update last login time
        auth.last_login_at = datetime.utcnow()
        user = db.query(User).filter(User.id == auth.user_id).first()
        if user:
            user.last_login_at = datetime.utcnow()
            db.commit()
            return user
    
    # Check if user exists with the same email
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # Create new user
        user = User(
            email=email,
            full_name=full_name,
            role="client",  # Default role
            account_status="active",
            created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow()
        )
        db.add(user)
        db.flush()
    
    # Create or update authentication record
    if not auth:
        auth = Authentification(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow()
        )
        db.add(auth)
    
    db.commit()
    return user
