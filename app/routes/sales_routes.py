import logging
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from functools import wraps
from decimal import Decimal

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes des ventes
sales_bp = Blueprint('sales', __name__, url_prefix='/ventes')

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

# Endpoint pour lister toutes les ventes
@sales_bp.route('', methods=['GET'])
@token_required
def get_sales():
    """
    Liste toutes les ventes de l'utilisateur authentifié ou filtrées par critères
    ---
    tags:
      - Ventes
    security:
      - Bearer: []
    parameters:
      - in: query
        name: client_id
        type: integer
        description: Filtrer par ID du client
      - in: query
        name: product_id
        type: integer
        description: Filtrer par ID du produit
      - in: query
        name: status
        type: string
        enum: [payé, en_attente, remboursé]
        description: Filtrer par statut de paiement
      - in: query
        name: date_start
        type: string
        format: date
        description: Date de début (format YYYY-MM-DD)
      - in: query
        name: date_end
        type: string
        format: date
        description: Date de fin (format YYYY-MM-DD)
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
        description: Liste des ventes
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID de la vente
              user_id:
                type: integer
                description: ID du freelance
              client_id:
                type: integer
                description: ID du client
              client_name:
                type: string
                description: Nom du client
              produit_id:
                type: integer
                description: ID du produit (si applicable)
              product_name:
                type: string
                description: Nom du produit (si applicable)
              montant:
                type: number
                format: float
                description: Montant total de la vente
              discount_applied:
                type: number
                format: float
                description: Réduction appliquée
              description:
                type: string
                description: Description de la vente
              date:
                type: string
                format: date-time
                description: Date de la vente
              source:
                type: string
                description: Source de la vente (manuel, stripe, etc.)
              commission_plateforme:
                type: number
                format: float
                description: Commission pour la plateforme
              commission_commerciale:
                type: number
                format: float
                description: Commission pour le commercial
              commission_partenaire:
                type: number
                format: float
                description: Commission pour le partenaire
              montant_net_freelance:
                type: number
                format: float
                description: Montant net pour le freelance
              commercial_id:
                type: integer
                description: ID du commercial (si applicable)
              partenaire_id:
                type: integer
                description: ID du partenaire (si applicable)
              statut_paiement:
                type: string
                enum: [payé, en_attente, remboursé]
                description: Statut du paiement
      401:
        description: Non authentifié
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    # Récupérer les filtres de la requête
    client_id = request.args.get('client_id')
    product_id = request.args.get('product_id')
    status = request.args.get('status')  # 'payé', 'en_attente', 'remboursé'
    date_start = request.args.get('date_start')
    date_end = request.args.get('date_end')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier le rôle de l'utilisateur
            role_query = text("SELECT role FROM users WHERE id = :id")
            role_result = conn.execute(role_query, {"id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Construire la requête SQL avec les filtres
            query_parts = [
                "SELECT v.*, c.full_name as client_name, p.nom as product_name",
                "FROM ventes v",
                "LEFT JOIN clients c ON v.client_id = c.id",
                "LEFT JOIN produits p ON v.produit_id = p.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Filtrer par utilisateur sauf pour les admins
            if not is_admin:
                query_parts.append("AND v.user_id = :user_id")
                params["user_id"] = user_id
            
            # Ajouter les filtres
            if client_id:
                query_parts.append("AND v.client_id = :client_id")
                params["client_id"] = int(client_id)
                
            if product_id:
                query_parts.append("AND v.produit_id = :product_id")
                params["product_id"] = int(product_id)
                
            if status:
                query_parts.append("AND v.statut_paiement = :status")
                params["status"] = status
                
            if date_start:
                query_parts.append("AND v.date >= :date_start")
                params["date_start"] = date_start
                
            if date_end:
                query_parts.append("AND v.date <= :date_end")
                params["date_end"] = date_end
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY v.date DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            sales = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for sale in sales:
                sale_dict = {column: getattr(sale, column) for column in sale._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                for key in ['montant', 'discount_applied', 'commission_plateforme', 
                           'commission_commerciale', 'commission_partenaire', 'montant_net_freelance']:
                    if sale_dict.get(key):
                        sale_dict[key] = float(sale_dict[key])
                
                result.append(sale_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting sales: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer une vente
@sales_bp.route('', methods=['POST'])
@token_required
def create_sale():
    """
    Crée une nouvelle vente avec calcul des commissions pour chaque partie
    ---
    tags:
      - Ventes
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - client_id
            - montant
            - description
          properties:
            client_id:
              type: integer
              description: ID du client
            montant:
              type: number
              format: float
              description: Montant total de la vente
            description:
              type: string
              description: Description de la vente
            produit_id:
              type: integer
              description: ID du produit (optionnel)
            discount_applied:
              type: number
              format: float
              default: 0
              description: Réduction appliquée
            source:
              type: string
              default: manuel
              description: Source de la vente (manuel, stripe, etc.)
            statut_paiement:
              type: string
              enum: [payé, en_attente, remboursé]
              default: en_attente
              description: Statut du paiement
            commercial_id:
              type: integer
              description: ID du commercial (si applicable)
            partenaire_id:
              type: integer
              description: ID du partenaire (si applicable)
    responses:
      201:
        description: Vente créée avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de la vente créée
            message:
              type: string
              description: Message de confirmation
            commissions:
              type: object
              properties:
                plateforme:
                  type: number
                  format: float
                  description: Commission pour la plateforme
                commerciale:
                  type: number
                  format: float
                  description: Commission pour le commercial
                partenaire:
                  type: number
                  format: float
                  description: Commission pour le partenaire
                freelance:
                  type: number
                  format: float
                  description: Montant net pour le freelance
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
    required_fields = ['client_id', 'montant', 'description']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    client_id = data['client_id']
    montant = float(data['montant'])
    description = data['description']
    produit_id = data.get('produit_id')
    discount_applied = float(data.get('discount_applied', 0))
    source = data.get('source', 'manuel')
    statut_paiement = data.get('statut_paiement', 'en_attente')
    commercial_id = data.get('commercial_id')
    partenaire_id = data.get('partenaire_id')
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Calculer les commissions
            commissions = calculate_commissions(
                conn=conn,
                montant=montant,
                commercial_id=commercial_id,
                partenaire_id=partenaire_id
            )
            
            # Insérer la vente
            insert_query = text("""
                INSERT INTO ventes (
                    user_id, client_id, produit_id, montant, discount_applied,
                    description, date, source, commission_plateforme,
                    commission_commerciale, commission_partenaire, montant_net_freelance,
                    commercial_id, partenaire_id, statut_paiement
                )
                VALUES (
                    :user_id, :client_id, :produit_id, :montant, :discount_applied,
                    :description, NOW(), :source, :commission_plateforme,
                    :commission_commerciale, :commission_partenaire, :montant_net_freelance,
                    :commercial_id, :partenaire_id, :statut_paiement
                )
                RETURNING id
            """)
            
            params = {
                "user_id": user_id,
                "client_id": client_id,
                "produit_id": produit_id,
                "montant": montant,
                "discount_applied": discount_applied,
                "description": description,
                "source": source,
                "commission_plateforme": commissions['plateforme'],
                "commission_commerciale": commissions['commerciale'],
                "commission_partenaire": commissions['partenaire'],
                "montant_net_freelance": commissions['freelance'],
                "commercial_id": commercial_id,
                "partenaire_id": partenaire_id,
                "statut_paiement": statut_paiement
            }
            
            result = conn.execute(insert_query, params)
            sale_id = result.fetchone()[0]
            
            # Si commercial ou partenaire présent, créer les affiliations
            if commercial_id:
                insert_affiliation_query = text("""
                    INSERT INTO affiliations (source_type, source_id, vente_id, commission)
                    VALUES ('commercial', :commercial_id, :vente_id, :commission)
                """)
                
                conn.execute(insert_affiliation_query, {
                    "commercial_id": commercial_id,
                    "vente_id": sale_id,
                    "commission": commissions['commerciale']
                })
            
            if partenaire_id:
                insert_affiliation_query = text("""
                    INSERT INTO affiliations (source_type, source_id, vente_id, commission)
                    VALUES ('partenaire', :partenaire_id, :vente_id, :commission)
                """)
                
                conn.execute(insert_affiliation_query, {
                    "partenaire_id": partenaire_id,
                    "vente_id": sale_id,
                    "commission": commissions['partenaire']
                })
            
            # Commit les changements
            conn.commit()
            
            # Retourner l'ID de la vente créée avec les commissions
            return jsonify({
                'id': sale_id,
                'message': 'Vente créée avec succès',
                'commissions': commissions
            }), 201
    except Exception as e:
        logger.error(f"Error creating sale: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour récupérer une vente spécifique
@sales_bp.route('/<int:sale_id>', methods=['GET'])
@token_required
def get_sale(sale_id):
    """
    Récupère les détails d'une vente
    ---
    tags:
      - Ventes
    security:
      - Bearer: []
    parameters:
      - in: path
        name: sale_id
        required: true
        type: integer
        description: ID de la vente à récupérer
    responses:
      200:
        description: Détails de la vente
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID de la vente
            user_id:
              type: integer
              description: ID du freelance
            client_id:
              type: integer
              description: ID du client
            client_name:
              type: string
              description: Nom du client
            client_email:
              type: string
              description: Email du client
            produit_id:
              type: integer
              description: ID du produit (si applicable)
            product_name:
              type: string
              description: Nom du produit (si applicable)
            montant:
              type: number
              format: float
              description: Montant total de la vente
            discount_applied:
              type: number
              format: float
              description: Réduction appliquée
            description:
              type: string
              description: Description de la vente
            date:
              type: string
              format: date-time
              description: Date de la vente
            source:
              type: string
              description: Source de la vente (manuel, stripe, etc.)
            commission_plateforme:
              type: number
              format: float
              description: Commission pour la plateforme
            commission_commerciale:
              type: number
              format: float
              description: Commission pour le commercial
            commission_partenaire:
              type: number
              format: float
              description: Commission pour le partenaire
            montant_net_freelance:
              type: number
              format: float
              description: Montant net pour le freelance
            commercial_id:
              type: integer
              description: ID du commercial (si applicable)
            commercial_name:
              type: string
              description: Nom du commercial (si applicable)
            partenaire_id:
              type: integer
              description: ID du partenaire (si applicable)
            partenaire_nom:
              type: string
              description: Nom du partenaire (si applicable)
            statut_paiement:
              type: string
              enum: [payé, en_attente, remboursé]
              description: Statut du paiement
            freelance_name:
              type: string
              description: Nom du freelance
            freelance_email:
              type: string
              description: Email du freelance
            affiliations:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    description: ID de l'affiliation
                  source_type:
                    type: string
                    enum: [commercial, partenaire]
                    description: Type de source d'affiliation
                  source_id:
                    type: integer
                    description: ID de la source d'affiliation
                  source_name:
                    type: string
                    description: Nom de la source d'affiliation
                  vente_id:
                    type: integer
                    description: ID de la vente
                  commission:
                    type: number
                    format: float
                    description: Montant de la commission
      401:
        description: Non authentifié
      404:
        description: Vente non trouvée ou non autorisée
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
            role_query = text("SELECT role FROM users WHERE id = :id")
            role_result = conn.execute(role_query, {"id": user_id}).fetchone()
            
            if not role_result:
                return jsonify({'message': 'User not found'}), 404
            
            is_admin = role_result.role == 'admin'
            
            # Récupérer la vente
            sale_query = text("""
                SELECT v.*, 
                       c.full_name as client_name, c.email as client_email,
                       p.nom as product_name,
                       u.full_name as freelance_name, u.email as freelance_email,
                       comm.full_name as commercial_name,
                       part.nom as partenaire_nom
                FROM ventes v
                LEFT JOIN clients c ON v.client_id = c.id
                LEFT JOIN produits p ON v.produit_id = p.id
                LEFT JOIN users u ON v.user_id = u.id
                LEFT JOIN commerciaux comm ON v.commercial_id = comm.id
                LEFT JOIN partenaires part ON v.partenaire_id = part.id
                WHERE v.id = :sale_id AND (v.user_id = :user_id OR :is_admin)
            """)
            
            sale = conn.execute(sale_query, {
                "sale_id": sale_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not sale:
                return jsonify({'message': 'Vente non trouvée ou non autorisée'}), 404
            
            # Convertir en dictionnaire
            sale_dict = {column: getattr(sale, column) for column in sale._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            for key in ['montant', 'discount_applied', 'commission_plateforme', 
                       'commission_commerciale', 'commission_partenaire', 'montant_net_freelance']:
                if sale_dict.get(key):
                    sale_dict[key] = float(sale_dict[key])
            
            # Récupérer les affiliations liées à la vente
            affiliations_query = text("""
                SELECT a.*, 
                       CASE 
                         WHEN a.source_type = 'commercial' THEN comm.full_name
                         WHEN a.source_type = 'partenaire' THEN part.nom
                         ELSE NULL
                       END as source_name
                FROM affiliations a
                LEFT JOIN commerciaux comm ON a.source_type = 'commercial' AND a.source_id = comm.id
                LEFT JOIN partenaires part ON a.source_type = 'partenaire' AND a.source_id = part.id
                WHERE a.vente_id = :sale_id
            """)
            
            affiliations = conn.execute(affiliations_query, {"sale_id": sale_id}).fetchall()
            
            # Convertir les affiliations en liste de dictionnaires
            affiliations_list = []
            for affiliation in affiliations:
                aff_dict = {column: getattr(affiliation, column) for column in affiliation._mapping.keys()}
                
                # Conversion des valeurs décimales
                if aff_dict.get('commission'):
                    aff_dict['commission'] = float(aff_dict['commission'])
                
                affiliations_list.append(aff_dict)
            
            # Ajouter les affiliations à la vente
            sale_dict['affiliations'] = affiliations_list
            
            return jsonify(sale_dict)
    except Exception as e:
        logger.error(f"Error getting sale details: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Fonctions utilitaires
def calculate_commissions(conn, montant, commercial_id=None, partenaire_id=None):
    """
    Calcule les commissions pour chaque partie en fonction des configurations
    
    Args:
        conn: Connexion à la base de données
        montant: Montant total de la vente
        commercial_id: ID du commercial (optionnel)
        partenaire_id: ID du partenaire (optionnel)
        
    Returns:
        dict: Commissions pour chaque partie (plateforme, commerciale, partenaire, freelance)
    """
    # Taux de commission par défaut
    plateforme_rate = Decimal('0.15')  # 15% par défaut pour la plateforme seule
    commerciale_rate = Decimal('0.05')  # 5% par défaut pour un commercial
    partenaire_rate = Decimal('0.02')  # 2% par défaut pour un partenaire
    
    # Si commercial et partenaire sont présents, ajustement des taux
    if commercial_id and partenaire_id:
        plateforme_rate = Decimal('0.08')  # 8% pour la plateforme
    # Si seulement commercial est présent
    elif commercial_id:
        plateforme_rate = Decimal('0.10')  # 10% pour la plateforme
    # Si seulement partenaire est présent
    elif partenaire_id:
        plateforme_rate = Decimal('0.13')  # 13% pour la plateforme
    
    # Récupérer les taux personnalisés du commercial ou partenaire si présent
    if commercial_id:
        commercial_query = text("SELECT pourcentage FROM commerciaux WHERE id = :commercial_id")
        commercial = conn.execute(commercial_query, {"commercial_id": commercial_id}).fetchone()
        
        if commercial and commercial.pourcentage:
            commerciale_rate = Decimal(str(commercial.pourcentage)) / 100
    
    if partenaire_id:
        partenaire_query = text("SELECT pourcentage FROM partenaires WHERE id = :partenaire_id")
        partenaire = conn.execute(partenaire_query, {"partenaire_id": partenaire_id}).fetchone()
        
        if partenaire and partenaire.pourcentage:
            partenaire_rate = Decimal(str(partenaire.pourcentage)) / 100
    
    # Calculer les montants
    montant_decimal = Decimal(str(montant))
    commission_plateforme = montant_decimal * plateforme_rate
    commission_commerciale = montant_decimal * commerciale_rate if commercial_id else Decimal('0')
    commission_partenaire = montant_decimal * partenaire_rate if partenaire_id else Decimal('0')
    
    # Le reste va au freelance
    montant_net_freelance = montant_decimal - commission_plateforme - commission_commerciale - commission_partenaire
    
    return {
        'plateforme': float(commission_plateforme.quantize(Decimal('0.01'))),
        'commerciale': float(commission_commerciale.quantize(Decimal('0.01'))),
        'partenaire': float(commission_partenaire.quantize(Decimal('0.01'))),
        'freelance': float(montant_net_freelance.quantize(Decimal('0.01')))
    }