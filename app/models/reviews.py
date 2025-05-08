from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class AvisFreelance(Base):
    __tablename__ = "avis_freelance"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    vente_id = Column(Integer, ForeignKey("ventes.id", ondelete="CASCADE"))
    note = Column(Integer)
    commentaire = Column(Text)
    date = Column(DateTime, server_default=func.now())
    visible = Column(Boolean, default=True)
    
    # Relationships
    freelance = relationship("User", back_populates="avis_recus")
    client = relationship("Client", back_populates="avis_donnes")
    vente = relationship("Vente", back_populates="avis")

class AvisPlateforme(Base):
    __tablename__ = "avis_plateforme"
    
    id = Column(Integer, primary_key=True, index=True)
    auteur_id = Column(Integer)
    auteur_role = Column(String(20))
    note = Column(Integer)
    commentaire = Column(Text)
    date = Column(DateTime, server_default=func.now())
    visible = Column(Boolean, default=True)
    version_plateforme = Column(String(20))
    experience_type = Column(String(100))
