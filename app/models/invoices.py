from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, ForeignKey, Enum, func
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class DevisFacture(Base):
    __tablename__ = "devis_factures"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    type = Column(Enum("devis", "facture", name="type_document_enum"))
    status = Column(Enum("en_attente", "envoyé", "payé", "annulé", name="status_document_enum"), default="en_attente")
    date = Column(DateTime, server_default=func.now())
    due_date = Column(DateTime)
    payment_date = Column(DateTime, nullable=True)
    payment_method = Column(String(50))
    total_ht = Column(Numeric(10, 2), default=0)
    total_tva = Column(Numeric(10, 2), default=0)
    total_ttc = Column(Numeric(10, 2), default=0)
    paid_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    pdf_url = Column(Text)
    notes = Column(Text)
    
    # Relationships
    freelance = relationship("User", foreign_keys=[user_id], back_populates="devis_factures")
    client = relationship("Client", back_populates="devis_factures")
    lignes = relationship("DevisFactureLigne", back_populates="devis", cascade="all, delete-orphan")


class DevisFactureLigne(Base):
    __tablename__ = "devis_factures_lignes"
    
    id = Column(Integer, primary_key=True, index=True)
    devis_id = Column(Integer, ForeignKey("devis_factures.id", ondelete="CASCADE"))
    ordre = Column(Integer, default=0)
    type_ligne = Column(Enum("produit", "service", "texte", "remise", "custom", 
                          name="type_ligne_enum"), default="produit")
    description = Column(Text, nullable=False)
    quantite = Column(Numeric(10, 2), default=1)
    prix_unitaire_ht = Column(Numeric(10, 2), default=0)
    tva = Column(Numeric(5, 2), default=20)
    
    # In SQLAlchemy we need to calculate these values in Python since the GENERATED ALWAYS doesn't work directly
    # We'll handle this in the Pydantic schemas
    
    # Relationships
    devis = relationship("DevisFacture", back_populates="lignes")
