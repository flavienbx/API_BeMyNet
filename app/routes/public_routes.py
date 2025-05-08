import logging
from flask import Blueprint, jsonify, current_app, request
from sqlalchemy import text

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes publiques
public_bp = Blueprint('public', __name__, url_prefix='/public')

@public_bp.route('/freelances', methods=['GET'])
def list_freelances():
    """
    Liste tous les freelances avec leur profile public
    ---
    tags:
      - Public
    parameters:
      - in: query
        name: category
        type: string
        description: Catégorie de services
      - in: query
        name: experience
        type: string
        description: Type d'expérience
      - in: query
        name: rating_min
        type: number
        description: Note minimale (1-5)
      - in: query
        name: limit
        type: integer
        default: 50
        description: Nombre maximum de résultats
      - in: query
        name: offset
        type: integer
        default: 0
        description: Décalage pour pagination
    responses:
      200:
        description: Liste des freelances publics
      500:
        description: Erreur serveur
    """
    # Récupérer les filtres de la requête
    category = request.args.get('category')
    experience = request.args.get('experience')
    rating_min = request.args.get('rating_min', type=float)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT u.id, u.full_name, u.bio, u.experience_type, u.rating,",
                "u.portfolio_url, u.website, u.city, u.country,",
                "(SELECT COUNT(*) FROM avis_freelance a WHERE a.user_id = u.id AND a.visible = TRUE) as review_count",
                "FROM users u",
                "WHERE u.role = 'freelance' AND u.account_status = 'active'"
            ]
            
            params = {}
            
            # Ajouter les filtres
            if category:
                query_parts.append("AND u.experience_type = :category")
                params["category"] = category
                
            if experience:
                query_parts.append("AND u.experience = :experience")
                params["experience"] = experience
                
            if rating_min:
                query_parts.append("AND (u.rating >= :rating_min OR u.rating IS NULL)")
                params["rating_min"] = rating_min
            
            # Ajouter l'ordre et la pagination (MySQL n'a pas NULLS LAST)
            query_parts.append("ORDER BY u.rating IS NULL, u.rating DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            freelances = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for freelance in freelances:
                freelance_dict = {column: getattr(freelance, column) for column in freelance._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                if freelance_dict.get('rating'):
                    freelance_dict['rating'] = float(freelance_dict['rating'])
                
                result.append(freelance_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error listing freelances: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@public_bp.route('/freelances/<int:freelance_id>', methods=['GET'])
def get_freelance_profile(freelance_id):
    """
    Récupère le profil public d'un freelance
    ---
    tags:
      - Public
    parameters:
      - in: path
        name: freelance_id
        type: integer
        required: true
        description: ID du freelance
    responses:
      200:
        description: Profil du freelance avec ses avis et produits
      404:
        description: Freelance non trouvé
      500:
        description: Erreur serveur
    """
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer les informations du freelance
            profile_query = text("""
                SELECT 
                    u.id, u.full_name, u.bio, u.experience_type, u.rating,
                    u.portfolio_url, u.website, u.city, u.country,
                    (SELECT COUNT(*) FROM avis_freelance a WHERE a.user_id = u.id AND a.visible = TRUE) as review_count
                FROM users u
                WHERE u.id = :freelance_id AND u.role = 'freelance' AND u.account_status = 'active'
            """)
            
            freelance = conn.execute(profile_query, {"freelance_id": freelance_id}).fetchone()
            
            if not freelance:
                return jsonify({'message': 'Freelance non trouvé ou non actif'}), 404
            
            # Convertir en dictionnaire
            profile = {column: getattr(freelance, column) for column in freelance._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if profile.get('rating'):
                profile['rating'] = float(profile['rating'])
            
            # Récupérer les avis du freelance
            reviews_query = text("""
                SELECT 
                    a.id, a.note, a.commentaire, a.date,
                    c.full_name as client_name
                FROM avis_freelance a
                LEFT JOIN clients c ON a.client_id = c.id
                WHERE a.user_id = :freelance_id AND a.visible = TRUE
                ORDER BY a.date DESC
                LIMIT 10
            """)
            
            reviews = conn.execute(reviews_query, {"freelance_id": freelance_id}).fetchall()
            
            profile['reviews'] = [{
                'id': review.id,
                'note': review.note,
                'commentaire': review.commentaire,
                'date': review.date.isoformat() if review.date else None,
                'client_name': review.client_name
            } for review in reviews]
            
            # Récupérer les produits du freelance
            products_query = text("""
                SELECT 
                    p.id, p.nom, p.description, p.prix, p.type,
                    p.delivery_time_days, p.category, p.is_customizable
                FROM produits p
                WHERE p.user_id = :freelance_id AND p.actif = TRUE
                ORDER BY p.prix ASC
                LIMIT 10
            """)
            
            products = conn.execute(products_query, {"freelance_id": freelance_id}).fetchall()
            
            profile['products'] = [{
                'id': product.id,
                'nom': product.nom,
                'description': product.description,
                'prix': float(product.prix) if product.prix else 0,
                'type': product.type,
                'delivery_time_days': product.delivery_time_days,
                'category': product.category,
                'is_customizable': product.is_customizable
            } for product in products]
            
            return jsonify(profile)
    except Exception as e:
        logger.error(f"Error getting freelance profile: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@public_bp.route('/portfolio/<int:freelance_id>', methods=['GET'])
def get_freelance_portfolio(freelance_id):
    """
    Récupère le portfolio d'un freelance
    ---
    tags:
      - Public
    parameters:
      - in: path
        name: freelance_id
        type: integer
        required: true
        description: ID du freelance
    responses:
      200:
        description: Portfolio du freelance avec ses projets et meilleurs avis
      404:
        description: Freelance non trouvé
      500:
        description: Erreur serveur
    """
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer les informations de base du freelance
            freelance_query = text("""
                SELECT 
                    u.id, u.full_name, u.bio, u.portfolio_url, u.website,
                    u.rating, u.experience_type
                FROM users u
                WHERE u.id = :freelance_id AND u.role = 'freelance' AND u.account_status = 'active'
            """)
            
            freelance = conn.execute(freelance_query, {"freelance_id": freelance_id}).fetchone()
            
            if not freelance:
                return jsonify({'message': 'Freelance non trouvé ou non actif'}), 404
            
            # Convertir en dictionnaire
            portfolio = {column: getattr(freelance, column) for column in freelance._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if portfolio.get('rating'):
                portfolio['rating'] = float(portfolio['rating'])
            
            # Récupérer les projets réalisés (ventes complétées)
            projects_query = text("""
                SELECT 
                    v.id, v.description, v.date, v.montant,
                    p.nom as product_name, p.type as product_type
                FROM ventes v
                LEFT JOIN produits p ON v.produit_id = p.id
                WHERE v.user_id = :freelance_id AND v.statut_paiement = 'payé'
                ORDER BY v.date DESC
                LIMIT 10
            """)
            
            projects = conn.execute(projects_query, {"freelance_id": freelance_id}).fetchall()
            
            portfolio['projects'] = [{
                'id': project.id,
                'description': project.description,
                'date': project.date.isoformat() if project.date else None,
                'montant': float(project.montant) if project.montant else 0,
                'product_name': project.product_name,
                'product_type': project.product_type
            } for project in projects]
            
            # Récupérer les meilleurs avis
            reviews_query = text("""
                SELECT 
                    a.id, a.note, a.commentaire, a.date,
                    c.full_name as client_name
                FROM avis_freelance a
                LEFT JOIN clients c ON a.client_id = c.id
                WHERE a.user_id = :freelance_id AND a.visible = TRUE
                ORDER BY a.note DESC, a.date DESC
                LIMIT 5
            """)
            
            reviews = conn.execute(reviews_query, {"freelance_id": freelance_id}).fetchall()
            
            portfolio['best_reviews'] = [{
                'id': review.id,
                'note': review.note,
                'commentaire': review.commentaire,
                'date': review.date.isoformat() if review.date else None,
                'client_name': review.client_name
            } for review in reviews]
            
            return jsonify(portfolio)
    except Exception as e:
        logger.error(f"Error getting freelance portfolio: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@public_bp.route('/produits', methods=['GET'])
def list_products():
    """
    Liste les produits disponibles dans le catalogue public
    ---
    tags:
      - Public
    parameters:
      - in: query
        name: category
        type: string
        description: Catégorie du produit
      - in: query
        name: type
        type: string
        description: Type de produit
      - in: query
        name: min_price
        type: number
        description: Prix minimum
      - in: query
        name: max_price
        type: number
        description: Prix maximum
      - in: query
        name: limit
        type: integer
        default: 50
        description: Nombre maximum de résultats
      - in: query
        name: offset
        type: integer
        default: 0
        description: Décalage pour pagination
    responses:
      200:
        description: Liste des produits disponibles
      500:
        description: Erreur serveur
    """
    # Récupérer les filtres de la requête
    category = request.args.get('category')
    type_produit = request.args.get('type')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT p.*, u.full_name as freelance_name, u.rating as freelance_rating",
                "FROM produits p",
                "LEFT JOIN users u ON p.user_id = u.id",
                "WHERE p.actif = TRUE"
            ]
            
            params = {}
            
            # Ajouter les filtres
            if category:
                query_parts.append("AND p.category = :category")
                params["category"] = category
                
            if type_produit:
                query_parts.append("AND p.type = :type")
                params["type"] = type_produit
                
            if min_price is not None:
                query_parts.append("AND p.prix >= :min_price")
                params["min_price"] = min_price
                
            if max_price is not None:
                query_parts.append("AND p.prix <= :max_price")
                params["max_price"] = max_price
            
            # Limiter aux freelances actifs
            query_parts.append("AND u.account_status = 'active'")
            
            # Ajouter l'ordre et la pagination (MySQL n'a pas NULLS LAST)
            query_parts.append("ORDER BY u.rating IS NULL, u.rating DESC, p.prix ASC")
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
                if product_dict.get('freelance_rating'):
                    product_dict['freelance_rating'] = float(product_dict['freelance_rating'])
                
                result.append(product_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error listing products: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@public_bp.route('/produits/<int:product_id>', methods=['GET'])
def get_product_details(product_id):
    """
    Récupère les détails d'un produit public
    ---
    tags:
      - Public
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID du produit
    responses:
      200:
        description: Détails complets du produit avec informations du freelance
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
            # Récupérer les informations du produit
            product_query = text("""
                SELECT 
                    p.*, u.full_name as freelance_name, u.id as freelance_id,
                    u.rating as freelance_rating, u.bio as freelance_bio
                FROM produits p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = :product_id AND p.actif = TRUE AND u.account_status = 'active'
            """)
            
            product = conn.execute(product_query, {"product_id": product_id}).fetchone()
            
            if not product:
                return jsonify({'message': 'Produit non trouvé ou non actif'}), 404
            
            # Convertir en dictionnaire
            product_dict = {column: getattr(product, column) for column in product._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            if product_dict.get('prix'):
                product_dict['prix'] = float(product_dict['prix'])
            if product_dict.get('freelance_rating'):
                product_dict['freelance_rating'] = float(product_dict['freelance_rating'])
            
            # Récupérer les avis du freelance associé
            reviews_query = text("""
                SELECT 
                    a.id, a.note, a.commentaire, a.date,
                    c.full_name as client_name
                FROM avis_freelance a
                LEFT JOIN clients c ON a.client_id = c.id
                WHERE a.user_id = :freelance_id AND a.visible = TRUE
                ORDER BY a.date DESC
                LIMIT 5
            """)
            
            reviews = conn.execute(reviews_query, {"freelance_id": product.freelance_id}).fetchall()
            
            product_dict['freelance_reviews'] = [{
                'id': review.id,
                'note': review.note,
                'commentaire': review.commentaire,
                'date': review.date.isoformat() if review.date else None,
                'client_name': review.client_name
            } for review in reviews]
            
            # Récupérer d'autres produits du même freelance
            similar_query = text("""
                SELECT 
                    p.id, p.nom, p.description, p.prix, p.type, p.category
                FROM produits p
                WHERE p.user_id = :freelance_id AND p.actif = TRUE AND p.id != :product_id
                ORDER BY p.prix ASC
                LIMIT 4
            """)
            
            similar_products = conn.execute(similar_query, {
                "freelance_id": product.freelance_id,
                "product_id": product_id
            }).fetchall()
            
            product_dict['similar_products'] = [{
                'id': p.id,
                'nom': p.nom,
                'description': p.description,
                'prix': float(p.prix) if p.prix else 0,
                'type': p.type,
                'category': p.category
            } for p in similar_products]
            
            return jsonify(product_dict)
    except Exception as e:
        logger.error(f"Error getting product details: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

@public_bp.route('/avis-plateforme', methods=['GET'])
def get_platform_reviews():
    """
    Récupère les avis publics sur la plateforme
    ---
    tags:
      - Public
    parameters:
      - in: query
        name: limit
        type: integer
        default: 10
        description: Nombre maximum d'avis à retourner
      - in: query
        name: offset
        type: integer
        default: 0
        description: Décalage pour pagination
    responses:
      200:
        description: Liste des avis sur la plateforme avec statistiques
      500:
        description: Erreur serveur
    """
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer les avis sur la plateforme
            query = text("""
                SELECT a.*
                FROM avis_plateforme a
                WHERE a.visible = TRUE
                ORDER BY a.date DESC
                LIMIT :limit OFFSET :offset
            """)
            
            reviews = conn.execute(query, {
                "limit": limit,
                "offset": offset
            }).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for review in reviews:
                review_dict = {column: getattr(review, column) for column in review._mapping.keys()}
                
                # Formater la date
                if review_dict.get('date'):
                    review_dict['date'] = review_dict['date'].isoformat()
                
                result.append(review_dict)
            
            # Calculer les statistiques
            stats_query = text("""
                SELECT 
                    COUNT(*) as total_reviews,
                    AVG(note) as average_rating,
                    SUM(CASE WHEN note >= 4 THEN 1 ELSE 0 END) as positive_reviews
                FROM avis_plateforme
                WHERE visible = TRUE
            """)
            
            stats = conn.execute(stats_query).fetchone()
            
            stats_dict = {
                'total_reviews': stats.total_reviews,
                'average_rating': float(stats.average_rating) if stats.average_rating else 0,
                'positive_percentage': (
                    (stats.positive_reviews / stats.total_reviews) * 100 
                    if stats.total_reviews > 0 else 0
                )
            }
            
            return jsonify({
                'reviews': result,
                'stats': stats_dict
            })
    except Exception as e:
        logger.error(f"Error getting platform reviews: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500