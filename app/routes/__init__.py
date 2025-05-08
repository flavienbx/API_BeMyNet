# Ce fichier rend le dossier routes un module Python
# Import des différents blueprints pour les exposer à l'application principale

from app.routes.oauth_routes import oauth_bp
from app.routes.auth_routes import auth_bp
from app.routes.stripe_routes import stripe_bp
from app.routes.invoice_routes import invoice_bp
from app.routes.product_routes import product_bp
from app.routes.sales_routes import sales_bp
from app.routes.review_routes import review_bp
from app.routes.affiliation_routes import affiliation_bp
from app.routes.partner_routes import partner_bp
from app.routes.public_routes import public_bp

# Liste des blueprints disponibles
__all__ = ['oauth_bp', 'auth_bp', 'stripe_bp', 'invoice_bp', 'product_bp', 'sales_bp', 
          'review_bp', 'affiliation_bp', 'partner_bp', 'public_bp']