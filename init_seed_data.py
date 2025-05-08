#!/usr/bin/env python3
"""
Initialize some test data for BeMyNet platform
"""

import os
import sys
import logging
import bcrypt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hash_password(password):
    """Generate a bcrypt hash for the given password"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def main():
    """Main function to seed the database with initial data"""
    
    # Get database URI from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        # Connect to the database
        engine = create_engine(database_url)
        logger.info("Connected to database")
        
        with engine.connect() as conn:
            # Create admin user if it doesn't exist
            user_query = text("""
                SELECT id FROM users 
                WHERE email = 'admin@bemynet.fr' 
                LIMIT 1
            """)
            
            existing_user = conn.execute(user_query).fetchone()
            
            if not existing_user:
                admin_password = hash_password("admin123")
                insert_admin = text("""
                    INSERT INTO users (
                        full_name, email, password_hash, role, 
                        phone_number, created_at, account_status
                    )
                    VALUES (
                        'Admin', 'admin@bemynet.fr', :password_hash, 'admin',
                        '+33123456789', NOW(), 'active'
                    )
                    RETURNING id
                """)
                
                admin_result = conn.execute(insert_admin, {
                    "password_hash": admin_password
                })
                admin_id = admin_result.fetchone().id
                logger.info(f"Created admin user with ID: {admin_id}")
            else:
                admin_id = existing_user.id
                logger.info(f"Admin user already exists with ID: {admin_id}")
            
            # Create test freelance user if it doesn't exist
            freelance_query = text("""
                SELECT id FROM users 
                WHERE email = 'freelance@bemynet.fr' 
                LIMIT 1
            """)
            
            existing_freelance = conn.execute(freelance_query).fetchone()
            
            if not existing_freelance:
                freelance_password = hash_password("freelance123")
                insert_freelance = text("""
                    INSERT INTO users (
                        full_name, email, password_hash, role, 
                        phone_number, bio, created_at, account_status,
                        company_name, siret, website, city, country
                    )
                    VALUES (
                        'Test Freelance', 'freelance@bemynet.fr', :password_hash, 'freelance',
                        '+33987654321', 'Développeur web fullstack avec 5 ans d''expérience', NOW(), 'active',
                        'FreeDev SARL', '12345678901234', 'https://freedev.fr', 'Paris', 'France'
                    )
                    RETURNING id
                """)
                
                freelance_result = conn.execute(insert_freelance, {
                    "password_hash": freelance_password
                })
                freelance_id = freelance_result.fetchone().id
                logger.info(f"Created freelance user with ID: {freelance_id}")
            else:
                freelance_id = existing_freelance.id
                logger.info(f"Freelance user already exists with ID: {freelance_id}")
            
            # Create test client if it doesn't exist
            client_query = text("""
                SELECT id FROM clients 
                WHERE email = 'client@example.com' 
                LIMIT 1
            """)
            
            existing_client = conn.execute(client_query).fetchone()
            
            if not existing_client:
                insert_client = text("""
                    INSERT INTO clients (
                        full_name, email, phone_number, company_name,
                        siret, industry, created_by_user, source, created_at
                    )
                    VALUES (
                        'Société Test', 'client@example.com', '+33123789456', 'Société Test SAS',
                        '98765432101234', 'E-commerce', :created_by, 'direct', NOW()
                    )
                    RETURNING id
                """)
                
                client_result = conn.execute(insert_client, {
                    "created_by": freelance_id
                })
                client_id = client_result.fetchone().id
                logger.info(f"Created test client with ID: {client_id}")
            else:
                client_id = existing_client.id
                logger.info(f"Test client already exists with ID: {client_id}")
            
            # Create test products if they don't exist
            product_query = text("""
                SELECT COUNT(*) as count FROM produits
            """)
            
            product_count = conn.execute(product_query).fetchone().count
            
            if product_count < 3:
                # Create some sample products
                products = [
                    {
                        "nom": "Site vitrine",
                        "description": "Site web vitrine professionnel pour présenter votre activité",
                        "prix": 1200.00,
                        "type": "service",
                        "delivery_time_days": 30,
                        "category": "web",
                        "freelance_only": True
                    },
                    {
                        "nom": "E-commerce WordPress",
                        "description": "Boutique en ligne complète avec WordPress et WooCommerce",
                        "prix": 2500.00,
                        "type": "service",
                        "delivery_time_days": 45,
                        "category": "web",
                        "freelance_only": True
                    },
                    {
                        "nom": "Application mobile",
                        "description": "Application mobile native iOS et Android",
                        "prix": 5000.00,
                        "type": "service",
                        "delivery_time_days": 90,
                        "category": "mobile",
                        "freelance_only": True
                    }
                ]
                
                insert_product = text("""
                    INSERT INTO produits (
                        nom, description, prix, type,
                        delivery_time_days, category, freelance_only, actif
                    )
                    VALUES (
                        :nom, :description, :prix, :type,
                        :delivery_time_days, :category, :freelance_only, true
                    )
                """)
                
                for product in products:
                    conn.execute(insert_product, product)
                
                logger.info(f"Created {len(products)} sample products")
            else:
                logger.info(f"Products already exist ({product_count} products found)")
                
            # Create sample invoice/quote if none exist
            doc_query = text("""
                SELECT COUNT(*) as count FROM devis_factures
            """)
            
            doc_count = conn.execute(doc_query).fetchone().count
            
            if doc_count == 0:
                # Create a sample invoice
                insert_invoice = text("""
                    INSERT INTO devis_factures (
                        user_id, client_id, type, status, date,
                        due_date, total_ht, total_tva, total_ttc,
                        payment_method, notes
                    )
                    VALUES (
                        :user_id, :client_id, 'facture', 'en_attente', NOW(),
                        NOW() + INTERVAL '30 days', 1000.00, 200.00, 1200.00,
                        'bank_transfer', 'Facture de test'
                    )
                    RETURNING id
                """)
                
                invoice_result = conn.execute(insert_invoice, {
                    "user_id": freelance_id,
                    "client_id": client_id
                })
                
                invoice_id = invoice_result.fetchone().id
                
                # Add some invoice lines
                insert_line = text("""
                    INSERT INTO devis_factures_lignes (
                        devis_id, ordre, type_ligne, description,
                        quantite, prix_unitaire_ht, tva
                    )
                    VALUES (
                        :devis_id, :ordre, :type_ligne, :description,
                        :quantite, :prix_unitaire_ht, 20
                    )
                """)
                
                lines = [
                    {
                        "devis_id": invoice_id,
                        "ordre": 1,
                        "type_ligne": "service",
                        "description": "Développement site web",
                        "quantite": 1,
                        "prix_unitaire_ht": 800.00
                    },
                    {
                        "devis_id": invoice_id,
                        "ordre": 2,
                        "type_ligne": "service",
                        "description": "Mise en place serveur",
                        "quantite": 1,
                        "prix_unitaire_ht": 200.00
                    }
                ]
                
                for line in lines:
                    conn.execute(insert_line, line)
                
                # Create a sample quote
                insert_quote = text("""
                    INSERT INTO devis_factures (
                        user_id, client_id, type, status, date,
                        due_date, total_ht, total_tva, total_ttc,
                        payment_method, notes
                    )
                    VALUES (
                        :user_id, :client_id, 'devis', 'en_attente', NOW(),
                        NOW() + INTERVAL '15 days', 2000.00, 400.00, 2400.00,
                        'card', 'Devis de test'
                    )
                    RETURNING id
                """)
                
                quote_result = conn.execute(insert_quote, {
                    "user_id": freelance_id,
                    "client_id": client_id
                })
                
                quote_id = quote_result.fetchone().id
                
                # Add some quote lines
                quote_lines = [
                    {
                        "devis_id": quote_id,
                        "ordre": 1,
                        "type_ligne": "service",
                        "description": "Développement application mobile",
                        "quantite": 1,
                        "prix_unitaire_ht": 1500.00
                    },
                    {
                        "devis_id": quote_id,
                        "ordre": 2,
                        "type_ligne": "service",
                        "description": "Design d'interface",
                        "quantite": 1,
                        "prix_unitaire_ht": 500.00
                    }
                ]
                
                for line in quote_lines:
                    conn.execute(insert_line, line)
                
                logger.info(f"Created sample invoice (ID: {invoice_id}) and quote (ID: {quote_id})")
            else:
                logger.info(f"Invoices/quotes already exist ({doc_count} documents found)")
            
            # Commit all changes
            conn.commit()
            logger.info("Database seeding completed successfully")
            
    except Exception as e:
        logger.error(f"Error seeding database: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()