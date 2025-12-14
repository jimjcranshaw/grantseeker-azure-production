#!/usr/bin/env python3
"""
Import UKCAT Classifications to Reference Table
==============================================

This script imports the UKCAT classification data from the CSV file
into the database reference table for lookup and matching.

Usage:
    python import_ukcat_classifications.py

Author: Grant Seeker UKCAT Integration
Date: December 2025
"""

import csv
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

def import_ukcat_data():
    """Import UKCAT classification data from CSV file."""
    
    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return False
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    # Path to UKCAT data file
    ukcat_csv_path = "ukcat_project/data/ukcat.csv"
    
    if not os.path.exists(ukcat_csv_path):
        logger.error(f"❌ UKCAT CSV file not found: {ukcat_csv_path}")
        return False
    
    try:
        logger.info(f"📥 Importing UKCAT data from {ukcat_csv_path}...")
        
        # Clear existing data
        logger.info("🗑️ Clearing existing UKCAT data...")
        cursor.execute("DELETE FROM ukcat_codes;")
        
        # Read and import CSV data
        imported_count = 0
        skipped_count = 0
        
        with open(ukcat_csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                try:
                    code = row['Code'].strip()
                    tag = row['tag'].strip()
                    category = row.get('Category', '').strip()
                    subcategory = row.get('Subcategory', '').strip()
                    level = int(row.get('Level', 1)) if row.get('Level') else 1
                    notes = row.get('Notes', '').strip()
                    related_icnptso = row.get('Related ICNPTSO code', '').strip()
                    regex_pattern = row.get('Regular expression', '').strip()
                    exclude_regex = row.get('Exclude regular expression', '').strip()
                    
                    # Skip empty or invalid codes
                    if not code or not tag:
                        skipped_count += 1
                        continue
                    
                    # Insert into database
                    cursor.execute("""
                        INSERT INTO ukcat_codes (
                            code, tag, category, subcategory, level, notes,
                            related_icnptso, regex_pattern, exclude_regex_pattern
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        code, tag, category, subcategory, level, notes,
                        related_icnptso, regex_pattern, exclude_regex
                    ))
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Skipping row with code {row.get('Code', 'unknown')}: {e}")
                    skipped_count += 1
                    continue
        
        # Commit the import
        conn.commit()
        
        logger.info(f"✅ UKCAT data import completed!")
        logger.info(f"📊 Records imported: {imported_count}")
        logger.info(f"⚠️ Records skipped: {skipped_count}")
        
        # Verify import
        cursor.execute("SELECT COUNT(*) FROM ukcat_codes;")
        total_count = cursor.fetchone()[0]
        logger.info(f"🗃️ Total records in database: {total_count}")
        
        # Show sample categories
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM ukcat_codes 
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 10;
        """)
        
        logger.info("📈 Top 10 categories by count:")
        for row in cursor.fetchall():
            category, count = row
            logger.info(f"   {category}: {count} codes")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

def show_ukcat_summary():
    """Show summary of imported UKCAT data."""
    
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    try:
        # Show category breakdown
        logger.info("\n📊 UKCAT Classification Summary:")
        logger.info("=" * 50)
        
        cursor.execute("""
            SELECT 
                category,
                COUNT(*) as total_codes,
                COUNT(CASE WHEN level = 1 THEN 1 END) as parent_codes,
                COUNT(CASE WHEN level > 1 THEN 1 END) as child_codes
            FROM ukcat_codes 
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category 
            ORDER BY total_codes DESC;
        """)
        
        for row in cursor.fetchall():
            category, total, parent, child = row
            logger.info(f"📂 {category}: {total} total ({parent} parent, {child} specific)")
        
        # Show code structure
        logger.info(f"\n🏗️ Code Structure Examples:")
        logger.info("-" * 30)
        
        cursor.execute("""
            SELECT code, tag, level, category 
            FROM ukcat_codes 
            WHERE category LIKE '%Health%' 
            ORDER BY code 
            LIMIT 10;
        """)
        
        for row in cursor.fetchall():
            code, tag, level, category = row
            indent = "  " * (level - 1) if level > 1 else ""
            logger.info(f"{indent}{code}: {tag}")
            
    except Exception as e:
        logger.error(f"❌ Summary query failed: {e}")
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = import_ukcat_data()
    if success:
        show_ukcat_summary()
        print("\n✅ UKCAT classification data imported successfully!")
        print("🔍 Reference table is ready for matching algorithms")
    else:
        print("\n❌ UKCAT import failed!")
        print("🔍 Check logs for details")
        exit(1)