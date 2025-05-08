from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# Base Client schema with common attributes
class ClientBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    siret: Optional[str] = None
    vat_number: Optional[str] = None
    industry: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    client_type: Optional[str] = None
    preferred_payment_method: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


# Schema for creating a new client
class ClientCreate(ClientBase):
    pass


# Schema for updating a client
class ClientUpdate(ClientBase):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


# Schema for returning a client
class ClientResponse(ClientBase):
    id: int
    created_by_user: Optional[int] = None
    lifetime_value: Optional[Decimal] = None
    last_purchase_date: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        orm_mode = True


# Schema for client summary with sales information
class ClientWithSalesResponse(ClientResponse):
    total_sales: int
    total_amount: Decimal
    sales: List[dict]
    
    class Config:
        orm_mode = True
