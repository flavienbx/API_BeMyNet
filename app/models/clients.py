from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255))
    email = Column(String(255))
    phone_number = Column(String(20))
    company_name = Column(String(255))
    siret = Column(String(14))
    vat_number = Column(String(20))
    industry = Column(String(100))
    billing_email = Column(String(255))
    client_type = Column(String(50))
    preferred_payment_method = Column(String(50))
    lifetime_value = Column(Numeric(10, 2), default=0)
    last_purchase_date = Column(DateTime)
    created_by_user = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="clients")
    ventes = relationship("Vente", back_populates="client")
    devis_factures = relationship("DevisFacture", back_populates="client")
    avis_donnes = relationship("AvisFreelance", back_populates="client")
