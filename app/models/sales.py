from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class Vente(Base):
    __tablename__ = "ventes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    produit_id = Column(Integer, ForeignKey("produits.id", ondelete="SET NULL"), nullable=True)
    montant = Column(Numeric(10, 2))
    discount_applied = Column(Numeric(10, 2), default=0)
    description = Column(Text)
    date = Column(DateTime, server_default=func.now())
    source = Column(String(50))
    commission_plateforme = Column(Numeric(10, 2), default=0)
    commission_commerciale = Column(Numeric(10, 2), default=0)
    commission_partenaire = Column(Numeric(10, 2), default=0)
    montant_net_freelance = Column(Numeric(10, 2), default=0)
    commercial_id = Column(Integer, ForeignKey("commerciaux.id", ondelete="SET NULL"), nullable=True)
    partenaire_id = Column(Integer, ForeignKey("partenaires.id", ondelete="SET NULL"), nullable=True)
    stripe_payment_id = Column(String(255))
    statut_paiement = Column(Enum("payé", "en_attente", "remboursé", name="statut_paiement_enum"), default="en_attente")
    feedback = Column(Text)
    invoice_id = Column(Integer, ForeignKey("devis_factures.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    freelance = relationship("User", back_populates="ventes")
    client = relationship("Client", back_populates="ventes")
    produit = relationship("Produit", back_populates="ventes")
    commercial = relationship("Commercial", back_populates="ventes")
    partenaire = relationship("Partenaire", back_populates="ventes")
    affiliations = relationship("Affiliation", back_populates="vente")
    avis = relationship("AvisFreelance", back_populates="vente")


class Affiliation(Base):
    __tablename__ = "affiliations"
    
    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(Enum("commercial", "partenaire", "lien", name="source_type_enum"))
    source_id = Column(Integer)
    vente_id = Column(Integer, ForeignKey("ventes.id", ondelete="CASCADE"))
    commission = Column(Numeric(10, 2), default=0)
    
    # Relationships
    vente = relationship("Vente", back_populates="affiliations")
