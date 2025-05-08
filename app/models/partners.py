from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from sqlalchemy.orm import relationship

from app.database import Base

class Commercial(Base):
    __tablename__ = "commerciaux"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255))
    email = Column(String(255))
    pourcentage = Column(Numeric(5, 2))
    status = Column(String(50))
    tracking_code = Column(String(20))
    contract_signed_at = Column(DateTime)
    
    # Relationships
    ventes = relationship("Vente", back_populates="commercial")

class Partenaire(Base):
    __tablename__ = "partenaires"
    
    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(255))
    type = Column(String(50))
    email_contact = Column(String(255))
    pourcentage = Column(Numeric(5, 2))
    tracking_url = Column(Text)
    status = Column(String(50))
    contract_signed_at = Column(DateTime)
    
    # Relationships
    ventes = relationship("Vente", back_populates="partenaire")
    users = relationship("User", foreign_keys="User.partner_id")
