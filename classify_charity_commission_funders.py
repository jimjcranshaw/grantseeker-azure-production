#!/usr/bin/env python3
"""
UKCAT Classification for Charity Commission Funders
==================================================

This script classifies the newly added charity commission funders using:
1. Charity number matching (primary method - most accurate)
2. Regex-based classification on name + activities/description (fallback)

Usage:
    python classify_charity_commission_funders.py
"""

import os
import csv
import json
import re
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CharityCommissionClassifier:
    """Comprehensive UKCAT classifier for charity commission funders."""
    
    def __init__(self):
        # Database connection
        db_config = {
            'host': os.getenv('DB_HOST', 'grantseeker-db.postgres.database.azure.com'),
            'user': os.getenv('DB_USER', 'grantseekeradmin'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'sslmode': 'require'
        }
        
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor()
        
        # Load data
        self.ukcat_mappings = self._load_ukcat_mappings()
        self.charity_data = self._load_charity_commission_data()
        self.ukcat_patterns = self._load_ukcat_patterns()
        
        self.stats = {
            'total_processed': 0,
            'charity_number_matched': 0,
            'regex_matched': 0,
            'no_match': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def _load_ukcat_mappings(self):
        """Load UKCAT charity number to code mappings."""
        logger.info("📁 Loading UKCAT charity number mappings...")
        
        ukcat_files = [
            'ukcat_project/data/charities_active-ukcat.csv',
            'ukcat_project/data/charities_inactive-ukcat.csv'
        ]
        
        mappings = {}
        total_records = 0
        
        for file_path in ukcat_files:
            if os.path.exists(file_path):
                logger.info(f"  Loading: {file_path}")
                try:
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
                except Exception as e:
                    logger.warning(f"  ⚠️ Error reading {file_path}: {e}")
        
        logger.info(f"✅ Loaded UKCAT mappings for {len(mappings)} charities ({total_records} records)")
        return mappings
    
    def _load_charity_commission_data(self):
        """Load charity commission CSV data for regex classification."""
        logger.info("📁 Loading charity commission data...")
        
        csv_file = 'charity_commission_funders_clean.csv'
        if not os.path.exists(csv_file):
            logger.warning(f"⚠️ CSV file not found: {csv_file}")
            return {}
        
        data = {}
        df = pd.read_csv(csv_file)
        
        for _, row in df.iterrows():
            charity_num = str(row['charity_number']).strip()
            activities = str(row.get('activities', '')).strip() if pd.notna(row.get('activities')) else ''
            description = str(row.get('description', '')).strip() if pd.notna(row.get('description')) else ''
            
            data[charity_num] = {
                'name': str(row['name']).strip(),
                'activities': activities,
                'description': description
            }
        
        logger.info(f"✅ Loaded data for {len(data)} charity commission funders")
        return data
    
    def _load_ukcat_patterns(self):
        """Load UKCAT regex patterns from database."""
        logger.info("📁 Loading UKCAT regex patterns...")
        
        patterns = {}
        
        try:
            self.cursor.execute("""
                SELECT code, tag, regex_pattern, exclude_regex_pattern, category
                FROM ukcat_codes 
                WHERE regex_pattern IS NOT NULL AND regex_pattern != ''
                ORDER BY code
            """)
            
            for row in self.cursor.fetchall():
                code, tag, include_regex, exclude_regex, category = row
                
                if include_regex:
                    try:
                        pattern = re.compile(include_regex, re.IGNORECASE)
                        patterns[code] = {
                            'tag': tag,
                            'pattern': pattern,
                            'exclude_pattern': re.compile(exclude_regex, re.IGNORECASE) if exclude_regex else None,
                            'category': category
                        }
                    except re.error as e:
                        logger.warning(f"⚠️ Invalid regex pattern for {code}: {e}")
                        continue
        except Exception as e:
            logger.error(f"❌ Error loading UKCAT patterns: {e}")
        
        logger.info(f"✅ Loaded {len(patterns)} UKCAT regex patterns")
        return patterns
    
    def classify_by_charity_number(self, charity_number):
        """Classify funder using charity number matching."""
        charity_str = str(charity_number).strip()
        if charity_str in self.ukcat_mappings:
            return self.ukcat_mappings[charity_str]
        return []
    
    def classify_by_regex(self, name, activities='', description=''):
        """Classify funder using regex patterns on name + activities + description."""
        text_to_analyze = f"{name} {activities} {description}".strip()
        
        if len(text_to_analyze) < 5:
            return []
        
        matched_codes = []
        
        for code, pattern_info in self.ukcat_patterns.items():
            try:
                if pattern_info['pattern'].search(text_to_analyze):
                    if pattern_info['exclude_pattern'] and pattern_info['exclude_pattern'].search(text_to_analyze):
                        continue
                    matched_codes.append(code)
            except Exception as e:
                logger.debug(f"⚠️ Error matching pattern {code}: {e}")
                continue
        
        return matched_codes
    
    def get_unclassified_funders(self, limit=1000):
        """Get funders that need classification."""
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
    
    def classify_funders(self, batch_size=1000):
        """Main classification process."""
        logger.info("🚀 Starting UKCAT classification for charity commission funders...")
        logger.info("=" * 60)
        
        total_processed = 0
        total_matched = 0
        
        while True:
            # Get batch of unclassified funders
            funders_batch = self.get_unclassified_funders(batch_size)
            
            if not funders_batch:
                logger.info("🎉 No more funders to classify!")
                break
            
            logger.info(f"\n📊 Processing batch of {len(funders_batch)} funders...")
            
            batch_charity_matched = 0
            batch_regex_matched = 0
            batch_no_match = 0
            
            for funder_id, name, charity_number, existing_codes in funders_batch:
                try:
                    charity_str = str(charity_number).strip()
                    
                    # Get existing codes
                    current_codes = []
                    if existing_codes:
                        try:
                            current_codes = existing_codes if isinstance(existing_codes, list) else json.loads(existing_codes)
                        except:
                            current_codes = []
                    
                    # Method 1: Try charity number matching first
                    ukcat_codes = self.classify_by_charity_number(charity_number)
                    method = "charity_number"
                    
                    # Method 2: If no match, try regex-based classification
                    if not ukcat_codes and charity_str in self.charity_data:
                        charity_info = self.charity_data[charity_str]
                        ukcat_codes = self.classify_by_regex(
                            charity_info['name'],
                            charity_info['activities'],
                            charity_info['description']
                        )
                        method = "regex"
                    
                    # Merge codes (avoid duplicates)
                    all_codes = list(set(current_codes + ukcat_codes))
                    
                    # Update database
                    self.cursor.execute("""
                        UPDATE funders 
                        SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (json.dumps(all_codes), funder_id))
                    
                    total_processed += 1
                    
                    if ukcat_codes:
                        total_matched += 1
                        if method == "charity_number":
                            batch_charity_matched += 1
                            self.stats['charity_number_matched'] += 1
                        else:
                            batch_regex_matched += 1
                            self.stats['regex_matched'] += 1
                        
                        logger.debug(f"✅ {name} ({charity_number}) -> {ukcat_codes} [{method}]")
                    else:
                        batch_no_match += 1
                        self.stats['no_match'] += 1
                        logger.debug(f"⚠️ No match: {name} ({charity_number})")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing funder {funder_id}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Commit batch
            self.conn.commit()
            
            logger.info(f"  ✅ Batch complete: {batch_charity_matched} charity-matched, {batch_regex_matched} regex-matched, {batch_no_match} no-match")
            
            # Show progress
            progress = self.get_progress()
            logger.info(f"  📊 Overall progress: {progress['classified']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
        
        self.print_final_summary(total_processed, total_matched)
    
    def get_progress(self):
        """Get current classification progress."""
        self.cursor.execute('SELECT COUNT(*) FROM funders')
        total_funders = self.cursor.fetchone()[0]
        
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE ukcat_codes IS NOT NULL 
            AND jsonb_array_length(ukcat_codes) > 0
        """)
        classified = self.cursor.fetchone()[0]
        
        return {
            'total_funders': total_funders,
            'classified': classified,
            'progress_percentage': (classified / total_funders) * 100 if total_funders > 0 else 0
        }
    
    def print_final_summary(self, total_processed, total_matched):
        """Print final classification summary."""
        progress = self.get_progress()
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 60
        
        logger.info("\n" + "=" * 60)
        logger.info("🏁 UKCAT CLASSIFICATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} minutes")
        logger.info(f"📊 Total processed: {total_processed}")
        logger.info(f"📊 Total matched: {total_matched}")
        logger.info(f"📊 Match rate: {(total_matched/total_processed*100):.1f}%" if total_processed > 0 else "N/A")
        logger.info(f"\n📊 Classification Methods:")
        logger.info(f"  - Charity number matching: {self.stats['charity_number_matched']}")
        logger.info(f"  - Regex-based matching: {self.stats['regex_matched']}")
        logger.info(f"  - No match: {self.stats['no_match']}")
        logger.info(f"  - Errors: {self.stats['errors']}")
        logger.info(f"\n📊 Final Coverage:")
        logger.info(f"  - Classified: {progress['classified']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
        logger.info("=" * 60)
        
        if progress['progress_percentage'] > 90:
            logger.info("🎉 EXCELLENT! Over 90% coverage achieved!")
        elif progress['progress_percentage'] > 75:
            logger.info("👍 GREAT! Over 75% coverage achieved!")
    
    def close(self):
        """Clean up resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    classifier = CharityCommissionClassifier()
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
