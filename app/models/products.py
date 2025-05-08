from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric
from sqlalchemy.orm import relationship

from app.database import Base

class Produit(Base):
    __tablename__ = "produits"
    
    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(255))
    description = Column(Text)
    prix = Column(Numeric(10, 2))
    type = Column(String(50))
    delivery_time_days = Column(Integer)
    is_customizable = Column(Boolean, default=False)
    category = Column(String(50))
    freelance_only = Column(Boolean, default=True)
    actif = Column(Boolean, default=True)
    
    # Relationships
    ventes = relationship("Vente", back_populates="produit")
