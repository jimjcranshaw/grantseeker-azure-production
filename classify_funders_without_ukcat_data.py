#!/usr/bin/env python3
"""
Classify Funders Without UKCAT Data Using Regex Patterns
========================================================

Uses UKCAT regex patterns to classify funders that don't have UKCAT data
by matching patterns against their name, activities, and description.

This uses the open-source UKCAT classification system with regex patterns
to assign codes to funders that aren't in the UKCAT database.
"""

import os
import json
import re
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RegexUKCATClassifier:
    """Classify funders using UKCAT regex patterns."""
    
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
        
        # Load UKCAT patterns from database
        self.ukcat_patterns = self._load_ukcat_patterns()
        
        # Load charity commission data for activities/description
        self.charity_data = self._load_charity_commission_data()
        
        self.stats = {
            'processed': 0,
            'classified': 0,
            'no_match': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def _load_ukcat_patterns(self):
        """Load UKCAT regex patterns from database."""
        logger.info("📁 Loading UKCAT regex patterns from database...")
        
        patterns = {}
        
        try:
            self.cursor.execute("""
                SELECT code, tag, regex_pattern, exclude_regex_pattern, category
                FROM ukcat_codes 
                WHERE regex_pattern IS NOT NULL 
                AND regex_pattern != ''
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
    
    def _load_charity_commission_data(self):
        """Load charity commission CSV data for activities/description."""
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
    
    def classify_funder(self, name: str, activities: str = '', description: str = '') -> list:
        """Classify a funder using regex patterns."""
        if not name:
            return []
        
        # Combine name, activities, and description for analysis
        text_to_analyze = f"{name} {activities} {description}".strip()
        
        if len(text_to_analyze) < 5:
            return []
        
        matched_codes = []
        
        for code, pattern_info in self.ukcat_patterns.items():
            try:
                # Check if pattern matches
                if pattern_info['pattern'].search(text_to_analyze):
                    # Check exclude pattern if present
                    if pattern_info['exclude_pattern'] and pattern_info['exclude_pattern'].search(text_to_analyze):
                        continue
                    
                    matched_codes.append(code)
            
            except Exception as e:
                logger.debug(f"⚠️ Error matching pattern {code}: {e}")
                continue
        
        return matched_codes
    
    def classify_funders_without_ukcat_data(self, batch_size=1000):
        """Classify funders that don't have UKCAT data."""
        logger.info("🚀 Starting regex-based classification for funders without UKCAT data...")
        logger.info("=" * 60)
        
        # Get funders without UKCAT data
        self.cursor.execute("""
            SELECT id, name, charity_number, ukcat_codes
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
            AND (ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb)
            ORDER BY id
        """)
        
        funders = self.cursor.fetchall()
        logger.info(f"📊 Found {len(funders)} funders without UKCAT data")
        
        if not funders:
            logger.info("✅ No funders need classification")
            return
        
        classified_count = 0
        no_match_count = 0
        
        # Process in batches
        for i in range(0, len(funders), batch_size):
            batch = funders[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"\n📦 Processing batch {batch_num} ({len(batch)} funders)...")
            
            batch_classified = 0
            batch_no_match = 0
            
            for funder_id, name, charity_number, existing_codes in batch:
                try:
                    charity_str = str(charity_number).strip()
                    
                    # Get activities/description from charity commission data
                    activities = ''
                    description = ''
                    if charity_str in self.charity_data:
                        charity_info = self.charity_data[charity_str]
                        activities = charity_info.get('activities', '')
                        description = charity_info.get('description', '')
                    
                    # Classify using regex patterns
                    matched_codes = self.classify_funder(name, activities, description)
                    
                    if matched_codes:
                        # Get existing codes
                        current_codes = []
                        if existing_codes:
                            try:
                                current_codes = existing_codes if isinstance(existing_codes, list) else json.loads(existing_codes)
                            except:
                                current_codes = []
                        
                        # Merge codes (avoid duplicates)
                        all_codes = list(set(current_codes + matched_codes))
                        
                        # Update database
                        self.cursor.execute("""
                            UPDATE funders 
                            SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (json.dumps(all_codes), funder_id))
                        
                        batch_classified += 1
                        classified_count += 1
                        logger.debug(f"  ✅ {name[:50]}: {matched_codes}")
                    else:
                        batch_no_match += 1
                        no_match_count += 1
                    
                    self.stats['processed'] += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error processing funder {funder_id}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Commit batch
            self.conn.commit()
            
            logger.info(f"  Batch {batch_num} complete: {batch_classified} classified, {batch_no_match} no match")
            
            # Show progress
            progress_pct = (self.stats['processed'] / len(funders)) * 100 if funders else 0
            logger.info(f"  Overall progress: {self.stats['processed']}/{len(funders)} ({progress_pct:.1f}%)")
        
        # Final summary
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 60
        
        logger.info("\n" + "=" * 60)
        logger.info("🏁 REGEX-BASED CLASSIFICATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} minutes")
        logger.info(f"📊 Total processed: {self.stats['processed']}")
        logger.info(f"📊 Successfully classified: {classified_count}")
        logger.info(f"📊 No match found: {no_match_count}")
        logger.info(f"📊 Errors: {self.stats['errors']}")
        logger.info(f"📊 Success rate: {(classified_count/self.stats['processed']*100):.1f}%" if self.stats['processed'] > 0 else "N/A")
        logger.info("=" * 60)
    
    def close(self):
        """Clean up resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    """Main execution."""
    classifier = RegexUKCATClassifier()
    try:
        classifier.classify_funders_without_ukcat_data()
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
