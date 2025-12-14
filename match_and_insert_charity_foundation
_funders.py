#!/usr/bin/env python3
"""
Match and Insert Charity Foundation Funders
============================================

This script matches charity data from charity_foundation.csv against the Azure 
PostgreSQL database funders table and inserts new records for charities not 
already in the database.

Usage:
    python match_and_insert_charity_foundation_funders.py

Requirements:
- Reads ukcat_project/charity_foundation.csv
- Extracts charity numbers, names, and websites from CSV
- Queries funders table for existing charity numbers
- Inserts new funders with charity_number tracking
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import logging
import json
import os
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': os.getenv('DB_PORT', '5432'),
    'sslmode': 'require'
}

class CharityFoundationMatcher:
    """Match and insert charity foundation data into the database."""
    
    def __init__(self, csv_file: str, db_config: Dict):
        self.csv_file = csv_file
        self.db_config = db_config
        self.inserted_count = 0
        self.skipped_count = 0
        self.errors = []
        
    def parse_contact_info(self, contact_info_str: str) -> Optional[str]:
        """
        Parse contact_info JSON string to extract website URL.
        
        Args:
            contact_info_str: JSON string containing contact information
            
        Returns:
            Website URL or None if not found/invalid
        """
        try:
            if pd.isna(contact_info_str) or not contact_info_str:
                return None
                
            # Parse JSON string
            contact_data = json.loads(contact_info_str)
            
            # Extract web field
            website = contact_data.get('web', '').strip()
            
            # Clean up website URL
            if website:
                # Ensure has protocol
                if not website.startswith(('http://', 'https://')):
                    website = 'https://' + website
                return website
            
            return None
            
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logger.debug(f"Could not parse contact_info: {str(e)[:100]}")
            return None
    
    def load_charity_foundation_csv(self) -> List[Dict]:
        """
        Load and parse charity_foundation.csv file.
        
        Returns:
            List of charity dictionaries
        """
        logger.info(f"📖 Loading charity foundation data from: {self.csv_file}")
        
        try:
            # Read CSV file
            df = pd.read_csv(self.csv_file)
            logger.info(f"✅ Loaded {len(df)} rows from CSV")
            
            charities = []
            
            for index, row in df.iterrows():
                # Extract charity number from 'id' column
                charity_number = str(row.get('id', '')).strip()
                if not charity_number:
                    logger.warning(f"⚠️ Skipping row {index}: missing charity number")
                    continue
                
                # Extract organization name
                org_name = str(row.get('organization_name', '')).strip()
                if not org_name:
                    logger.warning(f"⚠️ Skipping charity {charity_number}: missing organization name")
                    continue
                
                # Parse website from contact_info
                contact_info = row.get('contact_info', '')
                website = self.parse_contact_info(contact_info)
                
                charity_data = {
                    'charity_number': charity_number,
                    'name': org_name,
                    'website': website
                }
                
                charities.append(charity_data)
            
            logger.info(f"✅ Parsed {len(charities)} charities from CSV")
            logger.info(f"📊 Charities with websites: {sum(1 for c in charities if c['website'])}")
            logger.info(f"📊 Charities without websites: {sum(1 for c in charities if not c['website'])}")
            
            return charities
            
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
    
    def get_existing_charity_numbers(self, conn) -> set:
        """
        Get all existing charity numbers from the funders table.
        
        Args:
            conn: Database connection
            
        Returns:
            Set of existing charity numbers
        """
        logger.info("🔍 Querying existing charity numbers from database...")
        
        try:
            cursor = conn.cursor()
            
            # Query all charity numbers from funders table
            cursor.execute("""
                SELECT DISTINCT charity_number 
                FROM funders 
                WHERE charity_number IS NOT NULL 
                AND charity_number != ''
            """)
            
            existing_numbers = set()
            for row in cursor.fetchall():
                if row[0]:
                    existing_numbers.add(str(row[0]))
            
            cursor.close()
            
            logger.info(f"📊 Found {len(existing_numbers)} existing charity numbers in database")
            return existing_numbers
            
        except Exception as e:
            logger.error(f"❌ Failed to query existing charity numbers: {str(e)}")
            raise
    
    def find_new_charities(self, charities: List[Dict], existing_numbers: set) -> List[Dict]:
        """
        Find charities that are NOT in the database.
        
        Args:
            charities: List of charity dictionaries from CSV
            existing_numbers: Set of existing charity numbers from database
            
        Returns:
            List of new charities to insert
        """
        logger.info("🔎 Comparing charity numbers to find new records...")
        
        new_charities = []
        
        for charity in charities:
            charity_number = charity['charity_number']
            
            if charity_number not in existing_numbers:
                new_charities.append(charity)
            else:
                self.skipped_count += 1
                logger.debug(f"⏭️  Skipping existing charity: {charity['name']} ({charity_number})")
        
        logger.info(f"✨ Found {len(new_charities)} new charities to insert")
        logger.info(f"⏭️  Skipped {self.skipped_count} existing charities")
        
        return new_charities
    
    def insert_new_charities(self, conn, new_charities: List[Dict]) -> int:
        """
        Insert new charities into the funders table.
        
        Args:
            conn: Database connection
            new_charities: List of charity dictionaries to insert
            
        Returns:
            Number of successfully inserted records
        """
        if not new_charities:
            logger.info("ℹ️  No new charities to insert")
            return 0
        
        logger.info(f"🚀 Inserting {len(new_charities)} new charities into database...")
        
        try:
            cursor = conn.cursor()
            
            # Prepare data for batch insertion
            insert_data = []
            for charity in new_charities:
                record = (
                    charity['name'],                    # name
                    charity['website'],                 # website
                    None,                               # description
                    None,                               # etag
                    None,                               # last_modified
                    charity['charity_number']           # charity_number
                )
                insert_data.append(record)
            
            # Batch insert using execute_values for efficiency
            insert_query = """
                INSERT INTO funders 
                (name, website, description, etag, last_modified, charity_number)
                VALUES %s
            """
            
            execute_values(cursor, insert_query, insert_data)
            conn.commit()
            
            self.inserted_count = len(insert_data)
            cursor.close()
            
            logger.info(f"✅ Successfully inserted {self.inserted_count} new charity records")
            return self.inserted_count
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Failed to insert charities: {str(e)}")
            raise
    
    def show_sample_insertions(self, new_charities: List[Dict], limit: int = 10):
        """
        Display sample of new records that were/will be inserted.
        
        Args:
            new_charities: List of new charity dictionaries
            limit: Number of samples to show
        """
        if not new_charities:
            return
        
        logger.info(f"\n📋 Sample of new records (showing up to {limit}):")
        logger.info("=" * 80)
        
        for i, charity in enumerate(new_charities[:limit], 1):
            website_display = charity['website'] if charity['website'] else "(no website)"
            logger.info(f"{i}. {charity['name']}")
            logger.info(f"   Charity Number: {charity['charity_number']}")
            logger.info(f"   Website: {website_display}")
            logger.info("-" * 80)
        
        if len(new_charities) > limit:
            logger.info(f"... and {len(new_charities) - limit} more")
    
    def run(self):
        """Execute the matching and insertion process."""
        logger.info("=" * 80)
        logger.info("🎯 CHARITY FOUNDATION MATCHER AND INSERTER")
        logger.info("=" * 80)
        
        try:
            # Step 1: Load charity data from CSV
            charities = self.load_charity_foundation_csv()
            
            # Step 2: Connect to database
            conn = self.create_database_connection()
            
            # Step 3: Get existing charity numbers from database
            existing_numbers = self.get_existing_charity_numbers(conn)
            
            # Step 4: Find charities NOT in database
            new_charities = self.find_new_charities(charities, existing_numbers)
            
            # Step 5: Show sample of what will be inserted
            self.show_sample_insertions(new_charities, limit=10)
            
            # Step 6: Insert new charities
            if new_charities:
                self.insert_new_charities(conn, new_charities)
            
            # Close database connection
            conn.close()
            logger.info("✅ Database connection closed")
            
            # Final summary
            logger.info("\n" + "=" * 80)
            logger.info("📊 FINAL SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total charities in CSV: {len(charities)}")
            logger.info(f"Existing in database: {self.skipped_count}")
            logger.info(f"New records inserted: {self.inserted_count}")
            logger.info(f"Errors encountered: {len(self.errors)}")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Process failed: {str(e)}")
            return False


def main():
    """Main execution function."""
    # Path to charity foundation CSV
    csv_file = 'ukcat_project/charity_foundation.csv'
    
    # Check if file exists
    if not os.path.exists(csv_file):
        logger.error(f"❌ CSV file not found: {csv_file}")
        return
    
    # Create matcher and run
    matcher = CharityFoundationMatcher(csv_file, DB_CONFIG)
    success = matcher.run()
    
    if success:
        logger.info("\n✨ Process completed successfully!")
    else:
        logger.error("\n❌ Process completed with errors")


if __name__ == "__main__":
    main()
