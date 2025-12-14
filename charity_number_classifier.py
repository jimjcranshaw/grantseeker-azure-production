#!/usr/bin/env python3
"""
Charity Number UKCAT Classifier
==============================

This classifier matches funders to UKCAT classifications based on charity numbers.
This is the correct approach - UKCAT has already classified charities by their charity numbers.
"""

import os
import csv
import json
from dotenv import load_dotenv
import psycopg2
from datetime import datetime
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CharityNumberClassifier:
    def __init__(self):
        # Set up database URL from individual components
        if not os.getenv('DATABASE_URL'):
            os.environ['DATABASE_URL'] = (
                f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}?"
                f"sslmode={os.getenv('DB_SSLMODE', 'require')}"
            )
        
        self.db_url = os.getenv('DATABASE_URL')
        self.conn = psycopg2.connect(self.db_url)
        self.cursor = self.conn.cursor()
        self.ukcat_mappings = {}  # charity_number -> [ukcat_codes]
        self.stats = {
            'total_funders': 0,
            'with_charity_numbers': 0,
            'matched_in_ukcat': 0,
            'classified': 0,
            'start_time': datetime.now()
        }
        
    def load_ukcat_mappings(self):
        """Load UKCAT charity number to code mappings from CSV files."""
        ukcat_files = [
            'ukcat_project/data/charities_active-ukcat.csv',
            'ukcat_project/data/charities_inactive-ukcat.csv'
        ]
        
        mappings = {}
        total_records = 0
        
        for file_path in ukcat_files:
            if os.path.exists(file_path):
                logger.info(f"📁 Loading UKCAT data from: {file_path}")
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        org_id = row['org_id']
                        ukcat_code = row['ukcat_code']
                        
                        # Convert "GB-CHC-1000001" to "1000001"
                        if org_id.startswith('GB-CHC-'):
                            charity_number = org_id.replace('GB-CHC-', '')
                            
                            if charity_number not in mappings:
                                mappings[charity_number] = []
                            
                            if ukcat_code not in mappings[charity_number]:
                                mappings[charity_number].append(ukcat_code)
                            
                            total_records += 1
        
        self.ukcat_mappings = mappings
        logger.info(f"📊 Loaded UKCAT mappings for {len(mappings)} charities ({total_records} records)")
        return mappings
    
    def get_funders_to_classify(self, limit=1000):
        """Get funders that have charity numbers but need classification."""
        self.cursor.execute("""
            SELECT id, name, charity_number, ukcat_codes
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
            AND (ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb)
            ORDER BY id
            LIMIT %s
        """, (limit,))
        
        return self.cursor.fetchall()
    
    def get_classification_progress(self):
        """Get current classification progress."""
        self.cursor.execute('SELECT COUNT(*) FROM funders')
        total_funders = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM funders WHERE charity_number IS NOT NULL AND charity_number != ''")
        with_charity_numbers = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM funders WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0')
        classified = self.cursor.fetchone()[0]
        
        self.stats['total_funders'] = total_funders
        self.stats['with_charity_numbers'] = with_charity_numbers
        self.stats['classified'] = classified
        
        return {
            'total_funders': total_funders,
            'with_charity_numbers': with_charity_numbers,
            'classified': classified,
            'progress_percentage': (classified / total_funders) * 100 if total_funders > 0 else 0,
            'charity_number_coverage': (with_charity_numbers / total_funders) * 100 if total_funders > 0 else 0
        }
    
    def classify_funders(self, batch_size=1000):
        """Classify funders based on charity number matching."""
        logger.info("🚀 Starting charity number-based UKCAT classification...")
        
        # Load UKCAT mappings
        self.load_ukcat_mappings()
        
        total_processed = 0
        total_matched = 0
        
        while True:
            # Get batch of funders to classify
            funders_batch = self.get_funders_to_classify(batch_size)
            
            if not funders_batch:
                logger.info("🎉 No more funders to classify!")
                break
            
            logger.info(f"📊 Processing batch of {len(funders_batch)} funders...")
            
            # Process each funder
            for funder_id, name, charity_number, existing_codes in funders_batch:
                try:
                    # Convert charity_number to string for lookup
                    charity_str = str(charity_number).strip()
                    
                    if charity_str in self.ukcat_mappings:
                        ukcat_codes = self.ukcat_mappings[charity_str]
                        
                        # Get existing codes
                        current_codes = []
                        if existing_codes:
                            try:
                                current_codes = existing_codes if isinstance(existing_codes, list) else []
                            except:
                                current_codes = []
                        
                        # Merge codes (avoid duplicates)
                        all_codes = list(set(current_codes + ukcat_codes))
                        
                        # Update database
                        self.cursor.execute("""
                            UPDATE funders 
                            SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (json.dumps(all_codes), funder_id))
                        
                        total_matched += 1
                        logger.debug(f"✅ Matched {name} (charity {charity_str}) -> {ukcat_codes}")
                    else:
                        # No UKCAT mapping found - mark as processed with empty array
                        # This prevents infinite loop on funders without UKCAT data
                        self.cursor.execute("""
                            UPDATE funders 
                            SET ukcat_codes = '[]'::jsonb, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (funder_id,))
                        logger.debug(f"⚠️ No UKCAT data for {name} (charity {charity_str}) - marked as processed")
                    
                    total_processed += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error processing funder {funder_id}: {e}")
                    continue
            
            # Commit batch
            self.conn.commit()
            logger.info(f"📊 Batch completed: {total_processed} processed, {total_matched} matched")
            
            # Show progress
            progress = self.get_classification_progress()
            logger.info(f"📊 Progress: {progress['classified']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
            
            # Brief pause
            import time
            time.sleep(1)
        
        self.print_final_summary(total_processed, total_matched)
    
    def print_final_summary(self, total_processed, total_matched):
        """Print final classification summary."""
        progress = self.get_classification_progress()
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 60
        
        logger.info("=" * 60)
        logger.info("🏁 CHARITY NUMBER CLASSIFICATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} minutes")
        logger.info(f"📊 Total processed: {total_processed}")
        logger.info(f"📊 Total matched: {total_matched}")
        logger.info(f"📊 Match rate: {(total_matched/total_processed*100):.1f}%" if total_processed > 0 else "N/A")
        logger.info(f"📊 UKCAT charity mappings loaded: {len(self.ukcat_mappings)}")
        logger.info(f"📊 Final classification coverage: {progress['classified']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
        logger.info(f"📊 Charity number coverage: {progress['with_charity_numbers']}/{progress['total_funders']} ({progress['charity_number_coverage']:.1f}%)")
        
        if progress['progress_percentage'] > 50:
            logger.info("🎉 EXCELLENT! More than 50% coverage achieved!")
        elif progress['progress_percentage'] > 25:
            logger.info("👍 GREAT! More than 25% coverage achieved!")
        
        logger.info("=" * 60)
    
    def close(self):
        """Clean up resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    classifier = CharityNumberClassifier()
    try:
        classifier.classify_funders()
    except KeyboardInterrupt:
        logger.info("🛑 Classification interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        classifier.close()

if __name__ == "__main__":
    main()