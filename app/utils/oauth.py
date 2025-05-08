import os
import logging
import requests
from urllib.parse import urlencode

# Configurer le logging
logger = logging.getLogger(__name__)

# Configuration Google OAuth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Configuration Discord OAuth
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USERINFO_URL = "https://discord.com/api/users/@me"

def get_google_auth_url(redirect_uri):
    """
    Génère l'URL d'authentification Google
    
    Args:
        redirect_uri: URL de redirection après authentification
    
    Returns:
        str: URL d'authentification Google
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return auth_url

def get_google_token(code, redirect_uri):
    """
    Échange un code d'autorisation contre un token d'accès Google
    
    Args:
        code: Code d'autorisation reçu de Google
        redirect_uri: URL de redirection utilisée pour l'authentification
    
    Returns:
        dict: Données du token Google (access_token, refresh_token, etc.)
    """
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(GOOGLE_TOKEN_URL, data=data)
    return response.json()

def get_google_user_info(access_token):
    """
    Récupère les informations de l'utilisateur Google
    
    Args:
        access_token: Token d'accès Google
    
    Returns:
        dict: Informations de l'utilisateur Google
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(GOOGLE_USERINFO_URL, headers=headers)
    return response.json()

def get_discord_auth_url(redirect_uri):
    """
    Génère l'URL d'authentification Discord
    
    Args:
        redirect_uri: URL de redirection après authentification
    
    Returns:
        str: URL d'authentification Discord
    """
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email"
    }
    
    auth_url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"
    return auth_url

def get_discord_token(code, redirect_uri):
    """
    Échange un code d'autorisation contre un token d'accès Discord
    
    Args:
        code: Code d'autorisation reçu de Discord
        redirect_uri: URL de redirection utilisée pour l'authentification
    
    Returns:
        dict: Données du token Discord (access_token, refresh_token, etc.)
    """
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
    return response.json()

def get_discord_user_info(access_token):
    """
    Récupère les informations de l'utilisateur Discord
    
    Args:
        access_token: Token d'accès Discord
    
    Returns:
        dict: Informations de l'utilisateur Discord
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(DISCORD_USERINFO_URL, headers=headers)
    return response.json()