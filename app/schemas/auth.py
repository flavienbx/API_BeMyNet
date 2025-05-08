from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

# Token schema for JWT authentication
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# Token data schema for decoded JWT payload
class TokenData(BaseModel):
    user_id: int


# Schema for login with email and password
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Schema for refresh token
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Schema for social login redirect
class SocialAuthRedirectResponse(BaseModel):
    auth_url: str


# Schema for social auth callback
class SocialAuthCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


# Schema for user profile from social auth
class SocialUserProfile(BaseModel):
    provider: str
    provider_user_id: str
    email: EmailStr
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None


# Schema for password change
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


# Schema for password reset request
class PasswordResetRequest(BaseModel):
    email: EmailStr


# Schema for password reset confirmation
class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v
