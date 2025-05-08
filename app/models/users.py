from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, Numeric, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255))
    email = Column(String(255), unique=True, index=True)
    password_hash = Column(Text)
    phone_number = Column(String(20))
    bio = Column(Text)
    role = Column(String(50))
    stripe_account_id = Column(String(255))
    stripe_dashboard_url = Column(Text)
    payout_enabled = Column(Boolean, default=False)
    partner_id = Column(Integer, ForeignKey("partenaires.id", ondelete="SET NULL"), nullable=True)
    affiliation_code = Column(String(20))
    siret = Column(String(14))
    vat_number = Column(String(20))
    company_name = Column(String(255))
    birthdate = Column(Date)
    country = Column(String(100))
    city = Column(String(100))
    zip_code = Column(String(10))
    language = Column(String(10))
    website = Column(Text)
    portfolio_url = Column(Text)
    id_card_verified = Column(Boolean, default=False)
    kyc_status = Column(String(50))
    last_login_at = Column(DateTime)
    account_status = Column(String(50), default="pending")
    total_revenue = Column(Numeric(10, 2), default=0)
    rating = Column(Numeric(3, 2))
    created_at = Column(DateTime, server_default=func.now())
    experience_type = Column(String(100))
    
    # Relationships
    clients = relationship("Client", back_populates="creator")
    authentifications = relationship("Authentification", back_populates="user")
    ventes = relationship("Vente", back_populates="freelance")
    devis_factures = relationship("DevisFacture", back_populates="freelance")
    avis_recus = relationship("AvisFreelance", back_populates="freelance")
