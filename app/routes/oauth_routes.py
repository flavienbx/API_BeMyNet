import os
import logging
from flask import Blueprint, request, redirect, jsonify, url_for, current_app
from sqlalchemy import text

from app.utils.oauth import (
    get_google_auth_url, get_google_token, get_google_user_info,
    get_discord_auth_url, get_discord_token, get_discord_user_info
)
from app.utils.user_management import find_or_create_social_user
from app.utils.jwt_utils import create_oauth_tokens, generate_oauth_redirect_url

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes OAuth
oauth_bp = Blueprint('oauth', __name__, url_prefix='/auth')

# Base URL pour les redirections
BASE_URL = "https://api.bemynet.fr"


# Routes Google OAuth
@oauth_bp.route('/google/login')
def google_login():
    """
    Redirige l'utilisateur vers la page de connexion Google
    ---
    tags:
      - Authentification
    responses:
      302:
        description: Redirection vers la page d'authentification Google
    """
    redirect_uri = f"{BASE_URL}{url_for('oauth.google_callback')}"
    auth_url = get_google_auth_url(redirect_uri)
    return redirect(auth_url)

@oauth_bp.route('/google/callback')
def google_callback():
    """
    Gère le callback après authentification Google
    ---
    tags:
      - Authentification
    parameters:
      - in: query
        name: code
        required: true
        schema:
          type: string
        description: Code d'autorisation fourni par Google
    responses:
      302:
        description: Redirection vers le frontend avec les tokens JWT
      400:
        description: Code d'autorisation manquant
      403:
        description: Email non vérifié
      500:
        description: Erreur serveur
    """
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'Authorization code missing'}), 400
    
    redirect_uri = f"{BASE_URL}{url_for('oauth.google_callback')}"
    
    try:
        # Échanger le code contre un token
        token_data = get_google_token(code, redirect_uri)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logger.error(f"Failed to get Google access token: {token_data}")
            return jsonify({'error': 'Failed to get access token from Google'}), 500
        
        # Récupérer les informations de l'utilisateur
        userinfo = get_google_user_info(access_token)
        
        if not userinfo.get('email_verified'):
            return jsonify({'error': 'Google email not verified'}), 403
        
        provider_user_id = userinfo.get('sub')
        email = userinfo.get('email')
        full_name = userinfo.get('name') or f"{userinfo.get('given_name', '')} {userinfo.get('family_name', '')}".strip()
        
        if not provider_user_id or not email:
            return jsonify({'error': 'Unable to get user info from Google'}), 500
        
        # Trouver ou créer l'utilisateur
        engine = current_app.config.get('db_engine')
        if not engine:
            return jsonify({'error': 'Database connection error'}), 500
        
        with engine.connect() as conn:
            user = find_or_create_social_user(
                conn=conn,
                provider="google",
                provider_user_id=provider_user_id,
                email=email,
                full_name=full_name
            )
            
            # Créer les tokens JWT
            access_token, refresh_token = create_oauth_tokens(
                user_id=user['id'],
                full_name=user['full_name'],
                email=user['email'],
                role=user['role']
            )
            
            # Générer l'URL de redirection
            redirect_url = generate_oauth_redirect_url(
                access_token=access_token,
                refresh_token=refresh_token,
                is_new_user=user['is_new']
            )
            
            # Valider la transaction
            conn.commit()
            
            # Rediriger vers le frontend
            return redirect(redirect_url)
    
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}")
        return jsonify({'error': f'Authentication error: {str(e)}'}), 500

# Routes Discord OAuth
@oauth_bp.route('/discord/login')
def discord_login():
    """
    Redirige l'utilisateur vers la page de connexion Discord
    ---
    tags:
      - Authentification
    responses:
      302:
        description: Redirection vers la page d'authentification Discord
    """
    redirect_uri = f"{BASE_URL}{url_for('oauth.discord_callback')}"
    auth_url = get_discord_auth_url(redirect_uri)
    return redirect(auth_url)

@oauth_bp.route('/discord/callback')
def discord_callback():
    """
    Gère le callback après authentification Discord
    ---
    tags:
      - Authentification
    parameters:
      - in: query
        name: code
        required: true
        schema:
          type: string
        description: Code d'autorisation fourni par Discord
    responses:
      302:
        description: Redirection vers le frontend avec les tokens JWT
      400:
        description: Code d'autorisation manquant
      403:
        description: Email non vérifié
      500:
        description: Erreur serveur
    """
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'Authorization code missing'}), 400
    
    redirect_uri = f"{BASE_URL}{url_for('oauth.discord_callback')}"
    
    try:
        # Échanger le code contre un token
        token_data = get_discord_token(code, redirect_uri)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logger.error(f"Failed to get Discord access token: {token_data}")
            return jsonify({'error': 'Failed to get access token from Discord'}), 500
        
        # Récupérer les informations de l'utilisateur
        userinfo = get_discord_user_info(access_token)
        
        provider_user_id = userinfo.get('id')
        email = userinfo.get('email')
        full_name = userinfo.get('username')
        
        if not provider_user_id or not email:
            return jsonify({'error': 'Unable to get user info from Discord'}), 500
        
        # Vérifier que l'email est vérifié
        if not userinfo.get('verified', False):
            return jsonify({'error': 'Discord email not verified'}), 403
        
        # Trouver ou créer l'utilisateur
        engine = current_app.config.get('db_engine')
        if not engine:
            return jsonify({'error': 'Database connection error'}), 500
        
        with engine.connect() as conn:
            user = find_or_create_social_user(
                conn=conn,
                provider="discord",
                provider_user_id=provider_user_id,
                email=email,
                full_name=full_name
            )
            
            # Créer les tokens JWT
            access_token, refresh_token = create_oauth_tokens(
                user_id=user['id'],
                full_name=user['full_name'],
                email=user['email'],
                role=user['role']
            )
            
            # Générer l'URL de redirection
            redirect_url = generate_oauth_redirect_url(
                access_token=access_token,
                refresh_token=refresh_token,
                is_new_user=user['is_new']
            )
            
            # Valider la transaction
            conn.commit()
            
            # Rediriger vers le frontend
            return redirect(redirect_url)
    
    except Exception as e:
        logger.error(f"Error in Discord OAuth callback: {str(e)}")
        return jsonify({'error': f'Authentication error: {str(e)}'}), 500