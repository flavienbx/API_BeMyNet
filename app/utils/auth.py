from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
import secrets
import string
import httpx
from fastapi import HTTPException, status

from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify if the plain password matches the hashed password"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_jwt_token(data: Dict[str, Any], token_type: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token with the provided data
    
    Args:
        data: Dictionary containing data to encode in the token
        token_type: Type of token ('access_token' or 'refresh_token')
        expires_delta: Optional expiration time delta
        
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif token_type == "access_token":
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    elif token_type == "refresh_token":
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)  # Default
    
    # Add claims to token
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": token_type
    })
    
    # Encode token
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt

def create_tokens(user_id: int) -> Dict[str, Any]:
    """
    Create access and refresh tokens for a user
    
    Args:
        user_id: ID of the user
        
    Returns:
        Dictionary with access_token, refresh_token, token_type, and expires_in
    """
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_jwt_token(
        data={"sub": str(user_id)},
        token_type="access_token",
        expires_delta=access_token_expires
    )
    
    # Create refresh token
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_jwt_token(
        data={"sub": str(user_id)},
        token_type="refresh_token",
        expires_delta=refresh_token_expires
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }

def generate_random_code(length: int = 8) -> str:
    """Generate a random alphanumeric code"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# OAuth2 utils
async def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Get user info from Google using the provided access token
    
    Args:
        access_token: Google OAuth2 access token
        
    Returns:
        Dictionary with user information
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate Google credentials"
            )
            
        user_info = response.json()
        return {
            "provider": "google",
            "provider_user_id": user_info["sub"],
            "email": user_info["email"],
            "full_name": user_info.get("name"),
            "profile_picture": user_info.get("picture")
        }

async def get_discord_user_info(access_token: str) -> Dict[str, Any]:
    """
    Get user info from Discord using the provided access token
    
    Args:
        access_token: Discord OAuth2 access token
        
    Returns:
        Dictionary with user information
    """
    async with httpx.AsyncClient() as client:
        # Get Discord user data
        user_response = await client.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate Discord credentials"
            )
            
        user_info = user_response.json()
        
        # Get Discord user email
        email_response = await client.get(
            "https://discord.com/api/users/@me/email",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        email = user_info.get("email")
        if email_response.status_code == 200:
            email_data = email_response.json()
            email = email_data.get("email", email)
        
        return {
            "provider": "discord",
            "provider_user_id": user_info["id"],
            "email": email,
            "full_name": user_info.get("username"),
            "profile_picture": f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png" if user_info.get("avatar") else None
        }

def generate_oauth_redirect_uri(provider: str) -> str:
    """
    Generate OAuth redirect URI for the specified provider
    
    Args:
        provider: OAuth provider ('google' or 'discord')
        
    Returns:
        Redirect URI string
    """
    if provider == "google":
        return f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={settings.GOOGLE_CLIENT_ID}&redirect_uri={settings.GOOGLE_REDIRECT_URI}&scope=openid%20email%20profile&prompt=select_account"
    elif provider == "discord":
        return f"https://discord.com/api/oauth2/authorize?client_id={settings.DISCORD_CLIENT_ID}&redirect_uri={settings.DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20email"
    else:
        raise ValueError(f"Invalid OAuth provider: {provider}")

async def exchange_code_for_token(provider: str, code: str) -> Dict[str, Any]:
    """
    Exchange OAuth2 authorization code for access token
    
    Args:
        provider: OAuth provider ('google' or 'discord')
        code: Authorization code
        
    Returns:
        Dictionary with access token and other OAuth2 response data
    """
    async with httpx.AsyncClient() as client:
        if provider == "google":
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI
                }
            )
        elif provider == "discord":
            response = await client.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": settings.DISCORD_CLIENT_ID,
                    "client_secret": settings.DISCORD_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.DISCORD_REDIRECT_URI
                }
            )
        else:
            raise ValueError(f"Invalid OAuth provider: {provider}")
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {response.text}"
            )
            
        return response.json()
