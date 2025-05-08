#!/usr/bin/env python3
"""
Script pour initialiser une base de données MySQL pour l'application BeMyNet
"""
import os
import logging
import pymysql
from sqlalchemy import create_engine, text
from app.models.users import User
from app.models.auth import Authentification 
from app.models.clients import Client
from app.models.products import Produit
from app.models.sales import Vente, Affiliation
from app.models.invoices import DevisFacture, DevisFactureLigne
from app.models.reviews import AvisFreelance, AvisPlateforme
from app.models.partners import Commercial, Partenaire
from app.config import settings
from sqlalchemy.ext.declarative import declarative_base

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()

def create_mysql_database():
    """Crée la base de données MySQL si elle n'existe pas déjà"""
    try:
        # Connexion à MySQL sans spécifier de base de données
        connection = pymysql.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            # Vérifier si la base de données existe déjà
            cursor.execute(f"SHOW DATABASES LIKE '{settings.MYSQL_DATABASE}'")
            result = cursor.fetchone()
            
            if not result:
                # Créer la base de données
                cursor.execute(f"CREATE DATABASE `{settings.MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                logger.info(f"Base de données '{settings.MYSQL_DATABASE}' créée avec succès")
            else:
                logger.info(f"La base de données '{settings.MYSQL_DATABASE}' existe déjà")
        
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création de la base de données MySQL: {str(e)}")
        return False

def create_tables():
    """Crée les tables dans la base de données MySQL"""
    try:
        engine = create_engine(
            settings.DATABASE_URL,
            echo=True,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        
        # Créer toutes les tables définies dans les modèles
        Base.metadata.create_all(engine)
        
        logger.info("Tables créées avec succès dans la base de données MySQL")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création des tables: {str(e)}")
        return False

def execute_sql(engine, sql, description="SQL"):
    """Exécute du SQL arbitraire sur la base de données"""
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            logger.info(f"{description} exécuté avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du {description}: {str(e)}")
        return False

def main():
    """Fonction principale pour initialiser la base de données"""
    logger.info("Initialisation de la base de données MySQL pour BeMyNet...")
    
    # Créer la base de données si elle n'existe pas
    if not create_mysql_database():
        logger.error("Impossible de créer la base de données. Arrêt du script.")
        return
    
    # Créer les tables
    if not create_tables():
        logger.error("Impossible de créer les tables. Arrêt du script.")
        return
    
    logger.info("Initialisation de la base de données terminée avec succès")

if __name__ == "__main__":
    main()