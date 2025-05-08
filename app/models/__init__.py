# Import all models to ensure they're registered with SQLAlchemy
from app.models.users import User
from app.models.clients import Client
from app.models.products import Produit
from app.models.sales import Vente, Affiliation
from app.models.invoices import DevisFacture, DevisFactureLigne
from app.models.partners import Commercial, Partenaire
from app.models.reviews import AvisFreelance, AvisPlateforme
from app.models.auth import Authentification
