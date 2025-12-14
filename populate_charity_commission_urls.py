#!/usr/bin/env python3
"""
Populate Charity Commission URLs for funders without websites.

This script updates funders that have charity numbers but no website,
setting their website field to their Charity Commission profile page URL.
"""

import psycopg2
import logging
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

def build_charity_commission_url(charity_number: str) -> str:
    """Build Charity Commission profile page URL from charity number."""
    return f"https://register-of-charities.charitycommission.gov.uk/charity-details/?regId={charity_number}&subId=0"

def populate_charity_commission_urls():
    """Update funders without websites to have their Charity Commission URLs."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Get funders without websites but with charity numbers
        cursor.execute("""
            SELECT id, charity_number, name
            FROM funders
            WHERE (website IS NULL OR website = '')
            AND charity_number IS NOT NULL
            AND charity_number != ''
        """)
        
        funders = cursor.fetchall()
        logger.info(f"📊 Found {len(funders)} funders without websites (with charity numbers)")
        
        if len(funders) == 0:
            logger.info("✅ No funders to update")
            return
        
        # Update each funder with their Charity Commission URL
        updated_count = 0
        for funder_id, charity_number, name in funders:
            charity_url = build_charity_commission_url(str(charity_number).strip())
            
            cursor.execute("""
                UPDATE funders
                SET website = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (charity_url, funder_id))
            
            updated_count += 1
            if updated_count % 100 == 0:
                logger.info(f"  ✓ Updated {updated_count}/{len(funders)} funders...")
        
        conn.commit()
        cursor.close()
        
        logger.info(f"✅ Successfully updated {updated_count} funders with Charity Commission URLs")
        
    except Exception as e:
        logger.error(f"❌ Error updating funders: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*70)
    print("POPULATE CHARITY COMMISSION URLS")
    print("="*70)
    print()
    
    populate_charity_commission_urls()
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
