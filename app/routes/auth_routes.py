import logging
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from datetime import datetime
from functools import wraps
from flasgger import swag_from

from app.utils.password_utils import hash_password, verify_password
from app.utils.jwt_utils import create_access_token, create_refresh_token, decode_token

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes d'authentification par email
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Middleware d'authentification pour les routes protégées
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
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'message': 'Token is invalid!'}), 401
        
        if payload.get('type') != 'access':
            return jsonify({'message': 'Invalid token type. Access token required.'}), 401
        
        # Add user_id to request for route handlers
        request.user_id = int(payload['sub'])
        
        return f(*args, **kwargs)
    
    return decorated

@auth_bp.route('/signup', methods=['POST'])
def signup():
    """
    Inscription d'un nouvel utilisateur par email
    ---
    tags:
      - Authentification
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
            - full_name
          properties:
            email:
              type: string
              format: email
              description: Email de l'utilisateur
            password:
              type: string
              format: password
              description: Mot de passe (8 caractères minimum)
            full_name:
              type: string
              description: Nom complet de l'utilisateur
            role:
              type: string
              enum: [freelance, client, admin, agent]
              default: freelance
              description: Rôle de l'utilisateur
    responses:
      201:
        description: Utilisateur créé avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de succès
            user_id:
              type: integer
              description: ID de l'utilisateur créé
            access_token:
              type: string
              description: JWT access token
            refresh_token:
              type: string
              description: JWT refresh token
      400:
        description: Données invalides
      409:
        description: Email déjà utilisé
      500:
        description: Erreur serveur
    """
    data = request.json
    
    # Vérifier les données requises
    if not data:
        return jsonify({'message': 'No input data provided'}), 400
    
    required_fields = ['email', 'password', 'full_name']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Field {field} is required'}), 400
    
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name')
    role = data.get('role', 'freelance')
    
    # Validation des données
    if len(password) < 8:
        return jsonify({'message': 'Password must be at least 8 characters long'}), 400
    
    if role not in ['freelance', 'client', 'admin', 'agent']:
        return jsonify({'message': 'Invalid role. Must be one of: freelance, client, admin, agent'}), 400
    
    # Hachage du mot de passe
    hashed_password = hash_password(password)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si l'email existe déjà
            check_query = text("""
                SELECT id FROM authentifications WHERE email = :email
                UNION
                SELECT id FROM users WHERE email = :email
            """)
            
            existing_user = conn.execute(check_query, {"email": email}).fetchone()
            
            if existing_user:
                return jsonify({'message': 'Email already in use'}), 409
            
            # Créer l'utilisateur
            insert_user_query = text("""
                INSERT INTO users (
                    email, full_name, role, created_at, account_status
                )
                VALUES (
                    :email, :full_name, :role, NOW(), 'pending'
                )
                RETURNING id
            """)
            
            user_result = conn.execute(insert_user_query, {
                "email": email,
                "full_name": full_name,
                "role": role
            })
            
            user_id = user_result.fetchone()[0]
            
            # Créer l'authentification
            insert_auth_query = text("""
                INSERT INTO authentifications (
                    user_id, provider, email, password_hash, created_at
                )
                VALUES (
                    :user_id, 'email', :email, :password_hash, NOW()
                )
            """)
            
            conn.execute(insert_auth_query, {
                "user_id": user_id,
                "email": email,
                "password_hash": hashed_password
            })
            
            # Mettre à jour la date de dernière connexion
            update_login_query = text("""
                UPDATE users
                SET last_login_at = NOW()
                WHERE id = :user_id
            """)
            
            conn.execute(update_login_query, {"user_id": user_id})
            
            # Créer les JWT tokens
            access_token = create_access_token(user_id)
            refresh_token = create_refresh_token(user_id)
            
            # Valider la transaction
            conn.commit()
            
            return jsonify({
                'message': 'User created successfully',
                'user_id': user_id,
                'access_token': access_token,
                'refresh_token': refresh_token
            }), 201
    
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Connexion d'un utilisateur par email et mot de passe
    ---
    tags:
      - Authentification
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              description: Email de l'utilisateur
            password:
              type: string
              format: password
              description: Mot de passe
    responses:
      200:
        description: Connexion réussie
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de succès
            user_id:
              type: integer
              description: ID de l'utilisateur
            access_token:
              type: string
              description: JWT access token
            refresh_token:
              type: string
              description: JWT refresh token
            user:
              type: object
              properties:
                id:
                  type: integer
                email:
                  type: string
                full_name:
                  type: string
                role:
                  type: string
      400:
        description: Données invalides
      401:
        description: Identifiants incorrects
      500:
        description: Erreur serveur
    """
    data = request.json
    
    # Vérifier les données requises
    if not data:
        return jsonify({'message': 'No input data provided'}), 400
    
    required_fields = ['email', 'password']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Field {field} is required'}), 400
    
    email = data.get('email')
    password = data.get('password')
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer l'utilisateur
            query = text("""
                SELECT a.id as auth_id, a.password_hash, a.user_id,
                       u.email, u.full_name, u.role
                FROM authentifications a
                JOIN users u ON a.user_id = u.id
                WHERE a.email = :email AND a.provider = 'email'
            """)
            
            user = conn.execute(query, {"email": email}).fetchone()
            
            if not user or not verify_password(password, user.password_hash):
                return jsonify({'message': 'Invalid email or password'}), 401
            
            # Mettre à jour la date de dernière connexion
            conn.execute(text("""
                UPDATE authentifications
                SET last_login_at = NOW()
                WHERE id = :auth_id
            """), {"auth_id": user.auth_id})

            conn.execute(text("""
                UPDATE users
                SET last_login_at = NOW()
                WHERE id = :user_id
            """), {"user_id": user.user_id})
            
            # Créer les JWT tokens
            access_token = create_access_token(user.user_id)
            refresh_token = create_refresh_token(user.user_id)
            
            # Valider la transaction
            conn.commit()
            
            return jsonify({
                'message': 'Login successful',
                'user_id': user.user_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user.user_id,
                    'email': user.email,
                    'full_name': user.full_name,
                    'role': user.role
                }
            }), 200
    
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """
    Rafraîchir un token d'accès à partir d'un refresh token
    ---
    tags:
      - Authentification
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - refresh_token
          properties:
            refresh_token:
              type: string
              description: JWT refresh token
    responses:
      200:
        description: Token rafraîchi avec succès
        schema:
          type: object
          properties:
            access_token:
              type: string
              description: Nouveau JWT access token
      400:
        description: Données invalides
      401:
        description: Token invalide ou expiré
      500:
        description: Erreur serveur
    """
    data = request.json
    
    # Vérifier les données requises
    if not data or 'refresh_token' not in data:
        return jsonify({'message': 'Refresh token is required'}), 400
    
    refresh_token = data.get('refresh_token')
    
    # Vérifier et décoder le token
    payload = decode_token(refresh_token)
    if not payload:
        return jsonify({'message': 'Invalid refresh token'}), 401
    
    # Vérifier le type de token
    if payload.get('type') != 'refresh':
        return jsonify({'message': 'Invalid token type. Refresh token required.'}), 401
    
    try:
        # Créer un nouveau token d'accès
        user_id = payload['sub']
        new_access_token = create_access_token(user_id)
        
        return jsonify({
            'access_token': new_access_token
        }), 200
    
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_me():
    """
    Récupérer les informations de l'utilisateur connecté
    ---
    tags:
      - Authentification
    security:
      - Bearer: []
    responses:
      200:
        description: Informations de l'utilisateur
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de l'utilisateur
            email:
              type: string
              description: Email de l'utilisateur
            full_name:
              type: string
              description: Nom complet de l'utilisateur
            role:
              type: string
              description: Rôle de l'utilisateur
            account_status:
              type: string
              description: Statut du compte
      401:
        description: Non authentifié ou token invalide
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
            # Récupérer les informations de l'utilisateur
            query = text("""
                SELECT id, email, full_name, role, bio, phone_number, stripe_account_id,
                       payout_enabled, rating, account_status, kyc_status, created_at,
                       last_login_at, total_revenue
                FROM users
                WHERE id = :user_id
            """)
            
            user = conn.execute(query, {"user_id": user_id}).fetchone()
            
            if not user:
                return jsonify({'message': 'User not found'}), 404
            
            # Convertir en dictionnaire
            user_dict = {column: getattr(user, column) for column in user._mapping.keys()}
            
            # Conversion des objets datetime en chaînes
            for key, value in user_dict.items():
                if isinstance(value, datetime):
                    user_dict[key] = value.isoformat()
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if user_dict.get('rating'):
                user_dict['rating'] = float(user_dict['rating'])
            if user_dict.get('total_revenue'):
                user_dict['total_revenue'] = float(user_dict['total_revenue'])
            
            return jsonify(user_dict), 200
    
    except Exception as e:
        logger.error(f"Error getting user data: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout():
    """
    Déconnexion de l'utilisateur (blacklist du token)
    ---
    tags:
      - Authentification
    security:
      - Bearer: []
    responses:
      200:
        description: Déconnexion réussie
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de succès
      401:
        description: Non authentifié ou token invalide
      500:
        description: Erreur serveur
    """
    # Dans une implémentation réelle, on ajouterait le token à une blacklist
    # Pour simplifier, on considère que le client supprimera le token côté frontend
    
    return jsonify({
        'message': 'Successfully logged out'
    }), 200