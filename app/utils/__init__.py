# Ce fichier rend le dossier utils un module Python
# Import des différentes utilitaires pour les exposer à l'application principale

from app.utils.oauth import (
    get_google_auth_url, get_google_token, get_google_user_info,
    get_discord_auth_url, get_discord_token, get_discord_user_info
)
from app.utils.user_management import find_or_create_social_user
from app.utils.jwt_utils import (
    create_access_token, create_refresh_token, decode_token
)

# Liste des utilitaires disponibles
__all__ = [
    'get_google_auth_url', 'get_google_token', 'get_google_user_info',
    'get_discord_auth_url', 'get_discord_token', 'get_discord_user_info',
    'find_or_create_social_user',
    'create_access_token', 'create_refresh_token', 'decode_token'
]