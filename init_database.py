import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get database URL from environment variables
database_url = os.environ.get("DATABASE_URL")

if not database_url:
    logger.error("DATABASE_URL environment variable not set")
    sys.exit(1)

# Create engine
engine = create_engine(database_url)

# Function to execute SQL safely
def execute_sql(conn, sql, description="SQL"):
    try:
        conn.execute(text(sql))
        logger.info(f"Success: {description}")
        return True
    except SQLAlchemyError as e:
        logger.warning(f"Error in {description}: {str(e)}")
        return False

try:
    with engine.begin() as conn:
        # Create users table
        users_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255),
            email VARCHAR(255) UNIQUE,
            password_hash TEXT,
            phone_number VARCHAR(20),
            bio TEXT,
            role VARCHAR(50),
            stripe_account_id VARCHAR(255),
            stripe_dashboard_url TEXT,
            payout_enabled BOOLEAN,
            partner_id INT,
            affiliation_code VARCHAR(20),
            siret VARCHAR(14),
            vat_number VARCHAR(20),
            company_name VARCHAR(255),
            birthdate DATE,
            country VARCHAR(100),
            city VARCHAR(100),
            zip_code VARCHAR(10),
            language VARCHAR(10),
            website TEXT,
            portfolio_url TEXT,
            id_card_verified BOOLEAN,
            kyc_status VARCHAR(50),
            last_login_at TIMESTAMP,
            account_status VARCHAR(50),
            total_revenue DECIMAL(10,2),
            rating DECIMAL(3,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            experience_type VARCHAR(100)
        )
        """
        execute_sql(conn, users_sql, "Create users table")
        
        # Create clients table
        clients_sql = """
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255),
            email VARCHAR(255),
            phone_number VARCHAR(20),
            company_name VARCHAR(255),
            siret VARCHAR(14),
            vat_number VARCHAR(20),
            industry VARCHAR(100),
            billing_email VARCHAR(255),
            client_type VARCHAR(50),
            preferred_payment_method VARCHAR(50),
            lifetime_value DECIMAL(10,2),
            last_purchase_date TIMESTAMP,
            created_by_user INT,
            source VARCHAR(50),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by_user) REFERENCES users(id) ON DELETE SET NULL
        )
        """
        execute_sql(conn, clients_sql, "Create clients table")
        
        # Create produits table
        produits_sql = """
        CREATE TABLE IF NOT EXISTS produits (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(255),
            description TEXT,
            prix DECIMAL(10,2),
            type VARCHAR(50),
            delivery_time_days INT,
            is_customizable BOOLEAN,
            category VARCHAR(50),
            freelance_only BOOLEAN,
            actif BOOLEAN
        )
        """
        execute_sql(conn, produits_sql, "Create produits table")
        
        # Create commerciaux table
        commerciaux_sql = """
        CREATE TABLE IF NOT EXISTS commerciaux (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255),
            email VARCHAR(255),
            pourcentage DECIMAL(5,2),
            status VARCHAR(50),
            tracking_code VARCHAR(20),
            contract_signed_at TIMESTAMP
        )
        """
        execute_sql(conn, commerciaux_sql, "Create commerciaux table")
        
        # Create partenaires table
        partenaires_sql = """
        CREATE TABLE IF NOT EXISTS partenaires (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(255),
            type VARCHAR(50),
            email_contact VARCHAR(255),
            pourcentage DECIMAL(5,2),
            tracking_url TEXT,
            status VARCHAR(50),
            contract_signed_at TIMESTAMP
        )
        """
        execute_sql(conn, partenaires_sql, "Create partenaires table")
        
        # Create ENUM types for PostgreSQL - try each one separately
        for enum_name, enum_values in [
            ("statut_paiement_enum", "('payé', 'en_attente', 'remboursé')"),
            ("type_document_enum", "('devis', 'facture')"),
            ("status_document_enum", "('en_attente', 'envoyé', 'payé', 'annulé')"),
            ("type_ligne_enum", "('produit', 'service', 'texte', 'remise', 'custom')"),
            ("source_type_enum", "('commercial', 'partenaire', 'lien')")
        ]:
            # Check if enum exists
            enum_exists = conn.execute(text(
                f"SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}')"
            )).scalar()
            
            if not enum_exists:
                enum_sql = f"CREATE TYPE {enum_name} AS ENUM {enum_values}"
                execute_sql(conn, enum_sql, f"Create {enum_name}")
        
        # Create ventes table
        ventes_sql = """
        CREATE TABLE IF NOT EXISTS ventes (
            id SERIAL PRIMARY KEY,
            user_id INT,
            client_id INT,
            produit_id INT,
            montant DECIMAL(10,2),
            discount_applied DECIMAL(10,2) DEFAULT 0,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR(50),
            commission_plateforme DECIMAL(10,2) DEFAULT 0,
            commission_commerciale DECIMAL(10,2) DEFAULT 0,
            commission_partenaire DECIMAL(10,2) DEFAULT 0,
            montant_net_freelance DECIMAL(10,2) DEFAULT 0,
            commercial_id INT,
            partenaire_id INT,
            stripe_payment_id VARCHAR(255),
            statut_paiement statut_paiement_enum DEFAULT 'en_attente',
            feedback TEXT,
            invoice_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
            FOREIGN KEY (produit_id) REFERENCES produits(id) ON DELETE SET NULL,
            FOREIGN KEY (commercial_id) REFERENCES commerciaux(id) ON DELETE SET NULL,
            FOREIGN KEY (partenaire_id) REFERENCES partenaires(id) ON DELETE SET NULL
        )
        """
        execute_sql(conn, ventes_sql, "Create ventes table")
        
        # Create devis_factures table
        devis_factures_sql = """
        CREATE TABLE IF NOT EXISTS devis_factures (
            id SERIAL PRIMARY KEY,
            user_id INT,
            client_id INT,
            type type_document_enum,
            status status_document_enum DEFAULT 'en_attente',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            due_date TIMESTAMP,
            payment_date TIMESTAMP,
            payment_method VARCHAR(50),
            total_ht DECIMAL(10,2) DEFAULT 0,
            total_tva DECIMAL(10,2) DEFAULT 0,
            total_ttc DECIMAL(10,2) DEFAULT 0,
            paid_by_user_id INT,
            pdf_url TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
            FOREIGN KEY (paid_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
        execute_sql(conn, devis_factures_sql, "Create devis_factures table")
        
        # Create devis_factures_lignes table - with calculated fields
        devis_factures_lignes_sql = """
        CREATE TABLE IF NOT EXISTS devis_factures_lignes (
            id SERIAL PRIMARY KEY,
            devis_id INT,
            ordre INT DEFAULT 0,
            type_ligne type_ligne_enum DEFAULT 'produit',
            description TEXT NOT NULL,
            quantite DECIMAL(10,2) DEFAULT 1.00,
            prix_unitaire_ht DECIMAL(10,2) DEFAULT 0.00,
            tva DECIMAL(5,2) DEFAULT 20.00,
            total_ht DECIMAL(10,2),
            total_tva DECIMAL(10,2),
            total_ttc DECIMAL(10,2),
            FOREIGN KEY (devis_id) REFERENCES devis_factures(id) ON DELETE CASCADE
        )
        """
        execute_sql(conn, devis_factures_lignes_sql, "Create devis_factures_lignes table")
        
        # Create trigger function
        trigger_function_sql = """
        CREATE OR REPLACE FUNCTION calculate_ligne_totals()
        RETURNS TRIGGER AS $BODY$
        BEGIN
            NEW.total_ht := NEW.quantite * NEW.prix_unitaire_ht;
            NEW.total_tva := NEW.quantite * NEW.prix_unitaire_ht * NEW.tva / 100;
            NEW.total_ttc := NEW.total_ht + NEW.total_tva;
            RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
        """
        execute_sql(conn, trigger_function_sql, "Create trigger function")
        
        # Create trigger
        trigger_sql = """
        DROP TRIGGER IF EXISTS calculate_totals_trigger ON devis_factures_lignes;
        CREATE TRIGGER calculate_totals_trigger
        BEFORE INSERT OR UPDATE ON devis_factures_lignes
        FOR EACH ROW
        EXECUTE FUNCTION calculate_ligne_totals();
        """
        execute_sql(conn, trigger_sql, "Create trigger")
        
        # Create affiliations table
        affiliations_sql = """
        CREATE TABLE IF NOT EXISTS affiliations (
            id SERIAL PRIMARY KEY,
            source_type source_type_enum,
            source_id INT,
            vente_id INT,
            commission DECIMAL(10,2) DEFAULT 0,
            FOREIGN KEY (vente_id) REFERENCES ventes(id) ON DELETE CASCADE
        )
        """
        execute_sql(conn, affiliations_sql, "Create affiliations table")
        
        # Create avis_freelance table
        avis_freelance_sql = """
        CREATE TABLE IF NOT EXISTS avis_freelance (
            id SERIAL PRIMARY KEY,
            user_id INT,
            client_id INT,
            vente_id INT,
            note INT,
            commentaire TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visible BOOLEAN,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
            FOREIGN KEY (vente_id) REFERENCES ventes(id) ON DELETE CASCADE
        )
        """
        execute_sql(conn, avis_freelance_sql, "Create avis_freelance table")
        
        # Create avis_plateforme table
        avis_plateforme_sql = """
        CREATE TABLE IF NOT EXISTS avis_plateforme (
            id SERIAL PRIMARY KEY,
            auteur_id INT,
            auteur_role VARCHAR(20),
            note INT,
            commentaire TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visible BOOLEAN,
            version_plateforme VARCHAR(20),
            experience_type VARCHAR(100)
        )
        """
        execute_sql(conn, avis_plateforme_sql, "Create avis_plateforme table")
        
        # Create authentifications table
        authentifications_sql = """
        CREATE TABLE IF NOT EXISTS authentifications (
            id SERIAL PRIMARY KEY,
            user_id INT,
            provider VARCHAR(50),
            provider_user_id VARCHAR(255),
            email VARCHAR(255),
            password_hash TEXT,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
        execute_sql(conn, authentifications_sql, "Create authentifications table")
        
    logger.info("Database schema initialization completed successfully")
    
except SQLAlchemyError as e:
    logger.error(f"Database error: {str(e)}")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error: {str(e)}")
    sys.exit(1)