import logging
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from functools import wraps
import uuid

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes de commerciaux et partenaires
partner_bp = Blueprint('partner', __name__)

# Middleware d'authentification (identique aux autres routes)
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

# Middleware pour vérifier si l'utilisateur est admin
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = request.user_id
        
        engine = current_app.config.get('db_engine')
        if not engine:
            return jsonify({'message': 'Database connection error'}), 500
        
        try:
            with engine.connect() as conn:
                role_query = text("SELECT role FROM users WHERE id = :user_id")
                role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
                
                if not role_result or role_result.role != 'admin':
                    return jsonify({'message': 'Admin role required'}), 403
                
                return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Admin check error: {str(e)}")
            return jsonify({'message': 'An error occurred'}), 500
        
    return decorated

# Routes pour les commerciaux
@partner_bp.route('/commerciaux', methods=['GET'])
@token_required
def get_commerciaux():
    """
    Liste tous les commerciaux avec options de filtrage
    ---
    tags:
      - Partenaires
    security:
      - Bearer: []
    parameters:
      - in: query
        name: user_id
        type: integer
        description: Filtrer par ID d'utilisateur
      - in: query
        name: status
        type: string
        enum: [actif, inactif]
        description: Filtrer par statut
      - in: query
        name: search
        type: string
        description: Recherche par nom ou email
      - in: query
        name: limit
        type: integer
        default: 50
        description: Nombre maximum de résultats à retourner
      - in: query
        name: offset
        type: integer
        default: 0
        description: Décalage pour la pagination
    responses:
      200:
        description: Liste des commerciaux
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID du commercial
              user_id:
                type: integer
                description: ID de l'utilisateur associé
              full_name:
                type: string
                description: Nom complet du commercial
              email:
                type: string
                description: Email de contact
              phone:
                type: string
                description: Numéro de téléphone
              status:
                type: string
                enum: [actif, inactif]
                description: Statut du commercial
              commission_rate:
                type: number
                format: float
                description: Taux de commission en pourcentage
              description:
                type: string
                description: Description du rôle ou spécialité
              date_creation:
                type: string
                format: date-time
                description: Date de création
              tracking_code:
                type: string
                description: Code d'affiliation unique
      401:
        description: Non authentifié
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    # Récupérer les filtres de la requête
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT c.*, u.full_name as creator_name",
                "FROM commerciaux c",
                "LEFT JOIN users u ON c.user_id = u.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Si non admin, limiter aux commerciaux créés par l'utilisateur
            if not is_admin:
                query_parts.append("AND c.user_id = :user_id")
                params["user_id"] = user_id
            
            # Ajouter les filtres
            if status:
                query_parts.append("AND c.status = :status")
                params["status"] = status
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY c.created_at DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            commerciaux = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for commercial in commerciaux:
                commercial_dict = {column: getattr(commercial, column) for column in commercial._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                if commercial_dict.get('pourcentage'):
                    commercial_dict['pourcentage'] = float(commercial_dict['pourcentage'])
                
                result.append(commercial_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting commerciaux: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/commerciaux', methods=['POST'])
@token_required
def create_commercial():
    """
    Crée un nouveau commercial avec un code de tracking unique
    ---
    tags:
      - Partenaires
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - full_name
            - email
            - pourcentage
          properties:
            full_name:
              type: string
              description: Nom complet du commercial
            email:
              type: string
              description: Email de contact
            pourcentage:
              type: number
              format: float
              minimum: 0
              maximum: 20
              description: Pourcentage de commission (0-20%)
            phone:
              type: string
              description: Numéro de téléphone
            status:
              type: string
              enum: [actif, inactif]
              default: actif
              description: Statut initial du commercial
            description:
              type: string
              description: Description de ses responsabilités
            tracking_code:
              type: string
              description: Code d'affiliation personnalisé (généré automatiquement si non fourni)
    responses:
      201:
        description: Commercial créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du commercial créé
            message:
              type: string
              description: Message de confirmation
            tracking_code:
              type: string
              description: Code de tracking généré ou fourni
      400:
        description: Données invalides (ex. pourcentage hors limites)
      401:
        description: Non authentifié
      409:
        description: Un commercial avec cet email existe déjà
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['full_name', 'email', 'pourcentage']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    full_name = data['full_name']
    email = data['email']
    pourcentage = float(data['pourcentage'])
    status = data.get('status', 'actif')
    tracking_code = data.get('tracking_code', str(uuid.uuid4()).split('-')[0].upper())
    
    # Valider le pourcentage (entre 0 et 20)
    if not 0 <= pourcentage <= 20:
        return jsonify({'message': 'Le pourcentage doit être compris entre 0 et 20'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si un commercial avec cet email existe déjà
            check_query = text("SELECT id FROM commerciaux WHERE email = :email")
            existing = conn.execute(check_query, {"email": email}).fetchone()
            
            if existing:
                return jsonify({'message': 'Un commercial avec cet email existe déjà'}), 409
            
            # Insérer le commercial
            insert_query = text("""
                INSERT INTO commerciaux (
                    full_name, email, pourcentage, status,
                    tracking_code, user_id, created_at
                )
                VALUES (
                    :full_name, :email, :pourcentage, :status,
                    :tracking_code, :user_id, NOW()
                )
                RETURNING id
            """)
            
            result = conn.execute(insert_query, {
                "full_name": full_name,
                "email": email,
                "pourcentage": pourcentage,
                "status": status,
                "tracking_code": tracking_code,
                "user_id": user_id
            })
            
            commercial_id = result.fetchone()[0]
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'id': commercial_id,
                'message': 'Commercial créé avec succès',
                'tracking_code': tracking_code
            }), 201
    except Exception as e:
        logger.error(f"Error creating commercial: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/commerciaux/<int:commercial_id>', methods=['GET'])
@token_required
def get_commercial(commercial_id):
    """
    Récupère les détails d'un commercial avec ses statistiques de ventes
    ---
    tags:
      - Partenaires
    security:
      - Bearer: []
    parameters:
      - in: path
        name: commercial_id
        required: true
        type: integer
        description: ID du commercial à récupérer
    responses:
      200:
        description: Détails du commercial
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du commercial
            user_id:
              type: integer
              description: ID de l'utilisateur associé
            full_name:
              type: string
              description: Nom complet du commercial
            email:
              type: string
              description: Email de contact
            pourcentage:
              type: number
              format: float
              description: Taux de commission
            status:
              type: string
              enum: [actif, inactif]
              description: Statut actuel
            tracking_code:
              type: string
              description: Code de tracking pour l'affiliation
            created_at:
              type: string
              format: date-time
              description: Date de création
            creator_name:
              type: string
              description: Nom de l'utilisateur qui a créé ce commercial
            stats:
              type: object
              properties:
                total_sales:
                  type: integer
                  description: Nombre total de ventes
                total_amount:
                  type: number
                  format: float
                  description: Montant total des ventes
                total_commission:
                  type: number
                  format: float
                  description: Montant total des commissions
      401:
        description: Non authentifié
      403:
        description: Non autorisé à accéder à cette ressource
      404:
        description: Commercial non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Récupérer le commercial
            query = text("""
                SELECT c.*, u.full_name as creator_name
                FROM commerciaux c
                LEFT JOIN users u ON c.user_id = u.id
                WHERE c.id = :commercial_id AND (c.user_id = :user_id OR :is_admin)
            """)
            
            commercial = conn.execute(query, {
                "commercial_id": commercial_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not commercial:
                return jsonify({'message': 'Commercial non trouvé ou non autorisé'}), 404
            
            # Convertir en dictionnaire
            commercial_dict = {column: getattr(commercial, column) for column in commercial._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if commercial_dict.get('pourcentage'):
                commercial_dict['pourcentage'] = float(commercial_dict['pourcentage'])
            
            # Récupérer les statistiques de vente
            stats_query = text("""
                SELECT 
                    COUNT(v.id) as total_sales,
                    SUM(v.montant) as total_amount,
                    SUM(v.commission_commerciale) as total_commission
                FROM ventes v
                WHERE v.commercial_id = :commercial_id
            """)
            
            stats = conn.execute(stats_query, {"commercial_id": commercial_id}).fetchone()
            
            if stats:
                commercial_dict['stats'] = {
                    'total_sales': stats.total_sales or 0,
                    'total_amount': float(stats.total_amount or 0),
                    'total_commission': float(stats.total_commission or 0)
                }
            
            return jsonify(commercial_dict)
    except Exception as e:
        logger.error(f"Error getting commercial details: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/commerciaux/<int:commercial_id>', methods=['PUT'])
@token_required
def update_commercial(commercial_id):
    """
    Met à jour un commercial
    """
    user_id = request.user_id
    data = request.json
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Vérifier l'accès au commercial
            check_query = text("""
                SELECT id FROM commerciaux
                WHERE id = :commercial_id AND (user_id = :user_id OR :is_admin)
            """)
            
            commercial = conn.execute(check_query, {
                "commercial_id": commercial_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not commercial:
                return jsonify({'message': 'Commercial non trouvé ou non autorisé'}), 404
            
            # Construire la requête de mise à jour
            update_parts = []
            params = {
                "commercial_id": commercial_id
            }
            
            # Champs modifiables
            if 'full_name' in data:
                update_parts.append("full_name = :full_name")
                params["full_name"] = data['full_name']
            
            if 'email' in data:
                # Vérifier que l'email n'existe pas déjà
                check_email_query = text("""
                    SELECT id FROM commerciaux
                    WHERE email = :email AND id != :commercial_id
                """)
                
                existing = conn.execute(check_email_query, {
                    "email": data['email'],
                    "commercial_id": commercial_id
                }).fetchone()
                
                if existing:
                    return jsonify({'message': 'Un commercial avec cet email existe déjà'}), 409
                
                update_parts.append("email = :email")
                params["email"] = data['email']
            
            if 'pourcentage' in data:
                pourcentage = float(data['pourcentage'])
                
                # Valider le pourcentage
                if not 0 <= pourcentage <= 20:
                    return jsonify({'message': 'Le pourcentage doit être compris entre 0 et 20'}), 400
                
                update_parts.append("pourcentage = :pourcentage")
                params["pourcentage"] = pourcentage
            
            if 'status' in data:
                update_parts.append("status = :status")
                params["status"] = data['status']
            
            if 'tracking_code' in data:
                # Vérifier que le code n'existe pas déjà
                check_code_query = text("""
                    SELECT id FROM commerciaux
                    WHERE tracking_code = :tracking_code AND id != :commercial_id
                """)
                
                existing = conn.execute(check_code_query, {
                    "tracking_code": data['tracking_code'],
                    "commercial_id": commercial_id
                }).fetchone()
                
                if existing:
                    return jsonify({'message': 'Ce code de tracking existe déjà'}), 409
                
                update_parts.append("tracking_code = :tracking_code")
                params["tracking_code"] = data['tracking_code']
            
            if 'contract_signed_at' in data:
                update_parts.append("contract_signed_at = :contract_signed_at")
                params["contract_signed_at"] = data['contract_signed_at']
            
            # Si aucun champ à mettre à jour
            if not update_parts:
                return jsonify({'message': 'Aucun champ à mettre à jour'}), 400
            
            # Exécuter la mise à jour
            update_query = text(f"""
                UPDATE commerciaux
                SET {", ".join(update_parts)}
                WHERE id = :commercial_id
                RETURNING id
            """)
            
            result = conn.execute(update_query, params)
            updated = result.fetchone()
            
            if not updated:
                return jsonify({'message': 'Échec de la mise à jour'}), 500
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'message': 'Commercial mis à jour avec succès',
                'id': commercial_id
            })
    except Exception as e:
        logger.error(f"Error updating commercial: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/commerciaux/<int:commercial_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_commercial(commercial_id):
    """
    Supprime un commercial (admin uniquement)
    """
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si le commercial existe
            check_query = text("SELECT id FROM commerciaux WHERE id = :commercial_id")
            commercial = conn.execute(check_query, {"commercial_id": commercial_id}).fetchone()
            
            if not commercial:
                return jsonify({'message': 'Commercial non trouvé'}), 404
            
            # Supprimer le commercial
            delete_query = text("DELETE FROM commerciaux WHERE id = :commercial_id")
            conn.execute(delete_query, {"commercial_id": commercial_id})
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'message': 'Commercial supprimé avec succès'
            })
    except Exception as e:
        logger.error(f"Error deleting commercial: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Routes pour les partenaires
@partner_bp.route('/partenaires', methods=['GET'])
@token_required
def get_partenaires():
    """
    Liste tous les partenaires avec options de filtrage
    ---
    tags:
      - Partenaires
    security:
      - Bearer: []
    parameters:
      - in: query
        name: user_id
        type: integer
        description: Filtrer par ID d'utilisateur
      - in: query
        name: status
        type: string
        enum: [actif, inactif]
        description: Filtrer par statut
      - in: query
        name: search
        type: string
        description: Recherche par nom ou email
      - in: query
        name: type
        type: string
        enum: [agency, individual, company, association]
        description: Filtrer par type de partenaire
      - in: query
        name: limit
        type: integer
        default: 50
        description: Nombre maximum de résultats à retourner
      - in: query
        name: offset
        type: integer
        default: 0
        description: Décalage pour la pagination
    responses:
      200:
        description: Liste des partenaires
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID du partenaire
              user_id:
                type: integer
                description: ID de l'utilisateur associé
              nom:
                type: string
                description: Nom du partenaire
              email:
                type: string
                description: Email de contact
              phone:
                type: string
                description: Numéro de téléphone
              type:
                type: string
                enum: [agency, individual, company, association]
                description: Type de partenaire
              status:
                type: string
                enum: [actif, inactif]
                description: Statut du partenaire
              pourcentage:
                type: number
                format: float
                description: Taux de commission en pourcentage
              description:
                type: string
                description: Description du partenaire
              website:
                type: string
                description: Site web du partenaire
              date_creation:
                type: string
                format: date-time
                description: Date de création
              tracking_code:
                type: string
                description: Code d'affiliation unique
      401:
        description: Non authentifié
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    # Récupérer les filtres de la requête
    status = request.args.get('status')
    type_partenaire = request.args.get('type')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT p.*, u.full_name as creator_name",
                "FROM partenaires p",
                "LEFT JOIN users u ON p.user_id = u.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Si non admin, limiter aux partenaires créés par l'utilisateur
            if not is_admin:
                query_parts.append("AND p.user_id = :user_id")
                params["user_id"] = user_id
            
            # Ajouter les filtres
            if status:
                query_parts.append("AND p.status = :status")
                params["status"] = status
                
            if type_partenaire:
                query_parts.append("AND p.type = :type")
                params["type"] = type_partenaire
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY p.created_at DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            partenaires = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for partenaire in partenaires:
                partenaire_dict = {column: getattr(partenaire, column) for column in partenaire._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                if partenaire_dict.get('pourcentage'):
                    partenaire_dict['pourcentage'] = float(partenaire_dict['pourcentage'])
                
                result.append(partenaire_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting partenaires: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/partenaires', methods=['POST'])
@token_required
def create_partenaire():
    """
    Crée un nouveau partenaire
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['nom', 'type', 'email_contact', 'pourcentage']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    nom = data['nom']
    type_partenaire = data['type']
    email_contact = data['email_contact']
    pourcentage = float(data['pourcentage'])
    status = data.get('status', 'actif')
    tracking_url = data.get('tracking_url', '')
    tracking_code = data.get('tracking_code', str(uuid.uuid4()).split('-')[0].upper())
    
    # Valider le pourcentage (entre 0 et 15)
    if not 0 <= pourcentage <= 15:
        return jsonify({'message': 'Le pourcentage doit être compris entre 0 et 15'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si un partenaire avec cet email existe déjà
            check_query = text("SELECT id FROM partenaires WHERE email_contact = :email")
            existing = conn.execute(check_query, {"email": email_contact}).fetchone()
            
            if existing:
                return jsonify({'message': 'Un partenaire avec cet email existe déjà'}), 409
            
            # Insérer le partenaire
            insert_query = text("""
                INSERT INTO partenaires (
                    nom, type, email_contact, pourcentage, tracking_url,
                    tracking_code, status, user_id, created_at
                )
                VALUES (
                    :nom, :type, :email_contact, :pourcentage, :tracking_url,
                    :tracking_code, :status, :user_id, NOW()
                )
                RETURNING id
            """)
            
            result = conn.execute(insert_query, {
                "nom": nom,
                "type": type_partenaire,
                "email_contact": email_contact,
                "pourcentage": pourcentage,
                "tracking_url": tracking_url,
                "tracking_code": tracking_code,
                "status": status,
                "user_id": user_id
            })
            
            partenaire_id = result.fetchone()[0]
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'id': partenaire_id,
                'message': 'Partenaire créé avec succès',
                'tracking_code': tracking_code
            }), 201
    except Exception as e:
        logger.error(f"Error creating partenaire: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/partenaires/<int:partenaire_id>', methods=['GET'])
@token_required
def get_partenaire(partenaire_id):
    """
    Récupère les détails d'un partenaire
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Récupérer le partenaire
            query = text("""
                SELECT p.*, u.full_name as creator_name
                FROM partenaires p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = :partenaire_id AND (p.user_id = :user_id OR :is_admin)
            """)
            
            partenaire = conn.execute(query, {
                "partenaire_id": partenaire_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not partenaire:
                return jsonify({'message': 'Partenaire non trouvé ou non autorisé'}), 404
            
            # Convertir en dictionnaire
            partenaire_dict = {column: getattr(partenaire, column) for column in partenaire._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if partenaire_dict.get('pourcentage'):
                partenaire_dict['pourcentage'] = float(partenaire_dict['pourcentage'])
            
            # Récupérer les statistiques de vente
            stats_query = text("""
                SELECT 
                    COUNT(v.id) as total_sales,
                    SUM(v.montant) as total_amount,
                    SUM(v.commission_partenaire) as total_commission
                FROM ventes v
                WHERE v.partenaire_id = :partenaire_id
            """)
            
            stats = conn.execute(stats_query, {"partenaire_id": partenaire_id}).fetchone()
            
            if stats:
                partenaire_dict['stats'] = {
                    'total_sales': stats.total_sales or 0,
                    'total_amount': float(stats.total_amount or 0),
                    'total_commission': float(stats.total_commission or 0)
                }
            
            # Récupérer les utilisateurs affiliés
            users_query = text("""
                SELECT id, full_name, email, role
                FROM users
                WHERE partner_id = :partenaire_id
            """)
            
            users = conn.execute(users_query, {"partenaire_id": partenaire_id}).fetchall()
            
            if users:
                partenaire_dict['users'] = [{
                    'id': user.id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'role': user.role
                } for user in users]
            
            return jsonify(partenaire_dict)
    except Exception as e:
        logger.error(f"Error getting partenaire details: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/partenaires/<int:partenaire_id>', methods=['PUT'])
@token_required
def update_partenaire(partenaire_id):
    """
    Met à jour un partenaire
    """
    user_id = request.user_id
    data = request.json
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Vérifier l'accès au partenaire
            check_query = text("""
                SELECT id FROM partenaires
                WHERE id = :partenaire_id AND (user_id = :user_id OR :is_admin)
            """)
            
            partenaire = conn.execute(check_query, {
                "partenaire_id": partenaire_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not partenaire:
                return jsonify({'message': 'Partenaire non trouvé ou non autorisé'}), 404
            
            # Construire la requête de mise à jour
            update_parts = []
            params = {
                "partenaire_id": partenaire_id
            }
            
            # Champs modifiables
            if 'nom' in data:
                update_parts.append("nom = :nom")
                params["nom"] = data['nom']
            
            if 'type' in data:
                update_parts.append("type = :type")
                params["type"] = data['type']
            
            if 'email_contact' in data:
                # Vérifier que l'email n'existe pas déjà
                check_email_query = text("""
                    SELECT id FROM partenaires
                    WHERE email_contact = :email AND id != :partenaire_id
                """)
                
                existing = conn.execute(check_email_query, {
                    "email": data['email_contact'],
                    "partenaire_id": partenaire_id
                }).fetchone()
                
                if existing:
                    return jsonify({'message': 'Un partenaire avec cet email existe déjà'}), 409
                
                update_parts.append("email_contact = :email_contact")
                params["email_contact"] = data['email_contact']
            
            if 'pourcentage' in data:
                pourcentage = float(data['pourcentage'])
                
                # Valider le pourcentage
                if not 0 <= pourcentage <= 15:
                    return jsonify({'message': 'Le pourcentage doit être compris entre 0 et 15'}), 400
                
                update_parts.append("pourcentage = :pourcentage")
                params["pourcentage"] = pourcentage
            
            if 'status' in data:
                update_parts.append("status = :status")
                params["status"] = data['status']
            
            if 'tracking_url' in data:
                update_parts.append("tracking_url = :tracking_url")
                params["tracking_url"] = data['tracking_url']
            
            if 'tracking_code' in data:
                # Vérifier que le code n'existe pas déjà
                check_code_query = text("""
                    SELECT id FROM partenaires
                    WHERE tracking_code = :tracking_code AND id != :partenaire_id
                """)
                
                existing = conn.execute(check_code_query, {
                    "tracking_code": data['tracking_code'],
                    "partenaire_id": partenaire_id
                }).fetchone()
                
                if existing:
                    return jsonify({'message': 'Ce code de tracking existe déjà'}), 409
                
                update_parts.append("tracking_code = :tracking_code")
                params["tracking_code"] = data['tracking_code']
            
            if 'contract_signed_at' in data:
                update_parts.append("contract_signed_at = :contract_signed_at")
                params["contract_signed_at"] = data['contract_signed_at']
            
            # Si aucun champ à mettre à jour
            if not update_parts:
                return jsonify({'message': 'Aucun champ à mettre à jour'}), 400
            
            # Exécuter la mise à jour
            update_query = text(f"""
                UPDATE partenaires
                SET {", ".join(update_parts)}
                WHERE id = :partenaire_id
                RETURNING id
            """)
            
            result = conn.execute(update_query, params)
            updated = result.fetchone()
            
            if not updated:
                return jsonify({'message': 'Échec de la mise à jour'}), 500
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'message': 'Partenaire mis à jour avec succès',
                'id': partenaire_id
            })
    except Exception as e:
        logger.error(f"Error updating partenaire: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@partner_bp.route('/partenaires/<int:partenaire_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_partenaire(partenaire_id):
    """
    Supprime un partenaire (admin uniquement)
    """
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si le partenaire existe
            check_query = text("SELECT id FROM partenaires WHERE id = :partenaire_id")
            partenaire = conn.execute(check_query, {"partenaire_id": partenaire_id}).fetchone()
            
            if not partenaire:
                return jsonify({'message': 'Partenaire non trouvé'}), 404
            
            # Supprimer le partenaire
            delete_query = text("DELETE FROM partenaires WHERE id = :partenaire_id")
            conn.execute(delete_query, {"partenaire_id": partenaire_id})
            
            # Retirer les associations avec les utilisateurs
            update_users_query = text("""
                UPDATE users
                SET partner_id = NULL
                WHERE partner_id = :partenaire_id
            """)
            
            conn.execute(update_users_query, {"partenaire_id": partenaire_id})
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'message': 'Partenaire supprimé avec succès'
            })
    except Exception as e:
        logger.error(f"Error deleting partenaire: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500