import logging
from datetime import datetime
from sqlalchemy import text
from werkzeug.security import generate_password_hash

# Configurer le logging
logger = logging.getLogger(__name__)

def find_or_create_social_user(conn, provider, provider_user_id, email, full_name=None):
    """
    Trouve un utilisateur existant ou en crée un nouveau à partir d'une authentification sociale
    
    Args:
        conn: Connection à la base de données
        provider: Fournisseur d'authentification ('google', 'discord', etc.)
        provider_user_id: ID de l'utilisateur chez le fournisseur d'authentification
        email: Email de l'utilisateur
        full_name: Nom complet de l'utilisateur (optionnel)
    
    Returns:
        dict: Les informations de l'utilisateur trouvé ou créé
    """
    try:
        # Vérifier si une authentification existe déjà pour ce fournisseur et cet ID
        auth_query = text("""
            SELECT a.*, u.* 
            FROM authentifications a
            JOIN users u ON a.user_id = u.id
            WHERE a.provider = :provider AND a.provider_user_id = :provider_user_id
            LIMIT 1
        """)
        
        existing_auth = conn.execute(auth_query, {
            "provider": provider,
            "provider_user_id": provider_user_id
        }).fetchone()
        
        if existing_auth:
            # Mettre à jour la date de dernière connexion
            update_login_query = text("""
                UPDATE authentifications
                SET last_login_at = NOW()
                WHERE id = :auth_id
            """)
            
            conn.execute(update_login_query, {
                "auth_id": existing_auth.id
            })
            
            # Mettre à jour la date de dernière connexion de l'utilisateur
            update_user_query = text("""
                UPDATE users
                SET last_login_at = NOW()
                WHERE id = :user_id
            """)
            
            conn.execute(update_user_query, {
                "user_id": existing_auth.user_id
            })
            
            # Retourner l'utilisateur existant
            return {
                "id": existing_auth.user_id,
                "full_name": existing_auth.full_name,
                "email": existing_auth.email,
                "role": existing_auth.role,
                "is_new": False
            }
        
        # Vérifier si un utilisateur existe avec cet email
        user_query = text("""
            SELECT * FROM users
            WHERE email = :email
            LIMIT 1
        """)
        
        existing_user = conn.execute(user_query, {
            "email": email
        }).fetchone()
        
        user_id = None
        is_new = False
        
        if existing_user:
            # Utiliser l'utilisateur existant
            user_id = existing_user.id
            user_role = existing_user.role
            user_name = existing_user.full_name
        else:
            # Créer un nouvel utilisateur
            insert_user_query = text("""
                INSERT INTO users (
                    full_name, email, role, 
                    account_status, created_at, last_login_at
                )
                VALUES (
                    :full_name, :email, 'freelance',
                    'active', NOW(), NOW()
                )
                RETURNING id, full_name, email, role
            """)
            
            new_user = conn.execute(insert_user_query, {
                "full_name": full_name or email.split('@')[0],
                "email": email
            }).fetchone()
            
            user_id = new_user.id
            user_role = new_user.role
            user_name = new_user.full_name
            is_new = True
        
        # Créer une entrée d'authentification pour cet utilisateur
        insert_auth_query = text("""
            INSERT INTO authentifications (
                user_id, provider, provider_user_id,
                email, created_at, last_login_at
            )
            VALUES (
                :user_id, :provider, :provider_user_id,
                :email, NOW(), NOW()
            )
        """)
        
        conn.execute(insert_auth_query, {
            "user_id": user_id,
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email
        })
        
        # Retourner les informations de l'utilisateur
        return {
            "id": user_id,
            "full_name": user_name,
            "email": email,
            "role": user_role,
            "is_new": is_new
        }
    except Exception as e:
        logger.error(f"Error in find_or_create_social_user: {str(e)}")
        raise