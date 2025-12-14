#!/usr/bin/env python3
"""
Charity Commission Funders Database Insertion Script
====================================================

This script inserts the processed charity commission funders into the database.
Takes the clean CSV file from process_charity_commission_funders.py and inserts
the data into the funders table with proper schema mapping.

Usage:
    python insert_charity_commission_funders.py

Requirements:
- Reads charity_commission_funders_clean.csv
- Maps data to existing database schema
- Handles missing website fields (NULL)
- Includes charity number tracking
- Sets appropriate default values
- Maintains data integrity and constraints
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import logging
import csv
from typing import List, Dict, Tuple
from datetime import datetime
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CharityCommissionInserter:
    """Database insertion handler for charity commission funders."""
    
    def __init__(self, db_config: Dict, csv_file: str):
        self.db_config = db_config
        self.csv_file = csv_file
        self.inserted_count = 0
        self.failed_count = 0
        self.errors = []
        
    def load_charity_funders_csv(self) -> List[Dict]:
        """Load the cleaned charity commission funders CSV."""
        logger.info(f"📖 Loading charity funders from: {self.csv_file}")
        
        funders = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    funder = {
                        'name': row.get('name', '').strip(),
                        'charity_number': row.get('charity_number', '').strip(),
                        'activities': row.get('activities', ''),
                        'org_id': row.get('org_id', ''),
                        'description': row.get('description', ''),
                        'source': row.get('source', 'charity_commission')
                    }
                    
                    # Validate required fields
                    if not funder['name']:
                        logger.warning(f"⚠️ Skipping row with missing name: {row}")
                        continue
                        
                    funders.append(funder)
            
            logger.info(f"✅ Loaded {len(funders)} charity funders from CSV")
            return funders
            
        except Exception as e:
            logger.error(f"❌ Failed to load CSV file: {str(e)}")
            raise
    
    def create_database_connection(self):
        """Create database connection."""
        try:
            conn = psycopg2.connect(**self.db_config)
            logger.info("✅ Database connection established")
            return conn
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {str(e)}")
            raise
    
    def check_existing_funders(self, conn, charity_numbers: List[str]) -> set:
        """Check which charity numbers already exist in database."""
        logger.info("🔍 Checking for existing funders in database...")
        
        existing_charity_numbers = set()
        
        try:
            cursor = conn.cursor()
            
            # Check by charity number (if charity_number column exists)
            placeholders = ','.join(['%s'] * len(charity_numbers))
            cursor.execute(f"""
                SELECT DISTINCT charity_number 
                FROM funders 
                WHERE charity_number IN ({placeholders})
                AND charity_number IS NOT NULL 
                AND charity_number != ''
            """, charity_numbers)
            
            for row in cursor.fetchall():
                if row[0]:  # If charity_number is not None
                    existing_charity_numbers.add(row[0])
            
            cursor.close()
            
            logger.info(f"📊 Found {len(existing_charity_numbers)} existing funders")
            return existing_charity_numbers
            
        except Exception as e:
            logger.warning(f"⚠️ Could not check existing funders: {str(e)}")
            logger.info("🔄 Proceeding with insertion without duplicate checking")
            return set()
    
    def insert_funders_batch(self, conn, funders: List[Dict], existing_charity_numbers: set) -> Tuple[int, int]:
        """Insert funders in batches with error handling."""
        logger.info(f"🚀 Starting batch insertion of {len(funders)} funders...")
        
        # Prepare data for insertion
        funders_to_insert = []
        
        for funder in funders:
            # Skip if charity number already exists
            if funder['charity_number'] and funder['charity_number'] in existing_charity_numbers:
                logger.debug(f"⏭️ Skipping existing funder: {funder['name']} (charity: {funder['charity_number']})")
                continue
            
            # Prepare database record
            db_record = (
                funder['name'],  # name
                None,  # website (NULL for charity commission funders)
                funder['description'][:1000] if funder['description'] else None,  # description (truncate to 1000 chars)
                None,  # etag
                None,  # last_modified
                funder['charity_number'] if funder['charity_number'] else None,  # charity_number
                'charity_commission'  # source/classification_type
            )
            funders_to_insert.append(db_record)
        
        if not funders_to_insert:
            logger.warning("⚠️ No new funders to insert")
            return 0, 0
        
        inserted_count = 0
        failed_count = 0
        
        try:
            cursor = conn.cursor()
            
            # Check if charity_number column exists in the funders table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'funders' 
                AND column_name = 'charity_number'
            """)
            
            has_charity_number_column = cursor.fetchone() is not None
            
            if has_charity_number_column:
                # Insert with charity_number column
                insert_query = """
                    INSERT INTO funders (
                        name, website, description, etag, last_modified, 
                        charity_number, classification_type, last_checked, created_at
                    ) VALUES %s
                    ON CONFLICT (name) DO NOTHING
                """
            else:
                # Insert without charity_number column
                insert_query = """
                    INSERT INTO funders (
                        name, website, description, etag, last_modified, 
                        classification_type, last_checked, created_at
                    ) VALUES %s
                    ON CONFLICT (name) DO NOTHING
                """
            
            # Insert in batches of 1000 to avoid memory issues
            batch_size = 1000
            for i in range(0, len(funders_to_insert), batch_size):
                batch = funders_to_insert[i:i + batch_size]
                
                try:
                    execute_values(cursor, insert_query, batch)
                    conn.commit()
                    inserted_count += len(batch)
                    logger.info(f"✅ Inserted batch {i//batch_size + 1}: {len(batch)} funders (Total: {inserted_count})")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"❌ Batch insertion failed: {str(e)}")
                    failed_count += len(batch)
                    self.errors.append(f"Batch {i//batch_size + 1}: {str(e)}")
            
            cursor.close()
            
        except Exception as e:
            logger.error(f"❌ Database insertion failed: {str(e)}")
            failed_count = len(funders_to_insert)
            self.errors.append(f"General insertion error: {str(e)}")
        
        return inserted_count, failed_count
    
    def generate_insertion_report(self, total_funders: int, inserted_count: int, failed_count: int) -> str:
        """Generate a detailed insertion report."""
        existing_count = total_funders - inserted_count - failed_count
        
        report = f"""
CHARITY COMMISSION FUNDERS DATABASE INSERTION REPORT
===================================================

Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Source File: {self.csv_file}

INSERTION SUMMARY:
==================
Total Funders Processed: {total_funders:,}
Successfully Inserted: {inserted_count:,}
Failed Insertions: {failed_count:,}
Already Existing: {existing_count:,}
Success Rate: {(inserted_count/total_funders*100):.1f}%

DATA QUALITY CHECKS:
====================
- All inserted funders have names: ✅
- All inserted funders have NULL websites: ✅
- Charity numbers included where available: ✅
- Descriptions truncated to 1000 chars: ✅
- Source classification set: ✅

ERRORS ENCOUNTERED:
===================
"""
        
        if self.errors:
            for i, error in enumerate(self.errors, 1):
                report += f"{i}. {error}\n"
        else:
            report += "No errors encountered! 🎉\n"
        
        report += f"""
DATABASE IMPACT:
================
- New funders added to database: {inserted_count:,}
- Total funder database size increased by: {inserted_count:,}
- Charity commission integration: {'✅ COMPLETE' if inserted_count > 0 else '❌ NO NEW DATA'}

NEXT STEPS:
===========
1. Verify insertion in database
2. Apply UKCAT classification to new funders
3. Update matching algorithms
4. Test end-to-end functionality

{'🚀 READY FOR UKCAT CLASSIFICATION!' if inserted_count > 0 else '⚠️ NO NEW FUNDERS TO CLASSIFY'}
"""
        
        return report
    
    def run_insertion(self) -> str:
        """Main insertion process."""
        logger.info("🚀 Starting charity commission funders database insertion...")
        
        try:
            # Step 1: Load charity funders from CSV
            funders = self.load_charity_funders_csv()
            
            if not funders:
                logger.warning("⚠️ No funders to insert")
                return "No funders found in CSV file"
            
            # Step 2: Create database connection
            conn = self.create_database_connection()
            
            # Step 3: Check for existing funders
            charity_numbers = [f['charity_number'] for f in funders if f['charity_number']]
            existing_charity_numbers = self.check_existing_funders(conn, charity_numbers)
            
            # Step 4: Insert funders
            inserted_count, failed_count = self.insert_funders_batch(conn, funders, existing_charity_numbers)
            
            # Step 5: Close connection
            conn.close()
            logger.info("✅ Database connection closed")
            
            # Step 6: Generate report
            report = self.generate_insertion_report(len(funders), inserted_count, failed_count)
            
            logger.info("🎉 Database insertion completed!")
            return report
            
        except Exception as e:
            logger.error(f"❌ Insertion process failed: {str(e)}")
            raise


def main():
    """Main execution function."""
    # Configuration
    CSV_FILE = "charity_commission_funders_clean.csv"
    
    # Database configuration (load from environment or config)
    db_config = {
        'host': os.getenv('DB_HOST', 'your-server.postgres.database.azure.com'),
        'user': os.getenv('DB_USER', 'your-admin-user'),
        'password': os.getenv('DB_PASSWORD', 'your-password'),
        'database': os.getenv('DB_NAME', 'postgres'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'sslmode': 'require'
    }
    
    try:
        # Check if CSV file exists
        if not Path(CSV_FILE).exists():
            raise FileNotFoundError(f"CSV file not found: {CSV_FILE}")
        
        # Create inserter and run
        inserter = CharityCommissionInserter(db_config, CSV_FILE)
        report = inserter.run_insertion()
        
        # Print report
        print(report)
        
        # Save report to file
        report_filename = f"charity_commission_insertion_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, 'w') as f:
            f.write(report)
        
        print(f"\n📄 Report saved to: {report_filename}")
        
    except Exception as e:
        logger.error(f"❌ Main execution failed: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())