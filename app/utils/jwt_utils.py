import os
import jwt
import logging
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, Tuple

# Configuration du logger
logger = logging.getLogger(__name__)

# Obtenir les clés et paramètres depuis les variables d'environnement
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super_secret_key_change_this_in_production")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7))
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://bemynet.fr")

# Avertissement si la clé par défaut est utilisée
if JWT_SECRET_KEY == "super_secret_key_change_this_in_production":
    logger.warning("JWT_SECRET_KEY not provided, using temporary key (will change on restart)")

def create_access_token(user_id: Union[str, int], name: Optional[str] = None, email: Optional[str] = None, role: Optional[str] = None) -> str:
    expiration = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        'sub': str(user_id),
        'exp': int(expiration.timestamp()),
        'iat': int(time.time()),
        'type': 'access'
    }
    if name: payload['name'] = name
    if email: payload['email'] = email
    if role: payload['role'] = role

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: Union[str, int]) -> str:
    """
    Crée un token JWT de rafraîchissement.
    
    Args:
        user_id: L'identifiant de l'utilisateur
        
    Returns:
        str: Le token JWT de rafraîchissement
    """
    # Timestamp pour l'expiration (plus long pour les refresh tokens)
    expiration = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Données à encoder dans le token
    payload = {
        'sub': str(user_id),
        'exp': int(expiration.timestamp()),
        'iat': int(time.time()),
        'type': 'refresh'
    }
    
    # Génération du token
    try:
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return token
    except Exception as e:
        logger.error(f"Erreur lors de la création du refresh token: {str(e)}")
        raise

def decode_token(token: str) -> Optional[Dict]:
    """
    Décode et vérifie un token JWT.
    
    Args:
        token: Le token JWT à vérifier
        
    Returns:
        Optional[Dict]: Les données décodées du token ou None si invalide
    """
    try:
        # Décodage et vérification du token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expiré")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Token invalide")
        return None
    except Exception as e:
        logger.error(f"Erreur lors du décodage du token: {str(e)}")
        return None

def create_oauth_tokens(user_id: int, full_name: str, email: str, role: str) -> Tuple[str, str]:
    """
    Crée des tokens d'accès et de rafraîchissement pour un utilisateur OAuth.
    
    Args:
        user_id: ID de l'utilisateur
        full_name: Nom complet
        email: Adresse email
        role: Rôle de l'utilisateur
        
    Returns:
        Tuple[str, str]: Tuple contenant (access_token, refresh_token)
    """
    try:
        # Créer un access token avec des informations supplémentaires
        expiration = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_payload = {
            'sub': str(user_id),
            'exp': int(expiration.timestamp()),
            'iat': int(time.time()),
            'type': 'access',
            'name': full_name,
            'email': email,
            'role': role
        }
        
        access_token = jwt.encode(access_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        # Créer un refresh token
        expiration = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_payload = {
            'sub': str(user_id),
            'exp': int(expiration.timestamp()),
            'iat': int(time.time()),
            'type': 'refresh'
        }
        
        refresh_token = jwt.encode(refresh_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        return access_token, refresh_token
    
    except Exception as e:
        logger.error(f"Erreur lors de la création des tokens OAuth: {str(e)}")
        raise

def generate_oauth_redirect_url(access_token: str, refresh_token: str, is_new_user: bool = False) -> str:
    """
    Génère une URL de redirection après authentification OAuth.
    
    Args:
        access_token: Token JWT d'accès
        refresh_token: Token JWT de rafraîchissement
        is_new_user: Indique si l'utilisateur vient d'être créé
        
    Returns:
        str: URL de redirection avec les tokens en query params
    """
    try:
        # Construire l'URL avec les paramètres
        params = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'is_new_user': '1' if is_new_user else '0'
        }
        
        # Ajouter les paramètres à l'URL du frontend
        query_string = urllib.parse.urlencode(params)
        redirect_url = f"{FRONTEND_URL}/auth/oauth?{query_string}"
        
        return redirect_url
    
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'URL de redirection: {str(e)}")
        # En cas d'erreur, rediriger vers la page d'accueil
        return FRONTEND_URL