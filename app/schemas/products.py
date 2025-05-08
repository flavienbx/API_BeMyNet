from pydantic import BaseModel, Field, validator
from typing import Optional, List
from decimal import Decimal

# Base Product schema with common attributes
class ProduitBase(BaseModel):
    nom: str
    description: str
    prix: Decimal = Field(..., ge=0)
    type: str
    delivery_time_days: int = Field(..., ge=1)
    is_customizable: bool = False
    category: str
    freelance_only: bool = True
    actif: bool = True


# Schema for creating a new product
class ProduitCreate(ProduitBase):
    pass


# Schema for updating a product
class ProduitUpdate(BaseModel):
    nom: Optional[str] = None
    description: Optional[str] = None
    prix: Optional[Decimal] = Field(None, ge=0)
    type: Optional[str] = None
    delivery_time_days: Optional[int] = Field(None, ge=1)
    is_customizable: Optional[bool] = None
    category: Optional[str] = None
    freelance_only: Optional[bool] = None
    actif: Optional[bool] = None


# Schema for returning a product
class ProduitResponse(ProduitBase):
    id: int
    
    class Config:
        orm_mode = True


# Schema for product list
class ProduitListResponse(BaseModel):
    produits: List[ProduitResponse]
    total: int
    page: int
    size: int
    
    class Config:
        orm_mode = True


# Schema for product with sales stats
class ProduitWithStatsResponse(ProduitResponse):
    total_sales: int
    total_revenue: Decimal
    average_rating: Optional[Decimal] = None
    
    class Config:
        orm_mode = True
