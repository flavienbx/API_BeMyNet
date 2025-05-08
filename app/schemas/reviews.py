from pydantic import BaseModel, Field, validator
from typing import Optional, List, Union
from datetime import datetime

# Base Review schema with common attributes
class AvisFreelanceBase(BaseModel):
    user_id: int
    client_id: int
    vente_id: int
    note: int = Field(..., ge=1, le=5)
    commentaire: Optional[str] = None
    visible: bool = True


# Schema for creating a new freelancer review
class AvisFreelanceCreate(AvisFreelanceBase):
    pass


# Schema for updating a freelancer review
class AvisFreelanceUpdate(BaseModel):
    note: Optional[int] = Field(None, ge=1, le=5)
    commentaire: Optional[str] = None
    visible: Optional[bool] = None


# Schema for returning a freelancer review
class AvisFreelanceResponse(AvisFreelanceBase):
    id: int
    date: datetime
    
    class Config:
        from_attributes = True


# Schema for returning a detailed freelancer review with related entities
class AvisFreelanceDetailResponse(AvisFreelanceResponse):
    freelance: dict
    client: dict
    vente: dict


# Base Platform Review schema
class AvisPlatformeBase(BaseModel):
    auteur_id: int
    auteur_role: str
    note: int = Field(..., ge=1, le=5)
    commentaire: Optional[str] = None
    visible: bool = True
    version_plateforme: Optional[str] = None
    experience_type: Optional[str] = None


# Schema for creating a new platform review
class AvisPlatformeCreate(AvisPlatformeBase):
    pass


# Schema for updating a platform review
class AvisPlatformeUpdate(BaseModel):
    note: Optional[int] = Field(None, ge=1, le=5)
    commentaire: Optional[str] = None
    visible: Optional[bool] = None
    version_plateforme: Optional[str] = None
    experience_type: Optional[str] = None


# Schema for returning a platform review
class AvisPlatformeResponse(AvisPlatformeBase):
    id: int
    date: datetime
    
    class Config:
        from_attributes = True


# Schema for paginated review list
class AvisListResponse(BaseModel):
    avis: List[Union[AvisFreelanceResponse, AvisPlatformeResponse]]
    total: int
    page: int
    size: int
    average_rating: Optional[float] = None
    
    class Config:
        from_attributes = True
