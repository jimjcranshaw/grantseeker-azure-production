#!/usr/bin/env python3
"""
Insert unique charity commission funders into PostgreSQL database.

This script reads the unique_charity_commission_funders.csv file and inserts
funders that don't already exist in the database (checked by charity_number).
Only inserts name, charity_number, and website fields - all other fields remain NULL/default.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create database connection."""
    db_config = {
        'host': os.getenv('DB_HOST', 'grantseeker-db.postgres.database.azure.com'),
        'user': os.getenv('DB_USER', 'grantseekeradmin'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME', 'postgres'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'sslmode': 'require'
    }
    
    try:
        conn = psycopg2.connect(**db_config)
        logger.info("✅ Database connection established")
        return conn
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {str(e)}")
        raise

def check_existing_charity_numbers(conn):
    """Get set of existing charity numbers from database."""
    logger.info("🔍 Checking for existing charity numbers in database...")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT charity_number 
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
        """)
        
        existing_numbers = {str(row[0]).strip() for row in cursor.fetchall() if row[0]}
        cursor.close()
        
        logger.info(f"📊 Found {len(existing_numbers)} existing charity numbers")
        return existing_numbers
        
    except Exception as e:
        logger.error(f"❌ Error checking existing charity numbers: {str(e)}")
        raise

def insert_funders(conn, df, existing_charity_numbers):
    """Insert funders into database."""
    logger.info(f"🚀 Starting insertion of {len(df)} funders...")
    
    # Filter out funders that already exist
    df_to_insert = df[~df['charity_number'].astype(str).isin(existing_charity_numbers)].copy()
    
    if len(df_to_insert) == 0:
        logger.warning("⚠️ No new funders to insert (all already exist)")
        return 0, 0
    
    logger.info(f"📝 {len(df_to_insert)} new funders to insert (skipping {len(df) - len(df_to_insert)} existing)")
    
    # Prepare data for insertion
    records = []
    for _, row in df_to_insert.iterrows():
        # Convert charity_number to string, handle NaN
        charity_num = str(row['charity_number']).strip() if pd.notna(row['charity_number']) else None
        website = row['website'].strip() if pd.notna(row['website']) and row['website'].strip() else None
        name = row['name'].strip() if pd.notna(row['name']) else None
        
        if not name:
            logger.warning(f"⚠️ Skipping row with missing name (charity_number: {charity_num})")
            continue
        
        records.append((
            name,           # name
            website,        # website (can be None)
            charity_num,    # charity_number (can be None)
        ))
    
    if not records:
        logger.warning("⚠️ No valid records to insert after processing")
        return 0, 0
    
    inserted_count = 0
    failed_count = 0
    
    try:
        cursor = conn.cursor()
        
        # Insert query - only name, website, and charity_number
        # Using ON CONFLICT (name) since there's a unique constraint on name
        # created_at and updated_at have DEFAULT values, so we don't need to specify them
        insert_query = """
            INSERT INTO funders (
                name, 
                website, 
                charity_number
            ) VALUES %s
            ON CONFLICT (name) DO NOTHING
        """
        
        # Insert in batches of 1000
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            try:
                execute_values(cursor, insert_query, batch)
                conn.commit()
                inserted_count += len(batch)
                logger.info(f"✅ Inserted batch {i//batch_size + 1}: {len(batch)} funders (Total: {inserted_count})")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"❌ Batch insertion failed: {str(e)}")
                failed_count += len(batch)
        
        cursor.close()
        
    except Exception as e:
        logger.error(f"❌ Database insertion failed: {str(e)}")
        failed_count = len(records)
        raise
    
    return inserted_count, failed_count

def main():
    """Main execution function."""
    csv_file = "/home/azureuser/grantseeker-azure-production-1/unique_charity_commission_funders.csv"
    
    logger.info("🚀 Starting unique funders insertion process...")
    logger.info(f"📖 Reading CSV file: {csv_file}")
    
    try:
        # Read CSV file
        df = pd.read_csv(csv_file)
        logger.info(f"✅ Loaded {len(df)} funders from CSV")
        
        # Connect to database
        conn = get_db_connection()
        
        try:
            # Check existing charity numbers
            existing_numbers = check_existing_charity_numbers(conn)
            
            # Insert funders
            inserted_count, failed_count = insert_funders(conn, df, existing_numbers)
            
            # Generate summary
            skipped_count = len(df) - inserted_count - failed_count
            
            logger.info("\n" + "="*60)
            logger.info("INSERTION SUMMARY")
            logger.info("="*60)
            logger.info(f"Total funders in CSV: {len(df):,}")
            logger.info(f"Successfully inserted: {inserted_count:,}")
            logger.info(f"Already existed (skipped): {skipped_count:,}")
            logger.info(f"Failed: {failed_count:,}")
            logger.info("="*60)
            
        finally:
            conn.close()
            logger.info("✅ Database connection closed")
        
    except FileNotFoundError:
        logger.error(f"❌ CSV file not found: {csv_file}")
        return 1
    except Exception as e:
        logger.error(f"❌ Process failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
