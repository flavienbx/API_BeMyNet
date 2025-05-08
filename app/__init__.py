import os
import logging
from flask import Flask
from sqlalchemy import create_engine
from flasgger import Swagger

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """
    Fonction de création de l'application Flask
    """
    # Création de l'application Flask
    app = Flask(__name__)

    # Configuration de la base de données MySQL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        try:
            # Configuration spécifique à MySQL
            engine = create_engine(
                database_url,
                connect_args={
                    'charset': 'utf8mb4',  # Support complet des caractères Unicode
                    'connect_timeout': 30,  # Timeout de connexion
                },
                pool_recycle=3600,  # Recycler les connexions après 1 heure
                pool_pre_ping=True   # Vérifier la connexion avant utilisation
            )
            app.config['db_engine'] = engine
            logger.info("MySQL database engine initialized")
        except Exception as e:
            logger.error(f"Error initializing MySQL database engine: {str(e)}")
    else:
        logger.warning("DATABASE_URL not provided, database features will be disabled")

    # Configuration de Stripe
    stripe_secret_key = os.environ.get('STRIPE_SECRET_KEY')
    if stripe_secret_key:
        import stripe
        stripe.api_key = stripe_secret_key
        app.config['stripe_configured'] = True
        logger.info("Stripe configured")
    else:
        app.config['stripe_configured'] = False
        logger.warning("STRIPE_SECRET_KEY not provided, Stripe features will be disabled")

    # Configuration du secret JWT
    jwt_secret = os.environ.get('JWT_SECRET_KEY')
    if not jwt_secret:
        import secrets
        jwt_secret = secrets.token_hex(32)
        logger.warning("JWT_SECRET_KEY not provided, using temporary key (will change on restart)")
    app.config['JWT_SECRET_KEY'] = jwt_secret
    
    # Configuration de Swagger pour la documentation API
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,  # all in
                "model_filter": lambda tag: True,  # all in
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs"
    }
    
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "BeMyNet API",
            "description": "API pour la plateforme BeMyNet - Gestion de freelances, clients, ventes et facturation",
            "version": "1.0",
            "contact": {
                "email": "contact@bemynet.fr"
            },
        },
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT Token d'authentification. Format: Bearer {token}"
            }
        },
        "security": [
            {
                "Bearer": []
            }
        ],
        "tags": [
            {"name": "Authentification", "description": "Routes d'authentification et gestion des utilisateurs"},
            {"name": "Stripe", "description": "Gestion des paiements via Stripe Connect"},
            {"name": "Factures", "description": "Gestion des devis et factures"},
            {"name": "Produits", "description": "Gestion des produits et services"},
            {"name": "Ventes", "description": "Gestion des ventes et commissions"},
            {"name": "Avis", "description": "Système d'avis clients"},
            {"name": "Affiliations", "description": "Gestion des affiliations et tracking"},
            {"name": "Partenaires", "description": "Gestion des commerciaux et partenaires"},
            {"name": "Public", "description": "Routes publiques accessibles sans authentification"}
        ]
    }
    
    # Initialisation de Swagger avec la configuration
    Swagger(app, config=swagger_config, template=swagger_template)

    # Enregistrement des blueprints
    from app.routes import oauth_bp, auth_bp, stripe_bp, invoice_bp, product_bp, sales_bp
    from app.routes import review_bp, affiliation_bp, partner_bp, public_bp
    app.register_blueprint(oauth_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(stripe_bp)
    app.register_blueprint(invoice_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(affiliation_bp)
    app.register_blueprint(partner_bp)
    app.register_blueprint(public_bp)

    # Route de base pour vérifier que l'application fonctionne
    @app.route('/')
    def index():
        return {
            "message": "BeMyNet API is running",
            "status": "OK",
            "version": "1.0.0",
            "documentation": "/docs",
            "auth_endpoints": {
                "signup": "/auth/signup",
                "login": "/auth/login",
                "refresh": "/auth/refresh",
                "me": "/auth/me",
                "logout": "/auth/logout",
                "google_login": "/auth/google/login",
                "discord_login": "/auth/discord/login"
            },
            "stripe_endpoints": {
                "create_checkout_session": "/stripe/create-checkout-session",
                "create_connect_account": "/stripe/create-connect-account",
                "dashboard_url": "/stripe/dashboard-url",
                "account_status": "/stripe/account-status",
                "webhook": "/stripe/webhook"
            },
            "invoice_endpoints": {
                "list": "/devis",
                "create": "/devis",
                "details": "/devis/{id}",
                "pdf": "/devis/{id}/pdf",
                "update_status": "/devis/{id}/status",
                "pay": "/devis/{id}/payer"
            },
            "product_endpoints": {
                "list": "/produits",
                "create": "/produits",
                "details": "/produits/{id}",
                "update": "/produits/{id}",
                "pay": "/produits/{id}/payer"
            },
            "sales_endpoints": {
                "list": "/ventes",
                "create": "/ventes",
                "details": "/ventes/{id}",
                "commissions": "Calcul automatique des commissions"
            },
            "payment_splitting": {
                "plateforme_seule": "15% plateforme, 85% freelance",
                "avec_commercial": "10% plateforme, 5% commercial, 85% freelance",
                "avec_partenaire": "13% plateforme, 2% partenaire, 85% freelance",
                "complet": "8% plateforme, 5% commercial, 2% partenaire, 85% freelance",
                "personnalisable": "Taux configurables par commercial/partenaire"
            },
            "review_endpoints": {
                "freelance_reviews": "/avis/freelance",
                "platform_reviews": "/avis/plateforme",
                "moderate": "/avis/{id}/moderate"
            },
            "affiliation_endpoints": {
                "list": "/affiliations",
                "tracking_code": "/affiliations/tracking-code",
                "track": "/affiliations/track/{type}/{code}"
            },
            "partner_endpoints": {
                "commerciaux": "/commerciaux",
                "commercial_details": "/commerciaux/{id}",
                "partenaires": "/partenaires",
                "partenaire_details": "/partenaires/{id}"
            },
            "public_endpoints": {
                "freelances": "/public/freelances",
                "freelance_profile": "/public/freelances/{id}",
                "portfolio": "/public/portfolio/{id}",
                "produits": "/public/produits",
                "produit_details": "/public/produits/{id}",
                "platform_reviews": "/public/avis-plateforme"
            }
        }

    return app