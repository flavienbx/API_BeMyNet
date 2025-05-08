import bcrypt
import logging

# Configuration du logger
logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    """
    Hash un mot de passe en utilisant bcrypt.
    
    Args:
        password: Le mot de passe en clair à hacher
        
    Returns:
        str: Le mot de passe haché en format string UTF-8
    """
    try:
        # Générer un salt aléatoire et hacher le mot de passe
        # 12 est un bon équilibre entre sécurité et performance
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        # Retourner le hash sous forme de chaîne
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Erreur lors du hachage du mot de passe: {str(e)}")
        raise

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Vérifie si un mot de passe en clair correspond à un hash.
    
    Args:
        plain_password: Le mot de passe en clair
        hashed_password: Le hash du mot de passe stocké
        
    Returns:
        bool: True si le mot de passe correspond, False sinon
    """
    try:
        # Encoder les entrées en bytes
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        
        # Vérifier le mot de passe
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du mot de passe: {str(e)}")
        return False