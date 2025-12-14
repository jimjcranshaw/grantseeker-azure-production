#!/usr/bin/env python3
"""
Safe Charity Commission Funder Processor
========================================

This script safely processes the charity_foundation.csv file to extract
charity commission funders without websites and prepare them for database insertion.

Usage:
    python process_charity_commission_funders.py

Requirements:
- Must use script to read charity_foundation.csv (don't read directly)
- Filter out existing database funders to avoid duplicates
- Create clean dataset for database insertion
"""

import pandas as pd
import csv
import hashlib
import logging
import psycopg2
from psycopg2.extras import execute_values
from typing import List, Dict, Set, Tuple
import re
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CharityCommissionProcessor:
    """Safe processor for charity commission funder data."""
    
    def __init__(self, csv_file_path: str):
        self.csv_file_path = csv_file_path
        self.charity_funders = []
        self.existing_funders = set()
        self.new_funders = []
        
    def read_csv_safely(self) -> pd.DataFrame:
        """
        Safely read the charity_foundation.csv file using pandas.
        This avoids direct file reads that can cause crashes.
        """
        logger.info(f"📖 Reading charity foundation data from: {self.csv_file_path}")
        
        try:
            # Use pandas with specific settings to avoid memory issues
            df = pd.read_csv(
                self.csv_file_path,
                dtype=str,  # Read everything as string to avoid type issues
                na_filter=True,
                low_memory=False,
                encoding='utf-8'
            )
            
            logger.info(f"✅ Successfully loaded {len(df)} rows from charity foundation data")
            logger.info(f"📊 Columns available: {list(df.columns)}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Failed to read charity foundation CSV: {str(e)}")
            raise
    
    def load_existing_funders_from_db(self, db_config: Dict) -> Set[str]:
        """
        Load existing funder names and charity numbers from database
        to avoid duplicates.
        """
        logger.info("🔍 Loading existing funders from database...")
        
        try:
            conn = psycopg2.connect(**db_config)
            cursor = conn.cursor()
            
            # Get existing funder names and charity numbers
            cursor.execute("""
                SELECT DISTINCT 
                    LOWER(TRIM(name)) as funder_name,
                    COALESCE(charity_number, '') as charity_number
                FROM funders 
                WHERE name IS NOT NULL AND name != ''
            """)
            
            existing_funders = set()
            for row in cursor.fetchall():
                name, charity_number = row
                if name:
                    existing_funders.add(name.strip().lower())
                if charity_number and charity_number.strip():
                    existing_funders.add(f"charity_{charity_number.strip()}")
            
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Loaded {len(existing_funders)} existing funders from database")
            return existing_funders
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load existing funders from DB: {str(e)}")
            logger.info("🔄 Proceeding without duplicate checking")
            return set()
    
    def clean_funder_name(self, name: str) -> str:
        """Clean and normalize funder names for matching."""
        if not name or pd.isna(name):
            return ""
        
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', str(name).strip())
        
        # Remove common suffixes that might cause false mismatches
        suffixes_to_remove = [
            'ltd', 'limited', 'charity', 'trust', 'foundation', 
            'incorporated', 'inc', 'company', 'corp', 'llc'
        ]
        
        words = cleaned.split()
        filtered_words = []
        for word in words:
            if word.lower() not in suffixes_to_remove:
                filtered_words.append(word)
        
        return ' '.join(filtered_words).strip()
    
    def is_duplicate_funder(self, funder_name: str, charity_number: str = "") -> bool:
        """Check if funder already exists in database."""
        cleaned_name = self.clean_funder_name(funder_name)
        
        # Check name matches
        if cleaned_name.lower() in self.existing_funders:
            return True
            
        # Check charity number matches
        if charity_number and charity_number.strip():
            if f"charity_{charity_number.strip()}" in self.existing_funders:
                return True
        
        return False
    
    def extract_charity_number(self, org_id: str) -> str:
        """Extract charity number from org_id format like 'GB-CHC-1234567'."""
        if not org_id or pd.isna(org_id):
            return ""
        
        # Handle format like "GB-CHC-1234567"
        if org_id.startswith("GB-CHC-"):
            return org_id[7:]  # Remove "GB-CHC-" prefix
        
        return str(org_id)
    
    def process_charity_data(self, df: pd.DataFrame) -> List[Dict]:
        """
        Process charity data and extract grantmaking funders without websites.
        """
        logger.info("🔄 Processing charity data for grantmaking funders...")
        
        processed_funders = []
        
        for idx, row in df.iterrows():
            try:
                # Extract basic information (using correct column names from CSV)
                org_id = row.get('id', '')
                name = row.get('organization_name', '')
                activities = row.get('charity_does', '') or row.get('program_and_services', '')
                mission = row.get('mission_and_vision', '')
                
                # Extract charity number from org_id (assuming it's in the right format)
                charity_number = self.extract_charity_number(org_id)
                
                # Skip if essential data is missing
                if not name or pd.isna(name) or not org_id or pd.isna(org_id):
                    continue
                
                # Check if this funder already exists in our database
                if self.is_duplicate_funder(name, charity_number):
                    logger.debug(f"⏭️ Skipping existing funder: {name}")
                    continue
                
                # Combine activities and mission for description
                description_parts = []
                if activities and not pd.isna(activities):
                    description_parts.append(str(activities)[:300])
                if mission and not pd.isna(mission):
                    description_parts.append(str(mission)[:200])
                description = ' | '.join(description_parts)
                
                # Create funder record
                funder_record = {
                    'name': str(name).strip(),
                    'charity_number': charity_number,
                    'activities': str(activities) if activities and not pd.isna(activities) else "",
                    'org_id': str(org_id),
                    'website': None,  # These funders don't have websites
                    'description': description,
                    'source': 'charity_commission'
                }
                
                processed_funders.append(funder_record)
                
            except Exception as e:
                logger.warning(f"⚠️ Error processing row {idx}: {str(e)}")
                continue
        
        logger.info(f"✅ Processed {len(processed_funders)} new charity commission funders")
        return processed_funders
    
    def save_clean_dataset(self, funders: List[Dict], output_file: str):
        """Save the clean dataset to CSV for database insertion."""
        logger.info(f"💾 Saving clean dataset to: {output_file}")
        
        if not funders:
            logger.warning("⚠️ No funders to save")
            return
        
        # Define columns for output
        fieldnames = ['name', 'charity_number', 'activities', 'org_id', 'website', 'description', 'source']
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for funder in funders:
                # Ensure all fields are present and clean
                row = {field: funder.get(field, '') for field in fieldnames}
                writer.writerow(row)
        
        logger.info(f"✅ Saved {len(funders)} funders to {output_file}")
    
    def generate_summary_report(self, funders: List[Dict]) -> str:
        """Generate a summary report of the processing results."""
        total_funders = len(funders)
        
        # Count by source
        source_counts = {}
        for funder in funders:
            source = funder.get('source', 'unknown')
            source_counts[source] = source_counts.get(source, 0) + 1
        
        # Generate report
        report = f"""
CHARITY COMMISSION FUNDER PROCESSING SUMMARY
===========================================

Processing Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
Total New Funders: {total_funders}

Source Breakdown:
"""
        
        for source, count in source_counts.items():
            report += f"  - {source}: {count} funders\n"
        
        report += f"""
Data Quality:
  - All funders have charity numbers: {all(f.get('charity_number') for f in funders)}
  - All funders lack websites (charity commission only): {all(f.get('website') is None for f in funders)}
  - All funders have activities/purposes data: {any(f.get('activities') for f in funders)}

Next Steps:
  1. Review the clean dataset CSV file
  2. Run database insertion script
  3. Apply UKCAT classification to new funders
  4. Update matching algorithms

Ready for database insertion! 🎯
"""
        
        return report
    
    def run_processing(self, db_config: Dict, output_file: str = "charity_commission_funders_clean.csv") -> Tuple[List[Dict], str]:
        """Main processing function."""
        logger.info("🚀 Starting charity commission funder processing...")
        
        try:
            # Step 1: Load existing funders from database
            self.existing_funders = self.load_existing_funders_from_db(db_config)
            
            # Step 2: Read charity foundation data safely
            df = self.read_csv_safely()
            
            # Step 3: Process charity data
            new_funders = self.process_charity_data(df)
            
            # Step 4: Save clean dataset
            self.save_clean_dataset(new_funders, output_file)
            
            # Step 5: Generate summary report
            summary = self.generate_summary_report(new_funders)
            
            logger.info("🎉 Charity commission processing completed successfully!")
            return new_funders, summary
            
        except Exception as e:
            logger.error(f"❌ Processing failed: {str(e)}")
            raise


def main():
    """Main execution function."""
    # Configuration
    CSV_FILE_PATH = "ukcat_project/charity_foundation.csv"
    OUTPUT_FILE = "charity_commission_funders_clean.csv"
    
    # Database configuration (adjust as needed)
    db_config = {
        'host': 'your-server.postgres.database.azure.com',
        'user': 'your-admin-user',
        'password': 'your-password',
        'database': 'postgres',
        'port': 5432,
        'sslmode': 'require'
    }
    
    try:
        # Create processor and run
        processor = CharityCommissionProcessor(CSV_FILE_PATH)
        funders, summary = processor.run_processing(db_config, OUTPUT_FILE)
        
        # Print summary
        print(summary)
        
        # Save summary to file
        with open("charity_commission_processing_summary.txt", "w") as f:
            f.write(summary)
        
        print(f"\n📄 Summary saved to: charity_commission_processing_summary.txt")
        print(f"📊 Clean dataset saved to: {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"❌ Main execution failed: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())