import os
import logging
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, send_file, current_app
from sqlalchemy import text
from functools import wraps
import tempfile
import uuid

from app.utils.stripe_utils import create_checkout_session

# Configurer le logging
logger = logging.getLogger(__name__)

# Créer le blueprint pour les routes des devis et factures
invoice_bp = Blueprint('invoice', __name__, url_prefix='/devis')

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

# Endpoint pour lister tous les devis/factures
@invoice_bp.route('', methods=['GET'])
@token_required
def get_invoices():
    """
    Liste tous les devis et factures de l'utilisateur authentifié ou filtrés par type
    ---
    tags:
      - Factures
    security:
      - Bearer: []
    parameters:
      - in: query
        name: type
        type: string
        enum: [devis, facture]
        description: Filtrer par type de document
      - in: query
        name: status
        type: string
        enum: [en_attente, envoyé, payé, annulé]
        description: Filtrer par statut du document
      - in: query
        name: client_id
        type: integer
        description: Filtrer par ID du client
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
        description: Liste des devis et factures
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID du document
              type:
                type: string
                enum: [devis, facture]
                description: Type de document
              status:
                type: string
                enum: [en_attente, envoyé, payé, annulé]
                description: Statut du document
              date:
                type: string
                format: date-time
                description: Date de création
              due_date:
                type: string
                format: date-time
                description: Date d'échéance
              total_ht:
                type: number
                format: float
                description: Montant total HT
              total_tva:
                type: number
                format: float
                description: Montant total de TVA
              total_ttc:
                type: number
                format: float
                description: Montant total TTC
              client_name:
                type: string
                description: Nom du client
              client_email:
                type: string
                description: Email du client
      401:
        description: Non authentifié
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    # Récupérer les filtres de la requête
    type_doc = request.args.get('type')  # 'devis' ou 'facture'
    status = request.args.get('status')  # 'en_attente', 'envoyé', 'payé', 'annulé'
    client_id = request.args.get('client_id')
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
                "SELECT df.*, c.full_name as client_name, c.email as client_email",
                "FROM devis_factures df",
                "LEFT JOIN clients c ON df.client_id = c.id",
                "WHERE 1=1"
            ]
            
            params = {}
            
            # Filtrer par utilisateur sauf pour les admins
            if not is_admin:
                query_parts.append("AND df.user_id = :user_id")
                params["user_id"] = user_id
            
            # Ajouter les filtres
            if type_doc:
                query_parts.append("AND df.type = :type")
                params["type"] = type_doc
                
            if status:
                query_parts.append("AND df.status = :status")
                params["status"] = status
                
            if client_id:
                query_parts.append("AND df.client_id = :client_id")
                params["client_id"] = int(client_id)
            
            # Ajouter l'ordre et la pagination
            query_parts.append("ORDER BY df.date DESC")
            query_parts.append("LIMIT :limit OFFSET :offset")
            params["limit"] = limit
            params["offset"] = offset
            
            # Exécuter la requête
            query = text(" ".join(query_parts))
            invoices = conn.execute(query, params).fetchall()
            
            # Convertir les résultats en liste de dictionnaires
            result = []
            for invoice in invoices:
                invoice_dict = {column: getattr(invoice, column) for column in invoice._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                for key in ['total_ht', 'total_tva', 'total_ttc']:
                    if invoice_dict.get(key):
                        invoice_dict[key] = float(invoice_dict[key])
                
                result.append(invoice_dict)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting invoices: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer un devis/facture
@invoice_bp.route('', methods=['POST'])
@token_required
def create_invoice():
    """
    Crée un nouveau devis ou facture
    ---
    tags:
      - Factures
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
            - client_id
            - lignes
          properties:
            type:
              type: string
              enum: [devis, facture]
              description: Type de document
            client_id:
              type: integer
              description: ID du client
            lignes:
              type: array
              items:
                type: object
                properties:
                  type_ligne:
                    type: string
                    enum: [produit, service, texte, remise, custom]
                    description: Type de ligne
                  description:
                    type: string
                    description: Description de la ligne
                  quantite:
                    type: number
                    description: Quantité
                  prix_unitaire_ht:
                    type: number
                    description: Prix unitaire HT
                  tva:
                    type: number
                    description: Taux de TVA (%)
              description: Lignes du document
            status:
              type: string
              enum: [en_attente, envoyé, payé, annulé]
              description: Statut du document
            due_date:
              type: string
              format: date-time
              description: Date d'échéance
            notes:
              type: string
              description: Notes additionnelles
    responses:
      201:
        description: Document créé avec succès
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du document créé
            message:
              type: string
              description: Message de confirmation
            total_ht:
              type: number
              format: float
              description: Montant total HT
            total_tva:
              type: number
              format: float
              description: Montant total de TVA
            total_ttc:
              type: number
              format: float
              description: Montant total TTC
      400:
        description: Données invalides
      401:
        description: Non authentifié
      403:
        description: Client non autorisé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    # Valider les données requises
    required_fields = ['type', 'client_id', 'lignes']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis'}), 400
    
    # Extraire les données
    type_doc = data['type']
    client_id = data['client_id']
    lignes = data['lignes']
    status = data.get('status', 'en_attente')
    due_date = data.get('due_date')
    notes = data.get('notes', '')
    
    # Valider le type de document
    if type_doc not in ['devis', 'facture']:
        return jsonify({'message': 'Le type doit être devis ou facture'}), 400
    
    # Valider le statut
    if status not in ['en_attente', 'envoyé', 'payé', 'annulé']:
        return jsonify({'message': 'Statut invalide'}), 400
    
    # Valider qu'il y a au moins une ligne
    if not lignes or not isinstance(lignes, list) or len(lignes) == 0:
        return jsonify({'message': 'Le document doit contenir au moins une ligne'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier si le client existe et appartient à l'utilisateur
            client_query = text("""
                SELECT id 
                FROM clients 
                WHERE id = :client_id AND (created_by_user = :user_id OR EXISTS (
                    SELECT 1 FROM users WHERE id = :user_id AND role = 'admin'
                ))
            """)
            
            client = conn.execute(client_query, {
                "client_id": client_id,
                "user_id": user_id
            }).fetchone()
            
            if not client:
                return jsonify({'message': 'Client invalide ou non autorisé'}), 403
            
            # Calculer les totaux
            total_ht = sum(float(ligne.get('prix_unitaire_ht', 0)) * float(ligne.get('quantite', 1)) for ligne in lignes)
            total_tva = sum(float(ligne.get('prix_unitaire_ht', 0)) * float(ligne.get('quantite', 1)) * float(ligne.get('tva', 20)) / 100 for ligne in lignes)
            total_ttc = total_ht + total_tva
            
            # Créer le document
            insert_query = text("""
                INSERT INTO devis_factures (
                    user_id, client_id, type, status, date, due_date,
                    total_ht, total_tva, total_ttc, notes
                )
                VALUES (
                    :user_id, :client_id, :type, :status, NOW(),
                    :due_date, :total_ht, :total_tva, :total_ttc, :notes
                )
                RETURNING id
            """)
            
            params = {
                "user_id": user_id,
                "client_id": client_id,
                "type": type_doc,
                "status": status,
                "due_date": due_date if due_date else (datetime.now() + timedelta(days=30)).isoformat(),
                "total_ht": total_ht,
                "total_tva": total_tva,
                "total_ttc": total_ttc,
                "notes": notes
            }
            
            result = conn.execute(insert_query, params)
            doc_id = result.fetchone()[0]
            
            # Insérer les lignes
            for i, ligne in enumerate(lignes):
                insert_line_query = text("""
                    INSERT INTO devis_factures_lignes (
                        devis_id, ordre, type_ligne, description,
                        quantite, prix_unitaire_ht, tva
                    )
                    VALUES (
                        :devis_id, :ordre, :type_ligne, :description,
                        :quantite, :prix_unitaire_ht, :tva
                    )
                """)
                
                line_params = {
                    "devis_id": doc_id,
                    "ordre": i + 1,
                    "type_ligne": ligne.get('type_ligne', 'produit'),
                    "description": ligne.get('description', ''),
                    "quantite": float(ligne.get('quantite', 1)),
                    "prix_unitaire_ht": float(ligne.get('prix_unitaire_ht', 0)),
                    "tva": float(ligne.get('tva', 20))
                }
                
                conn.execute(insert_line_query, line_params)
            
            # Commit les changements
            conn.commit()
            
            # Retourner l'ID du document créé
            return jsonify({
                'id': doc_id,
                'message': f'{type_doc.capitalize()} créé avec succès',
                'total_ht': total_ht,
                'total_tva': total_tva,
                'total_ttc': total_ttc
            }), 201
    except Exception as e:
        logger.error(f"Error creating invoice: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour récupérer un devis/facture spécifique
@invoice_bp.route('/<int:doc_id>', methods=['GET'])
@token_required
def get_invoice(doc_id):
    """
    Récupère les détails d'un devis ou d'une facture
    ---
    tags:
      - Factures
    security:
      - Bearer: []
    parameters:
      - in: path
        name: doc_id
        required: true
        type: integer
        description: ID du devis ou de la facture
    responses:
      200:
        description: Détails du document
        schema:
          type: object
          properties:
            id:
              type: integer
              description: ID du document
            type:
              type: string
              enum: [devis, facture]
              description: Type de document
            status:
              type: string
              enum: [en_attente, envoyé, payé, annulé]
              description: Statut du document
            date:
              type: string
              format: date-time
              description: Date de création
            due_date:
              type: string
              format: date-time
              description: Date d'échéance
            total_ht:
              type: number
              format: float
              description: Montant total HT
            total_tva:
              type: number
              format: float
              description: Montant total de TVA
            total_ttc:
              type: number
              format: float
              description: Montant total TTC
            client_name:
              type: string
              description: Nom du client
            client_email:
              type: string
              description: Email du client
            freelance_name:
              type: string
              description: Nom du freelance
            freelance_email:
              type: string
              description: Email du freelance
            lignes:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    description: ID de la ligne
                  ordre:
                    type: integer
                    description: Ordre d'affichage de la ligne
                  type_ligne:
                    type: string
                    enum: [produit, service, texte, remise, custom]
                    description: Type de ligne
                  description:
                    type: string
                    description: Description de la ligne
                  quantite:
                    type: number
                    description: Quantité
                  prix_unitaire_ht:
                    type: number
                    description: Prix unitaire HT
                  tva:
                    type: number
                    description: Taux de TVA (%)
                  total_ht:
                    type: number
                    description: Total HT de la ligne
                  total_tva:
                    type: number
                    description: Total TVA de la ligne
                  total_ttc:
                    type: number
                    description: Total TTC de la ligne
      401:
        description: Non authentifié
      404:
        description: Document non trouvé ou non autorisé
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
            
            # Récupérer le document
            doc_query = text("""
                SELECT df.*, c.full_name as client_name, c.email as client_email,
                       u.full_name as freelance_name, u.email as freelance_email
                FROM devis_factures df
                LEFT JOIN clients c ON df.client_id = c.id
                LEFT JOIN users u ON df.user_id = u.id
                WHERE df.id = :doc_id AND (df.user_id = :user_id OR :is_admin)
            """)
            
            document = conn.execute(doc_query, {
                "doc_id": doc_id,
                "user_id": user_id,
                "is_admin": is_admin
            }).fetchone()
            
            if not document:
                return jsonify({'message': 'Document not found or unauthorized'}), 404
            
            # Convertir en dictionnaire
            doc_dict = {column: getattr(document, column) for column in document._mapping.keys()}
            
            # Conversion des valeurs décimales en float pour la sérialisation JSON
            for key in ['total_ht', 'total_tva', 'total_ttc']:
                if doc_dict.get(key):
                    doc_dict[key] = float(doc_dict[key])
            
            # Récupérer les lignes du document
            lines_query = text("""
                SELECT id, ordre, type_ligne, description, quantite, prix_unitaire_ht, tva
                FROM devis_factures_lignes
                WHERE devis_id = :doc_id
                ORDER BY ordre
            """)
            
            lines = conn.execute(lines_query, {"doc_id": doc_id}).fetchall()
            
            # Convertir les lignes en liste de dictionnaires
            lines_list = []
            for line in lines:
                line_dict = {column: getattr(line, column) for column in line._mapping.keys()}
                
                # Conversion des valeurs décimales en float pour la sérialisation JSON
                for key in ['quantite', 'prix_unitaire_ht', 'tva']:
                    if line_dict.get(key):
                        line_dict[key] = float(line_dict[key])
                
                # Calculer les totaux de la ligne
                line_dict['total_ht'] = line_dict['quantite'] * line_dict['prix_unitaire_ht']
                line_dict['total_tva'] = line_dict['total_ht'] * (line_dict['tva'] / 100)
                line_dict['total_ttc'] = line_dict['total_ht'] + line_dict['total_tva']
                
                lines_list.append(line_dict)
            
            # Ajouter les lignes au document
            doc_dict['lignes'] = lines_list
            
            return jsonify(doc_dict)
    except Exception as e:
        logger.error(f"Error getting invoice details: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour générer un PDF du devis/facture
@invoice_bp.route('/<int:doc_id>/pdf', methods=['GET'])
@token_required
def generate_invoice_pdf(doc_id):
    """
    Génère un PDF pour un devis ou une facture
    ---
    tags:
      - Factures
    security:
      - Bearer: []
    parameters:
      - in: path
        name: doc_id
        required: true
        type: integer
        description: ID du devis ou de la facture
    responses:
      200:
        description: Fichier PDF généré et téléchargé
        content:
          application/pdf:
            schema:
              type: string
              format: binary
      401:
        description: Non authentifié
      404:
        description: Document non trouvé ou non autorisé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier l'accès au document
            access_query = text("""
                SELECT 1
                FROM devis_factures df
                WHERE df.id = :doc_id AND (df.user_id = :user_id OR EXISTS (
                    SELECT 1 FROM users WHERE id = :user_id AND role = 'admin'
                ))
            """)
            
            access = conn.execute(access_query, {
                "doc_id": doc_id,
                "user_id": user_id
            }).fetchone()
            
            if not access:
                return jsonify({'message': 'Document not found or unauthorized'}), 404
            
            # Utiliser l'endpoint GET du document pour récupérer toutes les données
            from flask import url_for
            doc_data = json.loads(get_invoice(doc_id).data)
            
            # Générer le PDF avec les données
            from app.utils.pdf_utils import generate_invoice_pdf
            
            pdf_bytes = generate_invoice_pdf(doc_data)
            
            # Créer un fichier temporaire pour le PDF
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file.write(pdf_bytes)
            temp_file.close()
            
            # Déterminer le nom du fichier en fonction du type
            doc_type = "Devis" if doc_data['type'] == 'devis' else "Facture"
            filename = f"{doc_type}_{doc_id}_{uuid.uuid4().hex[:8]}.pdf"
            
            # Mettre à jour l'URL du PDF dans la base de données
            update_query = text("""
                UPDATE devis_factures
                SET pdf_url = :pdf_url
                WHERE id = :doc_id
            """)
            
            # Dans un environnement réel, on stockerait le PDF dans un service comme S3
            # et on mettrait à jour l'URL. Ici on simule juste.
            pdf_url = f"/devis/{doc_id}/pdf"
            
            conn.execute(update_query, {
                "pdf_url": pdf_url,
                "doc_id": doc_id
            })
            
            conn.commit()
            
            # Renvoyer le PDF
            return send_file(temp_file.name, 
                            mimetype='application/pdf',
                            as_attachment=True,
                            download_name=filename)
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour mettre à jour le statut d'un devis/facture
@invoice_bp.route('/<int:doc_id>/status', methods=['PUT'])
@token_required
def update_invoice_status(doc_id):
    """
    Met à jour le statut d'un devis ou d'une facture
    ---
    tags:
      - Factures
    security:
      - Bearer: []
    parameters:
      - in: path
        name: doc_id
        required: true
        type: integer
        description: ID du devis ou de la facture
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - status
          properties:
            status:
              type: string
              enum: [en_attente, envoyé, payé, annulé]
              description: Nouveau statut du document
    responses:
      200:
        description: Statut mis à jour avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              description: Message de confirmation
            id:
              type: integer
              description: ID du document
            status:
              type: string
              enum: [en_attente, envoyé, payé, annulé]
              description: Nouveau statut du document
            payment_date:
              type: string
              format: date-time
              description: Date de paiement (uniquement si status=payé)
      400:
        description: Données invalides
      401:
        description: Non authentifié
      404:
        description: Document non trouvé ou non autorisé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    data = request.json
    
    if 'status' not in data:
        return jsonify({'message': 'Le statut est requis'}), 400
    
    new_status = data['status']
    
    # Valider le statut
    if new_status not in ['en_attente', 'envoyé', 'payé', 'annulé']:
        return jsonify({'message': 'Statut invalide'}), 400
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Vérifier l'accès au document
            access_query = text("""
                SELECT df.id, df.type, df.client_id, df.total_ttc, u.stripe_account_id, u.payout_enabled
                FROM devis_factures df
                JOIN users u ON df.user_id = u.id
                WHERE df.id = :doc_id AND (df.user_id = :user_id OR EXISTS (
                    SELECT 1 FROM users WHERE id = :user_id AND role = 'admin'
                ))
            """)
            
            document = conn.execute(access_query, {
                "doc_id": doc_id,
                "user_id": user_id
            }).fetchone()
            
            if not document:
                return jsonify({'message': 'Document not found or unauthorized'}), 404
            
            # Si le statut passe à 'payé', mettre à jour la date de paiement
            payment_date = None
            if new_status == 'payé':
                payment_date = datetime.now().isoformat()
            
            # Mettre à jour le statut
            update_query = text("""
                UPDATE devis_factures
                SET status = :status, 
                    payment_date = :payment_date
                WHERE id = :doc_id
            """)
            
            conn.execute(update_query, {
                "status": new_status,
                "payment_date": payment_date,
                "doc_id": doc_id
            })
            
            conn.commit()
            
            return jsonify({
                'message': 'Statut mis à jour avec succès',
                'id': doc_id,
                'status': new_status,
                'payment_date': payment_date
            })
    except Exception as e:
        logger.error(f"Error updating invoice status: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500

# Endpoint pour créer une session de paiement Stripe pour un devis/facture
@invoice_bp.route('/<int:doc_id>/payer', methods=['POST'])
@token_required
def pay_invoice(doc_id):
    """
    Crée une session de paiement Stripe pour un devis/facture
    ---
    tags:
      - Factures
    security:
      - Bearer: []
    parameters:
      - in: path
        name: doc_id
        required: true
        type: integer
        description: ID du devis ou de la facture à payer
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
        description: Document déjà payé ou données invalides
      401:
        description: Non authentifié
      404:
        description: Document non trouvé
      500:
        description: Erreur serveur
    """
    user_id = request.user_id
    
    engine = current_app.config.get('db_engine')
    if not engine:
        return jsonify({'message': 'Database connection error'}), 500
    
    try:
        with engine.connect() as conn:
            # Récupérer les informations du document
            doc_query = text("""
                SELECT df.id, df.type, df.client_id, df.total_ttc, df.status,
                       df.user_id as freelance_id, u.stripe_account_id, u.payout_enabled,
                       c.full_name as client_name, u.full_name as freelance_name
                FROM devis_factures df
                JOIN users u ON df.user_id = u.id
                JOIN clients c ON df.client_id = c.id
                WHERE df.id = :doc_id
            """)
            
            document = conn.execute(doc_query, {"doc_id": doc_id}).fetchone()
            
            if not document:
                return jsonify({'message': 'Document not found'}), 404
            
            # Vérifier que le document n'est pas déjà payé
            if document.status == 'payé':
                return jsonify({'message': 'Ce document est déjà payé'}), 400
            
            # Créer la description du paiement
            description = f"{'Devis' if document.type == 'devis' else 'Facture'} #{document.id} - {document.freelance_name}"
            
            # Déterminer si on peut faire un paiement direct avec Stripe Connect
            freelance_stripe_id = None
            if document.stripe_account_id and document.payout_enabled:
                freelance_stripe_id = document.stripe_account_id
            
            # Créer la session de paiement
            checkout_session = create_checkout_session(
                client_id=document.client_id,
                product_id=0,  # Pas de produit spécifique pour un devis/facture
                freelance_id=document.freelance_id,
                montant=float(document.total_ttc),
                description=description,
                freelance_stripe_id=freelance_stripe_id,
                metadata={
                    "invoice_id": str(document.id),
                    "invoice_type": document.type,
                    "client_name": document.client_name
                }
            )
            
            # Mettre à jour le statut du document
            update_query = text("""
                UPDATE devis_factures
                SET status = 'envoyé'
                WHERE id = :doc_id
            """)
            
            conn.execute(update_query, {"doc_id": doc_id})
            conn.commit()
            
            # Retourner l'URL de paiement
            return jsonify({
                'session_id': checkout_session.id,
                'checkout_url': checkout_session.url
            })
    except Exception as e:
        logger.error(f"Error creating payment session: {str(e)}")
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500