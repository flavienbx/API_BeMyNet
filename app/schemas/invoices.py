from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Union
from datetime import datetime
from decimal import Decimal
from enum import Enum

# Enums for document type and status
class DocumentType(str, Enum):
    DEVIS = "devis"
    FACTURE = "facture"

class DocumentStatus(str, Enum):
    EN_ATTENTE = "en_attente"
    ENVOYE = "envoyé"
    PAYE = "payé"
    ANNULE = "annulé"

class LigneType(str, Enum):
    PRODUIT = "produit"
    SERVICE = "service"
    TEXTE = "texte"
    REMISE = "remise"
    CUSTOM = "custom"


# Schema for invoice/quote line items
class LigneBase(BaseModel):
    ordre: int = 0
    type_ligne: LigneType = LigneType.PRODUIT
    description: str
    quantite: Decimal = Field(1, ge=0)
    prix_unitaire_ht: Decimal = Field(0, ge=0)
    tva: Decimal = Field(20, ge=0)

    # Calculate derived fields
    @property
    def total_ht(self) -> Decimal:
        return self.quantite * self.prix_unitaire_ht
    
    @property
    def total_tva(self) -> Decimal:
        return self.total_ht * (self.tva / 100)
    
    @property
    def total_ttc(self) -> Decimal:
        return self.total_ht + self.total_tva


# Schema for creating a line item
class LigneCreate(LigneBase):
    pass


# Schema for updating a line item
class LigneUpdate(BaseModel):
    ordre: Optional[int] = None
    type_ligne: Optional[LigneType] = None
    description: Optional[str] = None
    quantite: Optional[Decimal] = Field(None, ge=0)
    prix_unitaire_ht: Optional[Decimal] = Field(None, ge=0)
    tva: Optional[Decimal] = Field(None, ge=0)


# Schema for returning a line item
class LigneResponse(LigneBase):
    id: int
    devis_id: int
    total_ht: Decimal
    total_tva: Decimal
    total_ttc: Decimal
    
    class Config:
        orm_mode = True


# Base DevisFacture schema with common attributes
class DevisFactureBase(BaseModel):
    user_id: int
    client_id: int
    type: DocumentType
    status: DocumentStatus = DocumentStatus.EN_ATTENTE
    due_date: Optional[datetime] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


# Schema for creating a new invoice/quote
class DevisFactureCreate(DevisFactureBase):
    lignes: List[LigneCreate] = []


# Schema for updating an invoice/quote
class DevisFactureUpdate(BaseModel):
    status: Optional[DocumentStatus] = None
    due_date: Optional[datetime] = None
    payment_date: Optional[datetime] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


# Schema for returning an invoice/quote
class DevisFactureResponse(DevisFactureBase):
    id: int
    date: datetime
    payment_date: Optional[datetime] = None
    total_ht: Decimal
    total_tva: Decimal
    total_ttc: Decimal
    paid_by_user_id: Optional[int] = None
    pdf_url: Optional[str] = None
    
    class Config:
        orm_mode = True


# Schema for detailed invoice/quote response with line items
class DevisFactureDetailResponse(DevisFactureResponse):
    lignes: List[LigneResponse]
    client: dict
    freelance: dict
    
    class Config:
        orm_mode = True


# Schema for paginated invoice/quote list
class DevisFactureListResponse(BaseModel):
    documents: List[DevisFactureResponse]
    total: int
    page: int
    size: int
    
    class Config:
        orm_mode = True


# Schema for generating a PDF
class PDFGenerateRequest(BaseModel):
    document_id: int
    include_logo: bool = True
    include_signature: bool = False
    custom_note: Optional[str] = None
