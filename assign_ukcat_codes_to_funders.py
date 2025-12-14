#!/usr/bin/env python3
"""
Assign UKCAT Codes to Existing Funders
====================================

This script processes existing funders and assigns UKCAT classification codes
based on their names and descriptions using the UKCAT regex patterns.

Usage:
    python assign_ukcat_codes_to_funders.py [--batch-size N] [--dry-run]

Author: Grant Seeker UKCAT Integration
Date: December 2025
"""

import re
import os
import psycopg2
from dotenv import load_dotenv
import logging
import argparse
from typing import List, Dict, Set
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UKCATClassifier:
    """UKCAT classification system for assigning codes to funders."""
    
    def __init__(self, db_connection):
        self.conn = db_connection
        self.cursor = db_connection.cursor()
        self.ukcat_patterns = self._load_ukcat_patterns()
        
    def _load_ukcat_patterns(self) -> Dict[str, Dict]:
        """Load UKCAT regex patterns from database."""
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
                    # Compile regex pattern
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
            logger.error(f"❌ Failed to load UKCAT patterns: {e}")
            
        logger.info(f"📊 Loaded {len(patterns)} UKCAT classification patterns")
        return patterns
    
    def classify_funder(self, funder_name: str, funder_description: str = "") -> List[str]:
        """Classify a funder and return matching UKCAT codes."""
        if not funder_name:
            return []
            
        # Combine name and description for analysis
        text_to_analyze = f"{funder_name} {funder_description}".strip()
        
        # Skip if text is too short
        if len(text_to_analyze) < 5:
            return []
            
        matched_codes = []
        
        for code, pattern_info in self.ukcat_patterns.items():
            try:
                # Check if pattern matches
                if pattern_info['pattern'].search(text_to_analyze):
                    # Check exclude pattern if present
                    if pattern_info['exclude_pattern'] and pattern_info['exclude_pattern'].search(text_to_analyze):
                        logger.debug(f"  Excluded {code} due to exclude pattern")
                        continue
                    
                    matched_codes.append(code)
                    logger.debug(f"  ✓ Matched: {code} ({pattern_info['tag']})")
                    
            except Exception as e:
                logger.warning(f"⚠️ Error matching pattern {code}: {e}")
                continue
        
        return matched_codes
    
    def process_funders_batch(self, batch_size: int = 100, dry_run: bool = False) -> Dict:
        """Process funders in batches and assign UKCAT codes."""
        
        results = {
            'processed': 0,
            'matched': 0,
            'no_matches': 0,
            'errors': 0,
            'matched_codes': set()
        }
        
        try:
            # Get all funders that don't have UKCAT codes yet
            self.cursor.execute("""
                SELECT id, name, description, ukcat_codes
                FROM funders 
                WHERE ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb
                ORDER BY id
                LIMIT %s
            """, (batch_size,))
            
            funders = self.cursor.fetchall()
            
            if not funders:
                logger.info("✅ No funders need classification")
                return results
            
            logger.info(f"📊 Processing {len(funders)} funders...")
            
            for funder_id, name, description, existing_codes in funders:
                try:
                    logger.info(f"  🔍 Processing: {name} (ID: {funder_id})")
                    
                    # Get current codes (if any)
                    current_codes = set()
                    if existing_codes:
                        try:
                            current_codes = set(json.loads(existing_codes)) if isinstance(existing_codes, str) else set(existing_codes)
                        except:
                            current_codes = set()
                    
                    # Classify funder
                    matched_codes = self.classify_funder(name, description or "")
                    
                    # Combine with existing codes
                    all_codes = list(current_codes.union(set(matched_codes)))
                    
                    # Update database
                    if not dry_run:
                        self.cursor.execute("""
                            UPDATE funders 
                            SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (json.dumps(all_codes), funder_id))
                    
                    results['processed'] += 1
                    results['matched_codes'].update(matched_codes)
                    
                    if matched_codes:
                        results['matched'] += 1
                        logger.info(f"    ✓ Assigned codes: {', '.join(matched_codes)}")
                    else:
                        results['no_matches'] += 1
                        logger.info(f"    ⚠️ No codes matched")
                        
                except Exception as e:
                    logger.error(f"❌ Error processing funder {funder_id}: {e}")
                    results['errors'] += 1
                    continue
            
            # Commit if not dry run
            if not dry_run:
                self.conn.commit()
            
            logger.info(f"✅ Batch processing completed!")
            logger.info(f"📊 Processed: {results['processed']}")
            logger.info(f"📊 Matched: {results['matched']}")
            logger.info(f"📊 No matches: {results['no_matches']}")
            logger.info(f"📊 Errors: {results['errors']}")
            logger.info(f"📊 Unique codes assigned: {len(results['matched_codes'])}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Batch processing failed: {e}")
            return results

def main():
    """Main function to assign UKCAT codes to funders."""
    
    parser = argparse.ArgumentParser(description='Assign UKCAT codes to funders')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of funders to process per batch')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return
    
    conn = psycopg2.connect(db_url)
    
    try:
        logger.info("🚀 Starting UKCAT classification assignment...")
        
        if args.dry_run:
            logger.info("🔍 DRY RUN MODE - No database changes will be made")
        
        # Initialize classifier
        classifier = UKCATClassifier(conn)
        
        if not classifier.ukcat_patterns:
            logger.error("❌ No UKCAT patterns loaded. Import UKCAT data first.")
            return
        
        # Process funders
        results = classifier.process_funders_batch(args.batch_size, args.dry_run)
        
        if args.dry_run:
            logger.info("🔍 DRY RUN SUMMARY:")
            logger.info(f"  Would process: {results['processed']} funders")
            logger.info(f"  Would match: {results['matched']} funders")
            logger.info(f"  Would assign: {len(results['matched_codes'])} unique codes")
            logger.info(f"  Would generate: {sum(1 for _ in results['matched_codes'])} code assignments")
        else:
            logger.info("✅ UKCAT classification completed!")
            
        # Show most common assigned codes
        if results['matched_codes']:
            logger.info("\n📈 Most commonly assigned codes:")
            for code in sorted(results['matched_codes']):
                logger.info(f"  {code}")
        
    except Exception as e:
        logger.error(f"❌ Classification failed: {e}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()