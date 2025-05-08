from pydantic import BaseModel, EmailStr, Field, validator, HttpUrl
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

# Base User schema with common attributes
class UserBase(BaseModel):
    full_name: Optional[str] = None
    email: EmailStr
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    role: Optional[str] = None
    
    # Company info
    company_name: Optional[str] = None
    siret: Optional[str] = None
    vat_number: Optional[str] = None
    
    # Location
    country: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    language: Optional[str] = None
    
    # Online presence
    website: Optional[str] = None
    portfolio_url: Optional[str] = None
    
    # Experience
    experience_type: Optional[str] = None


# Schema for creating a new user
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    confirm_password: str
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v


# Schema for updating a user
class UserUpdate(UserBase):
    password: Optional[str] = Field(None, min_length=8)
    birthdate: Optional[date] = None


# Schema for returning a user
class UserResponse(UserBase):
    id: int
    stripe_account_id: Optional[str] = None
    payout_enabled: Optional[bool] = None
    affiliation_code: Optional[str] = None
    id_card_verified: Optional[bool] = None
    kyc_status: Optional[str] = None
    account_status: Optional[str] = None
    total_revenue: Optional[Decimal] = None
    rating: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True


# Schema for returning a freelancer profile (public view)
class FreelanceProfileResponse(BaseModel):
    id: int
    full_name: str
    bio: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    portfolio_url: Optional[str] = None
    rating: Optional[Decimal] = None
    experience_type: Optional[str] = None
    
    class Config:
        orm_mode = True


# Schema for freelancer dashboard summary
class FreelanceDashboardResponse(BaseModel):
    total_revenue: Decimal
    pending_payouts: Decimal
    completed_sales: int
    active_sales: int
    average_rating: Optional[Decimal] = None
    recent_activity: List[dict]
    
    class Config:
        orm_mode = True
