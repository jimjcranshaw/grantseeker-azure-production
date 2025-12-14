#!/usr/bin/env python3
"""
UKCAT Integration Database Migration
===================================

This script adds UKCAT classification support to the grantseeker database.

Changes:
- Add charity_number column to funders table
- Add ukcat_codes JSONB column to funders table  
- Add ukcat_codes JSONB column to funding_opportunities table
- Create ukcat_codes reference table
- Add performance indexes

Usage:
    python migration_add_ukcat_integration.py

Author: Grant Seeker UKCAT Integration
Date: December 2025
"""

import os
import psycopg2
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_ukcat_migration():
    """Execute UKCAT integration migration."""
    
    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return False
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    try:
        logger.info("🚀 Starting UKCAT integration migration...")
        
        # 1. Add charity_number column to funders table
        logger.info("📝 Adding charity_number column to funders table...")
        cursor.execute("""
            ALTER TABLE funders 
            ADD COLUMN IF NOT EXISTS charity_number VARCHAR(20);
        """)
        logger.info("✅ charity_number column added")
        
        # 2. Add ukcat_codes JSONB column to funders table
        logger.info("📝 Adding ukcat_codes JSONB column to funders table...")
        cursor.execute("""
            ALTER TABLE funders 
            ADD COLUMN IF NOT EXISTS ukcat_codes JSONB DEFAULT '[]'::jsonb;
        """)
        logger.info("✅ ukcat_codes column added to funders table")
        
        # 3. Add ukcat_codes JSONB column to funding_opportunities table  
        logger.info("📝 Adding ukcat_codes JSONB column to funding_opportunities table...")
        cursor.execute("""
            ALTER TABLE funding_opportunities 
            ADD COLUMN IF NOT EXISTS ukcat_codes JSONB DEFAULT '[]'::jsonb;
        """)
        logger.info("✅ ukcat_codes column added to funding_opportunities table")
        
        # 4. Create UKCAT codes reference table
        logger.info("📝 Creating ukcat_codes reference table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ukcat_codes (
                code VARCHAR(10) PRIMARY KEY,
                tag VARCHAR(200) NOT NULL,
                category VARCHAR(100),
                subcategory VARCHAR(100),
                level INTEGER,
                notes TEXT,
                related_icnptso VARCHAR(100),
                regex_pattern TEXT,
                exclude_regex_pattern TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("✅ ukcat_codes reference table created")
        
        # 5. Add performance indexes
        logger.info("📝 Adding performance indexes...")
        
        # Index on charity_number for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_charity_number 
            ON funders(charity_number);
        """)
        logger.info("✅ Index on charity_number created")
        
        # Index on ukcat_codes JSONB for fast array queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_ukcat_codes_gin 
            ON funders USING gin(ukcat_codes);
        """)
        logger.info("✅ GIN index on ukcat_codes created")
        
        # Index on ukcat_codes in funding_opportunities
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_ukcat_codes_gin 
            ON funding_opportunities USING gin(ukcat_codes);
        """)
        logger.info("✅ GIN index on opportunities ukcat_codes created")
        
        # Index on ukcat_codes reference table
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ukcat_codes_category 
            ON ukcat_codes(category);
        """)
        logger.info("✅ Index on ukcat_codes category created")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ukcat_codes_level 
            ON ukcat_codes(level);
        """)
        logger.info("✅ Index on ukcat_codes level created")
        
        # 6. Add updated_at columns for tracking changes
        logger.info("📝 Adding updated_at tracking columns...")
        cursor.execute("""
            ALTER TABLE funders 
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)
        
        cursor.execute("""
            ALTER TABLE funding_opportunities 
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)
        logger.info("✅ updated_at columns added")
        
        # Commit all changes
        conn.commit()
        logger.info("🎉 UKCAT integration migration completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = create_ukcat_migration()
    if success:
        print("\n✅ Migration completed successfully!")
        print("📊 Database is now ready for UKCAT integration")
    else:
        print("\n❌ Migration failed!")
        print("🔍 Check logs for details")
        exit(1)