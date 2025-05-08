import logging
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from functools import wraps

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes d'avis
review_bp = Blueprint('review', __name__, url_prefix='/avis')

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

# Endpoint pour lister tous les avis (de ou pour un utilisateur)
@review_bp.route('/freelance', methods=['GET'])
def get_freelance_reviews():
    """
    Liste tous les avis pour des freelances, avec options de filtrage
    ---
    tags:
      - Avis
    parameters:
      - in: query
        name: freelance_id
        type: integer
        description: Filtrer par ID du freelance évalué
      - in: query
        name: client_id
        type: integer
        description: Filtrer par ID du client qui a donné l'avis
      - in: query
        name: visible_only
        type: boolean
        default: true
        description: Si true, retourne uniquement les avis visibles/publiés
      - in: query
        name: min_note
        type: integer
        minimum: 1
        maximum: 5
        default: 1
        description: Note minimale (1-5)
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
        description: Liste des avis
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID de l'avis
              user_id:
                type: integer
                description: ID du freelance évalué
              freelance_name:
                type: string
                description: Nom du freelance évalué
              client_id:
                type: integer
                description: ID du client qui a donné l'avis
              client_name:
                type: string
                description: Nom du client qui a donné l'avis
              note:
                type: integer
                description: Note (1-5)
              commentaire:
                type: string
                description: Commentaire textuel
              date_creation:
                type: string
                format: date-time
                description: Date de création de l'avis
              date_publication:
                type: string
                format: date-time
                description: Date de publication de l'avis (si modéré)
              visible:
                type: boolean
                description: Si l'avis est visible/publié
              reponse:
                type: string
                description: Réponse du freelance à l'avis (optionnel)
              date_reponse:
                type: string
                format: date-time
                description: Date de la réponse (si applicable)
      500:
        description: Erreur serveur
    """
    # Récupérer les filtres de la requête
    freelance_id = request.args.get('freelance_id')
    client_id = request.args.get('client_id')
    visible_only = request.args.get('visible_only', 'true').lower() == 'true'
    min_note = request.args.get('min_note', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT a.*, u.full_name as freelance_name, c.full_name as client_name",
                "FROM avis_freelance a",
                "LEFT JOIN users u ON a.user_id = u.id",
                "LEFT JOIN clients c ON a.client_id = c.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Ajouter les filtres
            if visible_only:
                query_parts.append("AND a.visible = TRUE")
                
            if freelance_id:
                query_parts.append("AND a.user_id = :freelance_id")
                params["freelance_id"] = int(freelance_id)
                
            if client_id:
                query_parts.append("AND a.client_id = :client_id")
                params["client_id"] = int(client_id)
                
            if min_note:
                query_parts.append("AND a.note >= :min_note")
                params["min_note"] = min_note
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY a.date DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            reviews = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for review in reviews:
                review_dict = {column: getattr(review, column) for column in review._mapping.keys()}
                result.append(review_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting reviews: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour lister les avis sur la plateforme
@review_bp.route('/plateforme', methods=['GET'])
def get_platform_reviews():
    """
    Liste tous les avis sur la plateforme, avec options de filtrage
    ---
    tags:
      - Avis
    parameters:
      - in: query
        name: role
        type: string
        enum: [freelance, client]
        description: Filtrer par rôle de l'auteur (freelance ou client)
      - in: query
        name: visible_only
        type: boolean
        default: true
        description: Si true, retourne uniquement les avis visibles/publiés
      - in: query
        name: min_note
        type: integer
        minimum: 1
        maximum: 5
        default: 1
        description: Note minimale (1-5)
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
        description: Liste des avis sur la plateforme
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID de l'avis
              auteur_id:
                type: integer
                description: ID de l'auteur de l'avis
              auteur_role:
                type: string
                enum: [freelance, client]
                description: Rôle de l'auteur (freelance ou client)
              note:
                type: integer
                description: Note (1-5)
              commentaire:
                type: string
                description: Commentaire textuel
              date:
                type: string
                format: date-time
                description: Date de création de l'avis
              date_publication:
                type: string
                format: date-time
                description: Date de publication de l'avis (si modéré)
              visible:
                type: boolean
                description: Si l'avis est visible/publié
              reponse_admin:
                type: string
                description: Réponse de l'administration (optionnel)
              date_reponse:
                type: string
                format: date-time
                description: Date de la réponse admin (si applicable)
      500:
        description: Erreur serveur
    """
    # Récupérer les filtres de la requête
    role = request.args.get('role')  # Filtrer par rôle de l'auteur
    min_note = request.args.get('min_note', 1, type=int)
    visible_only = request.args.get('visible_only', 'true').lower() == 'true'
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT a.*",
                "FROM avis_plateforme a",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Ajouter les filtres
            if visible_only:
                query_parts.append("AND a.visible = TRUE")
                
            if role:
                query_parts.append("AND a.auteur_role = :role")
                params["role"] = role
                
            if min_note:
                query_parts.append("AND a.note >= :min_note")
                params["min_note"] = min_note
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY a.date DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            reviews = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for review in reviews:
                review_dict = {column: getattr(review, column) for column in review._mapping.keys()}
                result.append(review_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting platform reviews: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer un avis sur un freelance
@review_bp.route('/freelance', methods=['POST'])
@token_required
def create_freelance_review():
    """
    Crée un nouvel avis pour un freelance
    ---
    tags:
      - Avis
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - freelance_id
            - note
            - vente_id
          properties:
            freelance_id:
              type: integer
              description: ID du freelance à évaluer
            note:
              type: integer
              minimum: 1
              maximum: 5
              description: Note de l'avis (1-5)
            vente_id:
              type: integer
              description: ID de la vente liée à cet avis
            commentaire:
              type: string
              description: Commentaire détaillé (optionnel)
            visible:
              type: boolean
              default: true
              description: Si l'avis doit être immédiatement visible
    responses:
      201:
        description: Avis créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de l'avis créé
            message:
              type: string
              description: Message de confirmation
      400:
        description: Données invalides (ex. note hors limites)
      401:
        description: Non authentifié
      403:
        description: Non autorisé à laisser un avis
      404:
        description: Vente non trouvée
      409:
        description: Un avis existe déjà pour cette vente
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['freelance_id', 'note', 'vente_id']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    freelance_id = data['freelance_id']
    note = data['note']
    vente_id = data['vente_id']
    commentaire = data.get('commentaire', '')
    visible = data.get('visible', True)
    
    # Valider la note (entre 1 et 5)
    if not 1 <= note <= 5:
        return jsonify({'message': 'La note doit être comprise entre 1 et 5'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier que la vente existe et est liée au client
            sale_query = text("""
                SELECT v.id, v.client_id, v.user_id, c.id as client_id_from_user
                FROM ventes v
                LEFT JOIN clients c ON c.created_by_user = :user_id AND c.id = v.client_id
                WHERE v.id = :vente_id
            """)
            
            sale = conn.execute(sale_query, {
                "vente_id": vente_id,
                "user_id": user_id
            }).fetchone()
            
            if not sale:
                return jsonify({'message': 'Vente non trouvée'}), 404
            
            # Si l'utilisateur n'est pas admin et n'est pas associé au client
            user_role_query = text("SELECT role FROM users WHERE id = :user_id")
            user_role = conn.execute(user_role_query, {"user_id": user_id}).fetchone()
            is_admin = user_role and user_role.role == 'admin'
            
            client_id = None
            if not is_admin:
                if sale.client_id_from_user is None and sale.client_id:
                    # L'utilisateur n'est pas le créateur du client
                    return jsonify({'message': 'Non autorisé à laisser un avis pour cette vente'}), 403
                client_id = sale.client_id
            else:
                client_id = sale.client_id
            
            # Vérifier que le freelance correspond à celui de la vente
            if sale.user_id != freelance_id:
                return jsonify({'message': 'Le freelance spécifié ne correspond pas à celui de la vente'}), 400
            
            # Vérifier qu'un avis n'existe pas déjà pour cette vente
            check_query = text("""
                SELECT id FROM avis_freelance
                WHERE vente_id = :vente_id
            """)
            
            existing_review = conn.execute(check_query, {"vente_id": vente_id}).fetchone()
            if existing_review:
                return jsonify({'message': 'Un avis existe déjà pour cette vente'}), 409
            
            # Insérer l'avis
            insert_query = text("""
                INSERT INTO avis_freelance (
                    user_id, client_id, vente_id, note,
                    commentaire, date, visible
                )
                VALUES (
                    :freelance_id, :client_id, :vente_id, :note,
                    :commentaire, NOW(), :visible
                )
                RETURNING id
            """)
            
            result = conn.execute(insert_query, {
                "freelance_id": freelance_id,
                "client_id": client_id,
                "vente_id": vente_id,
                "note": note,
                "commentaire": commentaire,
                "visible": visible
            })
            
            review_id = result.fetchone()[0]
            
            # Mettre à jour la note moyenne du freelance
            update_rating_query = text("""
                UPDATE users
                SET rating = (
                    SELECT AVG(note)
                    FROM avis_freelance
                    WHERE user_id = :freelance_id AND visible = TRUE
                )
                WHERE id = :freelance_id
            """)
            
            conn.execute(update_rating_query, {"freelance_id": freelance_id})
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'id': review_id,
                'message': 'Avis créé avec succès'
            }), 201
    except Exception as e:
        logger.error(f"Error creating review: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer un avis sur la plateforme
@review_bp.route('/plateforme', methods=['POST'])
@token_required
def create_platform_review():
    """
    Crée un nouvel avis sur la plateforme
    ---
    tags:
      - Avis
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - note
            - commentaire
          properties:
            note:
              type: integer
              minimum: 1
              maximum: 5
              description: Note de l'avis (1-5)
            commentaire:
              type: string
              description: Commentaire détaillé
            experience_type:
              type: string
              enum: [general, support, paiement, fonctionnalites]
              default: general
              description: Type d'expérience évaluée
            visible:
              type: boolean
              default: true
              description: Si l'avis doit être immédiatement visible
            version_plateforme:
              type: string
              default: "1.0"
              description: Version de la plateforme concernée par l'avis
    responses:
      201:
        description: Avis sur la plateforme créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de l'avis créé
            message:
              type: string
              description: Message de confirmation
      400:
        description: Données invalides (ex. note hors limites)
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['note', 'commentaire']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    note = data['note']
    commentaire = data['commentaire']
    experience_type = data.get('experience_type', 'general')
    visible = data.get('visible', True)
    
    # Valider la note (entre 1 et 5)
    if not 1 <= note <= 5:
        return jsonify({'message': 'La note doit être comprise entre 1 et 5'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'Utilisateur non trouvé'}), 404
            
            user_role = role_result.role
            
            # Insérer l'avis
            insert_query = text("""
                INSERT INTO avis_plateforme (
                    auteur_id, auteur_role, note, commentaire,
                    date, visible, version_plateforme, experience_type
                )
                VALUES (
                    :auteur_id, :auteur_role, :note, :commentaire,
                    NOW(), :visible, :version_plateforme, :experience_type
                )
                RETURNING id
            """)
            
            result = conn.execute(insert_query, {
                "auteur_id": user_id,
                "auteur_role": user_role,
                "note": note,
                "commentaire": commentaire,
                "visible": visible,
                "version_plateforme": data.get('version_plateforme', '1.0'),
                "experience_type": experience_type
            })
            
            review_id = result.fetchone()[0]
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'id': review_id,
                'message': 'Avis sur la plateforme créé avec succès'
            }), 201
    except Exception as e:
        logger.error(f"Error creating platform review: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour modérer un avis (admin uniquement)
@review_bp.route('/<int:review_id>/moderate', methods=['PUT'])
@token_required
def moderate_review(review_id):
    """
    Modère un avis (change sa visibilité) - réservé aux administrateurs
    ---
    tags:
      - Avis
    security:
      - Bearer: []
    parameters:
      - in: path
        name: review_id
        required: true
        type: integer
        description: ID de l'avis à modérer
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - visible
          properties:
            visible:
              type: boolean
              description: Nouveau statut de visibilité
            type:
              type: string
              enum: [freelance, plateforme]
              default: freelance
              description: Type d'avis (freelance ou plateforme)
    responses:
      200:
        description: Visibilité modifiée avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de confirmation
            visible:
              type: boolean
              description: Nouveau statut de visibilité
      400:
        description: Données invalides
      401:
        description: Non authentifié
      403:
        description: Non autorisé (réservé aux administrateurs)
      404:
        description: Avis non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    if 'visible' not in data:
        return jsonify({'message': 'Le champ visible est requis'}), 400
    
    visible = data['visible']
    review_type = data.get('type', 'freelance')  # 'freelance' ou 'plateforme'
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier que l'utilisateur est admin
            role_query = text("SELECT role FROM users WHERE id = :user_id")
            role_result = conn.execute(role_query, {"user_id": user_id}).fetchone()
            
            if not role_result or role_result.role != 'admin':
                return jsonify({'message': 'Seul un administrateur peut modérer les avis'}), 403
            
            # Déterminer la table en fonction du type d'avis
            table_name = "avis_freelance" if review_type == 'freelance' else "avis_plateforme"
            
            # Mettre à jour la visibilité
            update_query = text(f"""
                UPDATE {table_name}
                SET visible = :visible
                WHERE id = :review_id
                RETURNING id, user_id
            """)
            
            result = conn.execute(update_query, {
                "visible": visible,
                "review_id": review_id
            })
            
            updated_review = result.fetchone()
            
            if not updated_review:
                return jsonify({'message': 'Avis non trouvé'}), 404
            
            # Si c'est un avis de freelance, mettre à jour sa note moyenne
            if review_type == 'freelance' and updated_review.user_id:
                update_rating_query = text("""
                    UPDATE users
                    SET rating = (
                        SELECT AVG(note)
                        FROM avis_freelance
                        WHERE user_id = :freelance_id AND visible = TRUE
                    )
                    WHERE id = :freelance_id
                """)
                
                conn.execute(update_rating_query, {"freelance_id": updated_review.user_id})
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'message': 'Statut de visibilité mis à jour avec succès',
                'visible': visible
            })
    except Exception as e:
        logger.error(f"Error moderating review: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500