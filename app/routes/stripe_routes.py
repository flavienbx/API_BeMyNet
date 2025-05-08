import os
import logging
import stripe
from flask import Blueprint, request, jsonify, redirect, url_for, current_app
from sqlalchemy import text
from functools import wraps

from app.utils.stripe_utils import (
    create_checkout_session,
    create_connect_account,
    get_account_dashboard_link,
    check_account_status,
    handle_checkout_session_completed
)

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes Stripe
stripe_bp = Blueprint('stripe', __name__, url_prefix='/stripe')

# Clé webhook Stripe
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Middleware d'authentification
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        # Importer decode_token depuis jwt_utils
        from app.utils.jwt_utils import decode_token
        
        try:
            payload = decode_token(token)
            if not payload:
                return jsonify({'message': 'Token is invalid!'}), 401
            
            # Add user_id to request for route handlers
            request.user_id = int(payload['sub'])
            
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return jsonify({'message': 'Token is invalid!'}), 401
        
    return decorated

# Endpoint pour créer une session de paiement Stripe Checkout
@stripe_bp.route('/create-checkout-session', methods=['POST'])
@token_required
def stripe_checkout():
    """
    Crée une session de paiement Stripe Checkout
    ---
    tags:
      - Stripe
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - client_id
            - product_id
            - montant
            - description
          properties:
            client_id:
              type: integer
              description: ID du client
            product_id:
              type: integer
              description: ID du produit
            montant:
              type: number
              format: float
              description: Montant du paiement en euros
            description:
              type: string
              description: Description de la prestation
    responses:
      200:
        description: Session de paiement créée avec succès
        schema:
          type: object
          properties:
            session_id:
              type: string
              description: ID de la session Stripe
            checkout_url:
              type: string
              description: URL de redirection vers Stripe Checkout
      400:
        description: Données invalides
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    data = request.json
    user_id = request.user_id
    
    # Valider les données requises
    required_fields = ['client_id', 'product_id', 'montant', 'description']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    client_id = data['client_id']
    product_id = data['product_id']
    montant = float(data['montant'])
    description = data['description']
    
    # Vérifier le compte Stripe du freelance pour savoir si on doit faire un split
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            user_query = text("""
                SELECT id, email, full_name, stripe_account_id, payout_enabled
                FROM users
                WHERE id = :user_id
            """)
            
            user = conn.execute(user_query, {"user_id": user_id}).fetchone()
            
            if not user:
                return jsonify({'message': 'Utilisateur non trouvé'}), 404
            
            freelance_stripe_id = None
            
            # Si l'utilisateur a un compte Stripe Connect et que les paiements sont activés
            if user.stripe_account_id and user.payout_enabled:
                freelance_stripe_id = user.stripe_account_id
            
            # Créer la session de paiement
            checkout_session = create_checkout_session(
                client_id=client_id,
                product_id=product_id,
                freelance_id=user_id,
                montant=montant,
                description=description,
                freelance_stripe_id=freelance_stripe_id,
                metadata={
                    "user_email": user.email,
                    "user_name": user.full_name
                }
            )
            
            # Retourner l'ID de la session et l'URL
            return jsonify({
                'session_id': checkout_session.id,
                'checkout_url': checkout_session.url
            })
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        return jsonify({'message': f'Erreur lors de la création de la session: {str(e)}'}), 500

# Endpoint pour créer un compte Stripe Connect
@stripe_bp.route('/create-connect-account', methods=['POST'])
@token_required
def create_stripe_connect():
    """
    Crée un compte Stripe Connect Express pour le freelance
    ---
    tags:
      - Stripe
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            country:
              type: string
              description: Code pays à 2 lettres (ISO 3166-1)
              default: FR
            refresh_url:
              type: string
              description: URL de rafraîchissement personnalisée
            return_url:
              type: string
              description: URL de retour personnalisée
    responses:
      200:
        description: Compte existant ou nouveau compte créé
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de statut
            account_id:
              type: string
              description: ID du compte Stripe Connect
            account_link:
              type: string
              description: URL d'activation du compte (nouveau compte uniquement)
            dashboard_url:
              type: string
              description: URL du dashboard (compte existant uniquement)
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            user_query = text("""
                SELECT id, email, full_name, stripe_account_id
                FROM users
                WHERE id = :user_id
            """)
            
            user = conn.execute(user_query, {"user_id": user_id}).fetchone()
            
            if not user:
                return jsonify({'message': 'Utilisateur non trouvé'}), 404
            
            # Vérifier si l'utilisateur a déjà un compte Stripe
            if user.stripe_account_id:
                # Obtenir un lien vers le dashboard Express
                dashboard_url = get_account_dashboard_link(user.stripe_account_id)
                
                return jsonify({
                    'message': 'Compte Stripe Connect déjà créé',
                    'account_id': user.stripe_account_id,
                    'dashboard_url': dashboard_url
                })
            
            # Créer un nouveau compte Stripe Connect
            data = request.json or {}
            country = data.get('country', 'FR')
            
            # URLs de callback personnalisées si fournies
            refresh_url = data.get('refresh_url')
            return_url = data.get('return_url')
            
            # Créer le compte
            account_data = create_connect_account(
                email=user.email,
                country=country,
                refresh_url=refresh_url,
                return_url=return_url
            )
            
            # Mettre à jour l'utilisateur avec son ID de compte Stripe
            update_query = text("""
                UPDATE users
                SET stripe_account_id = :stripe_id, 
                    stripe_activated = NOW()
                WHERE id = :user_id
            """)
            
            conn.execute(update_query, {
                "stripe_id": account_data['account_id'],
                "user_id": user_id
            })
            
            # Commit les changements
            conn.commit()
            
            # Retourner le lien d'activation
            return jsonify({
                'message': 'Compte Stripe Connect créé avec succès',
                'account_id': account_data['account_id'],
                'account_link': account_data['account_link']
            })
    except Exception as e:
        logger.error(f"Error creating Stripe Connect account: {str(e)}")
        return jsonify({'message': f'Erreur lors de la création du compte: {str(e)}'}), 500

# Endpoint pour obtenir l'URL du dashboard Stripe
@stripe_bp.route('/dashboard-url', methods=['GET'])
@token_required
def get_dashboard_url():
    """
    Récupère l'URL du dashboard Stripe Express pour le freelance
    ---
    tags:
      - Stripe
    security:
      - Bearer: []
    responses:
      200:
        description: URL du dashboard Stripe récupérée avec succès
        schema:
          type: object
          properties:
            dashboard_url:
              type: string
              description: URL du dashboard Stripe Express
      400:
        description: Aucun compte Stripe Connect associé
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            user_query = text("""
                SELECT id, stripe_account_id
                FROM users
                WHERE id = :user_id
            """)
            
            user = conn.execute(user_query, {"user_id": user_id}).fetchone()
            
            if not user:
                return jsonify({'message': 'Utilisateur non trouvé'}), 404
            
            if not user.stripe_account_id:
                return jsonify({'message': 'Aucun compte Stripe Connect associé'}), 400
            
            # Obtenir l'URL du dashboard
            dashboard_url = get_account_dashboard_link(user.stripe_account_id)
            
            return jsonify({
                'dashboard_url': dashboard_url
            })
    except Exception as e:
        logger.error(f"Error getting Stripe dashboard URL: {str(e)}")
        return jsonify({'message': f'Erreur lors de la récupération de l\'URL: {str(e)}'}), 500

# Endpoint pour vérifier le statut du compte Stripe
@stripe_bp.route('/account-status', methods=['GET'])
@token_required
def get_account_status():
    """
    Vérifie le statut du compte Stripe Connect d'un freelance
    ---
    tags:
      - Stripe
    security:
      - Bearer: []
    responses:
      200:
        description: Statut du compte Stripe Connect récupéré
        schema:
          type: object
          properties:
            charges_enabled:
              type: boolean
              description: Indique si les paiements sont activés
            payouts_enabled:
              type: boolean
              description: Indique si les virements sont activés
            capabilities:
              type: object
              description: Capacités activées pour le compte
            requirements:
              type: object
              description: Exigences en cours pour le compte
      400:
        description: Aucun compte Stripe Connect associé
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            user_query = text("""
                SELECT id, stripe_account_id
                FROM users
                WHERE id = :user_id
            """)
            
            user = conn.execute(user_query, {"user_id": user_id}).fetchone()
            
            if not user:
                return jsonify({'message': 'Utilisateur non trouvé'}), 404
            
            if not user.stripe_account_id:
                return jsonify({'message': 'Aucun compte Stripe Connect associé'}), 400
            
            # Vérifier le statut du compte
            status = check_account_status(user.stripe_account_id)
            
            # Mettre à jour le statut des paiements dans la base de données
            update_query = text("""
                UPDATE users
                SET payout_enabled = :payout_enabled
                WHERE id = :user_id
            """)
            
            conn.execute(update_query, {
                "payout_enabled": status.get('payouts_enabled', False),
                "user_id": user_id
            })
            
            # Commit les changements
            conn.commit()
            
            return jsonify(status)
    except Exception as e:
        logger.error(f"Error checking Stripe account status: {str(e)}")
        return jsonify({'message': f'Erreur lors de la vérification du statut: {str(e)}'}), 500

# Webhook Stripe pour les événements de paiement
@stripe_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Webhook pour les événements Stripe
    ---
    tags:
      - Stripe
    parameters:
      - in: header
        name: Stripe-Signature
        schema:
          type: string
        required: false
        description: Signature Stripe pour vérifier l'authenticité du webhook
    responses:
      200:
        description: Événement traité avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de confirmation
      400:
        description: Payload invalide ou signature invalide
      500:
        description: Erreur serveur
    """
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    if not sig_header and not STRIPE_WEBHOOK_SECRET:
        # En développement, on peut ignorer la vérification de signature
        event = stripe.Event.construct_from(
            request.json, stripe.api_key
        )
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid payload: {str(e)}")
            return jsonify({'message': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {str(e)}")
            return jsonify({'message': 'Invalid signature'}), 400
    
    # Gérer l'événement
    if event.type == 'checkout.session.completed':
        try:
            # Traiter le paiement réussi
            session_data = handle_checkout_session_completed(event.data)
            
            # Enregistrer la vente en base de données
            engine = current_app.config.get('db_engine')
            if not engine:
                logger.error("Database connection error in webhook")
                return jsonify({'message': 'Database connection error'}), 500
            
            with engine.connect() as conn:
                # Créer une vente
                vente_query = text("""
                    INSERT INTO ventes (
                        user_id, client_id, produit_id,
                        montant, description, date,
                        source, commission_plateforme,
                        stripe_payment_id, statut_paiement
                    )
                    VALUES (
                        :freelance_id, :client_id, :product_id,
                        :montant, 'Paiement via Stripe', NOW(),
                        'stripe', :commission_plateforme,
                        :stripe_payment_id, :statut_paiement
                    )
                    RETURNING id
                """)
                
                result = conn.execute(vente_query, session_data)
                vente_id = result.fetchone()[0]
                
                # Commit les changements
                conn.commit()
                
                logger.info(f"Sale recorded successfully with ID: {vente_id}")
        except Exception as e:
            logger.error(f"Error processing checkout.session.completed: {str(e)}")
            # On renvoie 200 même en cas d'erreur pour éviter les retentatives de Stripe
            return jsonify({'message': 'Processed with error (will not retry)'}), 200
    
    # Traiter d'autres types d'événements si nécessaire
    # ...
    
    return jsonify({'message': 'Success'}), 200