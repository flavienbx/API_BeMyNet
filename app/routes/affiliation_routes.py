import logging
from flask import Blueprint, request, jsonify, current_app, redirect
from sqlalchemy import text
from functools import wraps
import uuid

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes d'affiliation
affiliation_bp = Blueprint('affiliation', __name__, url_prefix='/affiliations')

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

# Endpoint pour lister les affiliations
@affiliation_bp.route('', methods=['GET'])
@token_required
def get_affiliations():
    """
    Liste les affiliations (admin uniquement ou les siennes)
    ---
    tags:
      - Affiliations
    security:
      - Bearer: []
    parameters:
      - in: query
        name: source_type
        type: string
        enum: [commercial, partenaire, lien]
        description: Type de source d'affiliation
      - in: query
        name: source_id
        type: integer
        description: ID de la source d'affiliation
      - in: query
        name: vente_id
        type: integer
        description: ID de la vente liée
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
        description: Liste des affiliations
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID de l'affiliation
              source_type:
                type: string
                enum: [commercial, partenaire, lien]
                description: Type de source
              source_id:
                type: integer
                description: ID de la source
              source_name:
                type: string
                description: Nom de la source
              vente_id:
                type: integer
                description: ID de la vente liée
              commission:
                type: number
                format: float
                description: Montant de la commission
              montant:
                type: number
                format: float
                description: Montant total de la vente
              date:
                type: string
                format: date-time
                description: Date de la vente
              
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    # Récupérer les filtres de la requête
    source_type = request.args.get('source_type')  # 'commercial', 'partenaire', 'lien'
    source_id = request.args.get('source_id')
    vente_id = request.args.get('vente_id')
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
                "SELECT a.*, v.montant, v.date,",
                "CASE",
                "    WHEN a.source_type = 'commercial' THEN c.full_name",
                "    WHEN a.source_type = 'partenaire' THEN p.nom",
                "    ELSE NULL",
                "END as source_name",
                "FROM affiliations a",
                "LEFT JOIN ventes v ON a.vente_id = v.id",
                "LEFT JOIN commerciaux c ON a.source_type = 'commercial' AND a.source_id = c.id",
                "LEFT JOIN partenaires p ON a.source_type = 'partenaire' AND a.source_id = p.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Si non admin, limiter aux affiliations dont l'utilisateur est la source ou le propriétaire de la vente
            if not is_admin:
                query_parts.append("""
                    AND (
                        (a.source_type = 'commercial' AND a.source_id IN (
                            SELECT id FROM commerciaux WHERE user_id = :user_id
                        )) OR
                        (a.source_type = 'partenaire' AND a.source_id IN (
                            SELECT id FROM partenaires WHERE user_id = :user_id
                        )) OR
                        v.user_id = :user_id
                    )
                """)
                params["user_id"] = user_id
            
            # Ajouter les filtres
            if source_type:
                query_parts.append("AND a.source_type = :source_type")
                params["source_type"] = source_type
                
            if source_id:
                query_parts.append("AND a.source_id = :source_id")
                params["source_id"] = int(source_id)
                
            if vente_id:
                query_parts.append("AND a.vente_id = :vente_id")
                params["vente_id"] = int(vente_id)
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY v.date DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            affiliations = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for affiliation in affiliations:
                affiliation_dict = {column: getattr(affiliation, column) for column in affiliation._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                if affiliation_dict.get('commission'):
                    affiliation_dict['commission'] = float(affiliation_dict['commission'])
                if affiliation_dict.get('montant'):
                    affiliation_dict['montant'] = float(affiliation_dict['montant'])
                
                result.append(affiliation_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting affiliations: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer un tracking code
@affiliation_bp.route('/tracking-code', methods=['POST'])
@token_required
def create_tracking_code():
    """
    Crée un code de tracking pour un commercial ou partenaire
    ---
    tags:
      - Affiliations
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - type
          properties:
            type:
              type: string
              enum: [commercial, partenaire]
              description: Type de source d'affiliation
            id:
              type: integer
              description: ID du commercial ou partenaire (si non fourni, utilisera celui associé à l'utilisateur)
            code:
              type: string
              description: Code personnalisé (si non fourni, génération automatique)
    responses:
      200:
        description: Code de tracking créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de la source
            code:
              type: string
              description: Code de tracking généré
            name:
              type: string
              description: Nom de la source
            tracking_url:
              type: string
              description: URL complète de tracking
      400:
        description: Type invalide ou aucune source associée à l'utilisateur
      401:
        description: Non authentifié
      403:
        description: Non autorisé à créer un code pour cette source
      404:
        description: Utilisateur non trouvé
      409:
        description: Code de tracking déjà existant
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['type']  # 'commercial' ou 'partenaire'
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    source_type = data['type']
    source_id = data.get('id')  # ID du commercial ou partenaire
    code = data.get('code')  # Code personnalisé (optionnel)
    
    if source_type not in ['commercial', 'partenaire']:
        return jsonify({'message': 'Type doit être commercial ou partenaire'}), 400
    
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
            
            # Si pas d'ID spécifié, vérifier si l'utilisateur est lui-même un commercial/partenaire
            if not source_id:
                if source_type == 'commercial':
                    source_query = text("""
                        SELECT id FROM commerciaux
                        WHERE user_id = :user_id
                        LIMIT 1
                    """)
                else:  # partenaire
                    source_query = text("""
                        SELECT id FROM partenaires
                        WHERE user_id = :user_id
                        LIMIT 1
                    """)
                
                source = conn.execute(source_query, {"user_id": user_id}).fetchone()
                
                if source:
                    source_id = source.id
                else:
                    return jsonify({'message': f'Aucun {source_type} associé à cet utilisateur'}), 400
            
            # Vérifier que le source_id existe et que l'utilisateur y a accès
            if source_type == 'commercial':
                check_query = text("""
                    SELECT id FROM commerciaux
                    WHERE id = :source_id AND (user_id = :user_id OR :is_admin)
                """)
            else:  # partenaire
                check_query = text("""
                    SELECT id FROM partenaires
                    WHERE id = :source_id AND (user_id = :user_id OR :is_admin)
                """)
            
            source = conn.execute(check_query, {
                "source_id": source_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not source:
                return jsonify({'message': f'{source_type.capitalize()} non trouvé ou non autorisé'}), 403
            
            # Générer un code unique si non fourni
            if not code:
                code = str(uuid.uuid4()).split('-')[0].upper()
            else:
                # Vérifier que le code n'existe pas déjà
                if source_type == 'commercial':
                    check_code_query = text("""
                        SELECT id FROM commerciaux
                        WHERE tracking_code = :code AND id != :source_id
                    """)
                else:  # partenaire
                    check_code_query = text("""
                        SELECT id FROM partenaires
                        WHERE tracking_code = :code AND id != :source_id
                    """)
                
                existing_code = conn.execute(check_code_query, {
                    "code": code,
                    "source_id": source_id
                }).fetchone()
                
                if existing_code:
                    return jsonify({'message': 'Ce code de tracking existe déjà'}), 409
            
            # Mettre à jour le code de tracking
            if source_type == 'commercial':
                update_query = text("""
                    UPDATE commerciaux
                    SET tracking_code = :code
                    WHERE id = :source_id
                    RETURNING id, tracking_code, full_name
                """)
            else:  # partenaire
                update_query = text("""
                    UPDATE partenaires
                    SET tracking_code = :code
                    WHERE id = :source_id
                    RETURNING id, tracking_code, nom as name
                """)
            
            result = conn.execute(update_query, {
                "code": code,
                "source_id": source_id
            })
            
            updated = result.fetchone()
            
            # Commit les changements
            conn.commit()
            
            # Construire l'URL de tracking
            base_url = request.host_url.rstrip('/')
            tracking_url = f"{base_url}/track/{source_type}/{code}"
            
            return jsonify({
                'id': updated.id,
                'code': updated.tracking_code,
                'name': updated.name if hasattr(updated, 'name') else updated.full_name,
                'tracking_url': tracking_url
            })
    except Exception as e:
        logger.error(f"Error creating tracking code: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Route publique pour le tracking
@affiliation_bp.route('/track/<source_type>/<code>', methods=['GET'])
def track_visit(source_type, code):
    """
    Redirection avec tracking d'affiliation - route publique sans authentification
    ---
    tags:
      - Public
    parameters:
      - in: path
        name: source_type
        required: true
        type: string
        enum: [commercial, partenaire]
        description: Type de source d'affiliation
      - in: path
        name: code
        required: true
        type: string
        description: Code de tracking
      - in: query
        name: url
        type: string
        default: /
        description: URL de redirection après le tracking
    responses:
      302:
        description: Redirection vers l'URL spécifiée avec paramètres de tracking ajoutés
      500:
        description: Erreur serveur (redirige quand même vers l'URL spécifiée)
    """
    redirect_url = request.args.get('url', '/')
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return redirect(redirect_url)  # En cas d'erreur, rediriger sans tracking
    
    try:
        with engine.connect() as conn:
            # Enregistrer la visite et rediriger
            # Dans un système réel, on stockerait la visite, les cookies, etc.
            
            # Récupérer l'ID correspondant au code
            if source_type == 'commercial':
                query = text("""
                    SELECT id FROM commerciaux
                    WHERE tracking_code = :code
                """)
            else:  # partenaire
                query = text("""
                    SELECT id FROM partenaires
                    WHERE tracking_code = :code
                """)
            
            result = conn.execute(query, {"code": code}).fetchone()
            
            if result:
                # Stocker l'information dans une table de tracking (à implémenter)
                # ...
                
                # Pour l'exemple, on pourrait ajouter des paramètres à l'URL
                if '?' in redirect_url:
                    redirect_url += f"&ref_type={source_type}&ref_code={code}"
                else:
                    redirect_url += f"?ref_type={source_type}&ref_code={code}"
            
            return redirect(redirect_url)
    except Exception as e:
        logger.error(f"Error tracking visit: {str(e)}")
        return redirect(redirect_url)  # En cas d'erreur, rediriger sans tracking