#!/usr/bin/env python3
"""
Continuous UKCAT Classification
==============================

This script continuously processes all remaining funders in batches.
Can be run in the background for extended periods.
"""

import os
import time
import argparse
from dotenv import load_dotenv
import psycopg2
import json
import re
from datetime import datetime

# Load environment variables
load_dotenv()

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ContinuousClassifier:
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
        self.stats = {
            'total_processed': 0,
            'total_matched': 0,
            'batches_completed': 0,
            'start_time': datetime.now()
        }
        
        # Load UKCAT patterns
        self.patterns = self.load_patterns()
        
    def load_patterns(self):
        """Load UKCAT classification patterns."""
        patterns = {}
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
        
        logger.info(f"📊 Loaded {len(patterns)} UKCAT classification patterns")
        return patterns
    
    def get_progress(self):
        """Get current classification progress."""
        self.cursor.execute('SELECT COUNT(*) FROM funders')
        total_funders = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM funders WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0')
        classified_funders = self.cursor.fetchone()[0]
        
        unclassified_funders = total_funders - classified_funders
        progress_percentage = (classified_funders / total_funders) * 100 if total_funders > 0 else 0
        
        return {
            'total_funders': total_funders,
            'classified_funders': classified_funders,
            'unclassified_funders': unclassified_funders,
            'progress_percentage': progress_percentage
        }
    
    def classify_batch(self, batch_size=500):
        """Classify a single batch of funders."""
        
        # Get unclassified funders
        self.cursor.execute("""
            SELECT id, name, description, ukcat_codes
            FROM funders 
            WHERE ukcat_codes = '[]'::jsonb
            ORDER BY id
            LIMIT %s
        """, (batch_size,))
        
        funders = self.cursor.fetchall()
        
        if not funders:
            return False  # No more funders to classify
        
        logger.info(f"📊 Processing batch of {len(funders)} funders...")
        
        batch_stats = {
            'processed': 0,
            'matched': 0,
            'no_matches': 0,
            'errors': 0
        }
        
        # Process each funder
        for funder_id, name, description, existing_codes in funders:
            try:
                if not name:
                    batch_stats['no_matches'] += 1
                    continue
                
                # Get current codes
                current_codes = set()
                if existing_codes:
                    try:
                        current_codes = set(existing_codes) if isinstance(existing_codes, list) else set()
                    except:
                        current_codes = set()
                
                # Classify funder
                text_to_analyze = f"{name} {description or ''}".strip()
                matched_codes = []
                
                if len(text_to_analyze) >= 5:
                    for code, pattern_info in self.patterns.items():
                        try:
                            if pattern_info['pattern'].search(text_to_analyze):
                                if pattern_info['exclude_pattern'] and pattern_info['exclude_pattern'].search(text_to_analyze):
                                    continue
                                matched_codes.append(code)
                        except Exception as e:
                            continue
                
                # Update database
                all_codes = list(current_codes.union(set(matched_codes)))
                self.cursor.execute("""
                    UPDATE funders 
                    SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (json.dumps(all_codes), funder_id))
                
                batch_stats['processed'] += 1
                if matched_codes:
                    batch_stats['matched'] += 1
                else:
                    batch_stats['no_matches'] += 1
                    
            except Exception as e:
                logger.error(f"❌ Error processing funder {funder_id}: {e}")
                batch_stats['errors'] += 1
                continue
        
        # Commit batch
        self.conn.commit()
        
        # Update stats
        self.stats['total_processed'] += batch_stats['processed']
        self.stats['total_matched'] += batch_stats['matched']
        self.stats['batches_completed'] += 1
        
        # Log progress
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 3600
        rate_per_hour = batch_stats['processed'] / max(elapsed_time, 0.1) if elapsed_time > 0 else 0
        
        logger.info(f"📊 BATCH {self.stats['batches_completed']} COMPLETED:")
        logger.info(f"  Processed: {batch_stats['processed']}")
        logger.info(f"  Matched: {batch_stats['matched']} ({batch_stats['matched']/batch_stats['processed']*100:.1f}%)")
        logger.info(f"  Rate: {rate_per_hour:.1f} funders/hour")
        
        return True
    
    def run_continuous(self, max_batches=None):
        """Run continuous classification."""
        logger.info("🚀 Starting continuous UKCAT classification...")
        logger.info(f"⏰ Started at: {self.stats['start_time']}")
        logger.info("=" * 60)
        
        try:
            batch_count = 0
            while True:
                # Get progress
                progress = self.get_progress()
                logger.info(f"📊 Progress: {progress['classified_funders']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
                logger.info(f"📊 Remaining: {progress['unclassified_funders']} funders")
                
                # Process batch
                success = self.classify_batch()
                
                if not success:
                    logger.info("🎉 ALL FUNDERS CLASSIFIED! Mission accomplished!")
                    break
                
                batch_count += 1
                if max_batches and batch_count >= max_batches:
                    logger.info(f"📊 Reached maximum batches ({max_batches})")
                    break
                
                # Brief pause
                time.sleep(2)
                
        except KeyboardInterrupt:
            logger.info("🛑 Classification interrupted by user")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
        finally:
            self.close()
        
        # Final summary
        self.print_summary()
    
    def print_summary(self):
        """Print final summary."""
        progress = self.get_progress()
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 3600
        
        logger.info("=" * 60)
        logger.info("🏁 FINAL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} hours")
        logger.info(f"📊 Batches completed: {self.stats['batches_completed']}")
        logger.info(f"📊 Total processed: {self.stats['total_processed']}")
        logger.info(f"📊 Total matched: {self.stats['total_matched']}")
        logger.info(f"📊 Final progress: {progress['classified_funders']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
        
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
    parser = argparse.ArgumentParser(description='Continuous UKCAT classification')
    parser.add_argument('--max-batches', type=int, help='Maximum number of batches to process')
    parser.add_argument('--batch-size', type=int, default=500, help='Batch size for processing')
    
    args = parser.parse_args()
    
    classifier = ContinuousClassifier()
    classifier.run_continuous(args.max_batches)

if __name__ == "__main__":
    main()