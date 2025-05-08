import logging
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from functools import wraps

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes de produits
product_bp = Blueprint('product', __name__, url_prefix='/produits')

# Middleware d'authentification (identique à celui dans stripe_routes.py)
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

# Endpoint pour lister tous les produits
@product_bp.route('', methods=['GET'])
def get_products():
    """
    Liste tous les produits actifs ou filtrés par catégorie
    ---
    tags:
      - Produits
    parameters:
      - in: query
        name: category
        type: string
        description: Filtrer par catégorie de produit
      - in: query
        name: freelance_id
        type: integer
        description: Filtrer par ID du freelance
      - in: query
        name: actif
        type: string
        enum: [true, false]
        default: true
        description: Inclure uniquement les produits actifs
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
        description: Liste des produits
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID du produit
              nom:
                type: string
                description: Nom du produit
              description:
                type: string
                description: Description du produit
              prix:
                type: number
                format: float
                description: Prix du produit
              type:
                type: string
                description: Type de produit
              delivery_time_days:
                type: integer
                description: Délai de livraison en jours
              is_customizable:
                type: boolean
                description: Indique si le produit est personnalisable
              category:
                type: string
                description: Catégorie du produit
              freelance_id:
                type: integer
                description: ID du freelance
              freelance_name:
                type: string
                description: Nom du freelance
              actif:
                type: boolean
                description: Indique si le produit est actif
      500:
        description: Erreur serveur
    """
    # Récupérer les filtres de la requête
    category = request.args.get('category')
    freelance_id = request.args.get('freelance_id')
    actif_only = request.args.get('actif', 'true').lower() == 'true'
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT p.*, u.full_name as freelance_name",
                "FROM produits p",
                "LEFT JOIN users u ON p.freelance_id = u.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Ajouter les filtres
            if actif_only:
                query_parts.append("AND p.actif = TRUE")
                
            if category:
                query_parts.append("AND p.category = :category")
                params["category"] = category
                
            if freelance_id:
                query_parts.append("AND p.freelance_id = :freelance_id")
                params["freelance_id"] = int(freelance_id)
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY p.id DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            products = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for product in products:
                product_dict = {column: getattr(product, column) for column in product._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                if product_dict.get('prix'):
                    product_dict['prix'] = float(product_dict['prix'])
                
                result.append(product_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting products: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer un produit
@product_bp.route('', methods=['POST'])
@token_required
def create_product():
    """
    Crée un nouveau produit
    ---
    tags:
      - Produits
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - nom
            - prix
            - type
          properties:
            nom:
              type: string
              description: Nom du produit
            description:
              type: string
              description: Description détaillée du produit
            prix:
              type: number
              format: float
              description: Prix du produit
            type:
              type: string
              description: Type de produit (service, physique, etc.)
            delivery_time_days:
              type: integer
              default: 7
              description: Délai de livraison en jours
            is_customizable:
              type: boolean
              default: true
              description: Indique si le produit est personnalisable
            category:
              type: string
              default: other
              description: Catégorie du produit
            actif:
              type: boolean
              default: true
              description: Indique si le produit est visible et disponible
    responses:
      201:
        description: Produit créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du produit créé
            message:
              type: string
              description: Message de confirmation
            nom:
              type: string
              description: Nom du produit
            prix:
              type: number
              format: float
              description: Prix du produit
      400:
        description: Données invalides ou incomplètes
      401:
        description: Non authentifié
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['nom', 'prix', 'type']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Insérer le produit
            insert_query = text("""
                INSERT INTO produits (
                    nom, description, prix, type, delivery_time_days,
                    is_customizable, category, freelance_id, actif, created_at
                )
                VALUES (
                    :nom, :description, :prix, :type, :delivery_time_days,
                    :is_customizable, :category, :freelance_id, :actif, NOW()
                )
                RETURNING id
            """)
            
            params = {
                "nom": data.get('nom'),
                "description": data.get('description', ''),
                "prix": float(data.get('prix')),
                "type": data.get('type'),
                "delivery_time_days": data.get('delivery_time_days', 7),
                "is_customizable": data.get('is_customizable', True),
                "category": data.get('category', 'other'),
                "freelance_id": user_id,
                "actif": data.get('actif', True)
            }
            
            result = conn.execute(insert_query, params)
            product_id = result.fetchone()[0]
            
            # Commit les changements
            conn.commit()
            
            return jsonify({
                'id': product_id,
                'message': 'Produit créé avec succès',
                **params
            }), 201
    except Exception as e:
        logger.error(f"Error creating product: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour récupérer un produit spécifique
@product_bp.route('/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """
    Récupère les détails d'un produit
    ---
    tags:
      - Produits
    parameters:
      - in: path
        name: product_id
        required: true
        type: integer
        description: ID du produit à récupérer
    responses:
      200:
        description: Détails du produit
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du produit
            nom:
              type: string
              description: Nom du produit
            description:
              type: string
              description: Description détaillée du produit
            prix:
              type: number
              format: float
              description: Prix du produit
            type:
              type: string
              description: Type de produit (service, physique, etc.)
            delivery_time_days:
              type: integer
              description: Délai de livraison en jours
            is_customizable:
              type: boolean
              description: Indique si le produit est personnalisable
            category:
              type: string
              description: Catégorie du produit
            freelance_id:
              type: integer
              description: ID du freelance propriétaire
            freelance_name:
              type: string
              description: Nom du freelance propriétaire
            freelance_email:
              type: string
              description: Email du freelance propriétaire
            actif:
              type: boolean
              description: Indique si le produit est visible et disponible
            created_at:
              type: string
              format: date-time
              description: Date de création du produit
      404:
        description: Produit non trouvé
      500:
        description: Erreur serveur
    """
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer le produit
            query = text("""
                SELECT p.*, u.full_name as freelance_name, u.email as freelance_email
                FROM produits p
                LEFT JOIN users u ON p.freelance_id = u.id
                WHERE p.id = :product_id
            """)
            
            product = conn.execute(query, {"product_id": product_id}).fetchone()
            
            if not product:
                return jsonify({'message': 'Produit non trouvé'}), 404
            
            # Convertir en dictionnaire
            product_dict = {column: getattr(product, column) for column in product._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if product_dict.get('prix'):
                product_dict['prix'] = float(product_dict['prix'])
            
            return jsonify(product_dict)
    except Exception as e:
        logger.error(f"Error getting product: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour mettre à jour un produit
@product_bp.route('/<int:product_id>', methods=['PUT'])
@token_required
def update_product(product_id):
    """
    Met à jour un produit existant
    ---
    tags:
      - Produits
    security:
      - Bearer: []
    parameters:
      - in: path
        name: product_id
        required: true
        type: integer
        description: ID du produit à mettre à jour
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            nom:
              type: string
              description: Nom du produit
            description:
              type: string
              description: Description détaillée du produit
            prix:
              type: number
              format: float
              description: Prix du produit
            type:
              type: string
              description: Type de produit (service, physique, etc.)
            delivery_time_days:
              type: integer
              description: Délai de livraison en jours
            is_customizable:
              type: boolean
              description: Indique si le produit est personnalisable
            category:
              type: string
              description: Catégorie du produit
            actif:
              type: boolean
              description: Indique si le produit est visible et disponible
    responses:
      200:
        description: Produit mis à jour avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de confirmation
            id:
              type: integer
              description: ID du produit mis à jour
      400:
        description: Données invalides ou aucun champ à mettre à jour
      401:
        description: Non authentifié
      404:
        description: Produit non trouvé ou non autorisé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier que le produit existe et appartient à l'utilisateur
            check_query = text("""
                SELECT id FROM produits
                WHERE id = :product_id AND (freelance_id = :user_id OR EXISTS (
                    SELECT 1 FROM users WHERE id = :user_id AND role = 'admin'
                ))
            """)
            
            product = conn.execute(check_query, {
                "product_id": product_id,
                "user_id": user_id
            }).fetchone()
            
            if not product:
                return jsonify({'message': 'Produit non trouvé ou non autorisé'}), 404
            
            # Construire la requête de mise à jour
            update_parts = []
            params = {
                "product_id": product_id
            }
            
            # Ajouter chaque champ modifiable
            update_fields = [
                'nom', 'description', 'prix', 'type', 'delivery_time_days',
                'is_customizable', 'category', 'actif'
            ]
            
            for field in update_fields:
                if field in data:
                    update_parts.append(f"{field} = :{field}")
                    params[field] = data[field]
            
            if not update_parts:
                return jsonify({'message': 'Aucun champ à mettre à jour'}), 400
            
            # Exécuter la mise à jour
            update_query = text(f"""
                UPDATE produits
                SET {', '.join(update_parts)}
                WHERE id = :product_id
            """)
            
            conn.execute(update_query, params)
            conn.commit()
            
            return jsonify({
                'message': 'Produit mis à jour avec succès',
                'id': product_id
            })
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer une session de paiement pour un produit
@product_bp.route('/<int:product_id>/payer', methods=['POST'])
@token_required
def pay_product(product_id):
    """
    Crée une session de paiement Stripe pour un produit
    ---
    tags:
      - Produits
    security:
      - Bearer: []
    parameters:
      - in: path
        name: product_id
        required: true
        type: integer
        description: ID du produit à payer
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - client_id
          properties:
            client_id:
              type: integer
              description: ID du client qui effectue l'achat
    responses:
      200:
        description: Session de paiement créée avec succès
        schema:
          type: object
          properties:
            session_id:
              type: string
              description: ID de la session Stripe
            checkout_url:
              type: string
              description: URL de redirection vers Stripe Checkout
      400:
        description: ID client manquant ou produit déjà payé
      401:
        description: Non authentifié
      404:
        description: Produit ou client non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json or {}
    
    # Vérifier si un client_id est fourni
    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'message': 'ID client requis'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer les informations du produit et du freelance
            product_query = text("""
                SELECT p.*, u.id as freelance_id, u.full_name as freelance_name,
                       u.stripe_account_id, u.payout_enabled
                FROM produits p
                JOIN users u ON p.freelance_id = u.id
                WHERE p.id = :product_id AND p.actif = TRUE
            """)
            
            product = conn.execute(product_query, {"product_id": product_id}).fetchone()
            
            if not product:
                return jsonify({'message': 'Produit non trouvé ou inactif'}), 404
            
            # Vérifier que le client existe
            client_query = text("SELECT id, full_name FROM clients WHERE id = :client_id")
            client = conn.execute(client_query, {"client_id": client_id}).fetchone()
            
            if not client:
                return jsonify({'message': 'Client non trouvé'}), 404
            
            # Créer la description du paiement
            description = f"{product.nom} - {product.freelance_name}"
            
            # Déterminer si on peut faire un paiement direct avec Stripe Connect
            freelance_stripe_id = None
            if product.stripe_account_id and product.payout_enabled:
                freelance_stripe_id = product.stripe_account_id
            
            # Créer la session de paiement
            from app.utils.stripe_utils import create_checkout_session
            checkout_session = create_checkout_session(
                client_id=client_id,
                product_id=product_id,
                freelance_id=product.freelance_id,
                montant=float(product.prix),
                description=description,
                freelance_stripe_id=freelance_stripe_id,
                metadata={
                    "product_name": product.nom,
                    "client_name": client.full_name
                }
            )
            
            # Retourner l'URL de paiement
            return jsonify({
                'session_id': checkout_session.id,
                'checkout_url': checkout_session.url
            })
    except Exception as e:
        logger.error(f"Error creating payment session: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500