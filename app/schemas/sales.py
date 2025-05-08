from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# Enum for payment status
from enum import Enum

class StatutPaiement(str, Enum):
    PAYE = "payé"
    EN_ATTENTE = "en_attente"
    REMBOURSE = "remboursé"


# Base Sale schema with common attributes
class VenteBase(BaseModel):
    user_id: int
    client_id: int
    produit_id: int
    montant: Decimal = Field(..., ge=0)
    discount_applied: Optional[Decimal] = Field(0, ge=0)
    description: Optional[str] = None
    source: Optional[str] = None


# Schema for creating a new sale
class VenteCreate(VenteBase):
    commercial_id: Optional[int] = None
    partenaire_id: Optional[int] = None


# Schema for updating a sale
class VenteUpdate(BaseModel):
    statut_paiement: Optional[StatutPaiement] = None
    feedback: Optional[str] = None
    stripe_payment_id: Optional[str] = None
    invoice_id: Optional[int] = None


# Schema for calculating commissions
class VenteCalculateCommission(BaseModel):
    montant: Decimal = Field(..., ge=0)
    discount_applied: Optional[Decimal] = Field(0, ge=0)
    user_id: int
    commercial_id: Optional[int] = None
    partenaire_id: Optional[int] = None


# Schema for commission calculation response
class CommissionResponse(BaseModel):
    montant_brut: Decimal
    discount_applied: Decimal
    montant_apres_remise: Decimal
    commission_plateforme: Decimal
    commission_commerciale: Decimal
    commission_partenaire: Decimal
    montant_net_freelance: Decimal
    details: dict


# Schema for returning a sale
class VenteResponse(VenteBase):
    id: int
    date: datetime
    commission_plateforme: Decimal
    commission_commerciale: Decimal
    commission_partenaire: Decimal
    montant_net_freelance: Decimal
    commercial_id: Optional[int] = None
    partenaire_id: Optional[int] = None
    stripe_payment_id: Optional[str] = None
    statut_paiement: StatutPaiement
    feedback: Optional[str] = None
    invoice_id: Optional[int] = None
    
    class Config:
        orm_mode = True


# Schema for a detailed sale response with related entities
class VenteDetailResponse(VenteResponse):
    client: dict
    produit: dict
    freelance: dict
    commercial: Optional[dict] = None
    partenaire: Optional[dict] = None
    
    class Config:
        orm_mode = True


# Schema for affiliation
class AffiliationBase(BaseModel):
    source_type: str
    source_id: int
    vente_id: int
    commission: Decimal = Field(..., ge=0)


# Schema for creating a new affiliation
class AffiliationCreate(AffiliationBase):
    pass


# Schema for returning an affiliation
class AffiliationResponse(AffiliationBase):
    id: int
    
    class Config:
        orm_mode = True


# Schema for paginaged sales list
class VenteListResponse(BaseModel):
    ventes: List[VenteResponse]
    total: int
    page: int
    size: int
    
    class Config:
        orm_mode = True
