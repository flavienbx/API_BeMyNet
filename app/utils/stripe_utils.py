import os
import logging
import stripe
from datetime import datetime

# Configuration du logging
logger = logging.getLogger(__name__)

# Configuration Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_CONNECT_CLIENT_ID = os.environ.get("STRIPE_CONNECT_CLIENT_ID")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://panel.bemynet.fr")

# Base URL pour les redirections
BASE_URL = os.environ.get("BASE_URL", "")
if not BASE_URL:
    # Détecter l'URL de base à partir de l'environnement Replit
    replit_domain = os.environ.get("REPLIT_DOMAINS")
    if replit_domain:
        domains = replit_domain.split(",")
        if domains:
            BASE_URL = f"https://{domains[0]}"

def create_checkout_session(
    client_id, 
    product_id, 
    freelance_id, 
    montant, 
    description, 
    freelance_stripe_id=None,
    metadata=None
):
    """
    Crée une session de paiement Stripe avec partage de paiement si possible
    
    Args:
        client_id: ID du client
        product_id: ID du produit
        freelance_id: ID du freelance
        montant: Montant en centimes
        description: Description de l'achat
        freelance_stripe_id: ID Stripe du freelance pour le partage (optionnel)
        metadata: Métadonnées additionnelles pour la session (optionnel)
        
    Returns:
        Session Stripe créée
    """
    try:
        success_url = f"{BASE_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{BASE_URL}/payment/cancel?session_id={{CHECKOUT_SESSION_ID}}"
        
        # Métadonnées de base
        session_metadata = {
            "client_id": str(client_id),
            "product_id": str(product_id),
            "freelance_id": str(freelance_id),
            "date": datetime.utcnow().isoformat()
        }
        
        # Ajouter les métadonnées supplémentaires si fournies
        if metadata:
            session_metadata.update(metadata)
        
        session_params = {
            "payment_method_types": ["card"],
            "line_items": [{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": description,
                    },
                    "unit_amount": int(montant * 100),  # Conversion euros -> centimes
                },
                "quantity": 1,
            }],
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": session_metadata,
        }
        
        # Si le freelance a un compte Stripe Connect, configurer le partage de paiement
        if freelance_stripe_id:
            # Calcul de la commission plateforme (15% par défaut)
            application_fee_amount = int(montant * 100 * 0.15)  # 15% en centimes
            
            # Configurer le transfert vers le compte du freelance
            session_params["payment_intent_data"] = {
                "transfer_data": {
                    "destination": freelance_stripe_id,
                },
                "application_fee_amount": application_fee_amount,
            }
        
        # Créer la session de paiement
        checkout_session = stripe.checkout.Session.create(**session_params)
        
        return checkout_session
    except Exception as e:
        logger.error(f"Error creating Stripe checkout session: {str(e)}")
        raise

def create_connect_account(email, country="FR", refresh_url=None, return_url=None):
    """
    Crée un compte Express Stripe Connect pour un freelance
    
    Args:
        email: Email du freelance
        country: Code pays (par défaut: France)
        refresh_url: URL de rafraichissement (optionnel)
        return_url: URL de retour (optionnel)
        
    Returns:
        dict: Contenant account_id et account_link
    """
    try:
        if not refresh_url:
            refresh_url = f"{FRONTEND_URL}/dashboard/stripe/refresh"
        
        if not return_url:
            return_url = f"{FRONTEND_URL}/dashboard/stripe/success"
        
        # Créer le compte Express
        account = stripe.Account.create(
            type="express",
            country=country,
            email=email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_type="individual",
        )
        
        # Créer un lien d'activation pour le compte
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        
        return {
            "account_id": account.id,
            "account_link": account_link.url
        }
    except Exception as e:
        logger.error(f"Error creating Stripe Connect account: {str(e)}")
        raise

def get_account_dashboard_link(account_id):
    """
    Génère un lien vers le tableau de bord Express d'un compte Connect
    
    Args:
        account_id: ID du compte Stripe Connect
        
    Returns:
        str: URL du tableau de bord Express
    """
    try:
        login_link = stripe.Account.create_login_link(account_id)
        return login_link.url
    except Exception as e:
        logger.error(f"Error generating Stripe dashboard link: {str(e)}")
        raise

def check_account_status(account_id):
    """
    Vérifie le statut d'un compte Stripe Connect (vérifications, payouts actifs, etc.)
    
    Args:
        account_id: ID du compte Stripe Connect
        
    Returns:
        dict: Statut du compte
    """
    try:
        account = stripe.Account.retrieve(account_id)
        
        return {
            "id": account.id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "requirements": account.requirements,
            "details_submitted": account.details_submitted
        }
    except Exception as e:
        logger.error(f"Error checking Stripe account status: {str(e)}")
        raise

def handle_checkout_session_completed(event_data):
    """
    Traite l'événement checkout.session.completed de Stripe
    
    Args:
        event_data: Données de l'événement Stripe
        
    Returns:
        dict: Informations sur la vente créée
    """
    try:
        session = event_data.object
        
        # Récupérer les métadonnées
        client_id = session.metadata.get("client_id")
        product_id = session.metadata.get("product_id")
        freelance_id = session.metadata.get("freelance_id")
        
        # Montant total payé
        amount_total = session.amount_total / 100  # Convertir centimes en euros
        
        # Récupérer le payment_intent pour les détails du transfert
        payment_intent_id = session.payment_intent
        payment_intent = None
        transfer_id = None
        application_fee_amount = 0
        
        if payment_intent_id:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            # Si un transfert a été effectué, récupérer les détails
            if hasattr(payment_intent, 'transfer') and payment_intent.transfer:
                transfer_id = payment_intent.transfer
                
            # Récupérer la commission plateforme
            if hasattr(payment_intent, 'application_fee_amount') and payment_intent.application_fee_amount:
                application_fee_amount = payment_intent.application_fee_amount / 100  # Centimes en euros
        
        # Retourner les informations pour la création de la vente
        return {
            "client_id": int(client_id) if client_id else None,
            "product_id": int(product_id) if product_id else None,
            "freelance_id": int(freelance_id) if freelance_id else None,
            "montant": amount_total,
            "commission_plateforme": application_fee_amount,
            "stripe_payment_id": session.id,
            "stripe_transfer_id": transfer_id,
            "statut_paiement": "payé",
            "payment_intent_id": payment_intent_id,
        }
    except Exception as e:
        logger.error(f"Error handling checkout.session.completed: {str(e)}")
        raise