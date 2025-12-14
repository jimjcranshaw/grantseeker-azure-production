#!/usr/bin/env python3
"""
Background UKCAT Classification Processor
========================================

This script runs continuously to classify all remaining funders in batches.
Designed to run in tmux session for background processing.

Usage:
    python background_ukcat_classification.py --continuous

Author: Grant Seeker UKCAT Integration  
Date: December 2025
"""

import os
import time
import json
import psycopg2
from dotenv import load_dotenv
import logging
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ukcat_classification.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BackgroundClassifier:
    """Background classification processor for all remaining funders."""
    
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.conn = psycopg2.connect(self.db_url)
        self.cursor = self.conn.cursor()
        self.stats = {
            'total_processed': 0,
            'total_matched': 0,
            'total_errors': 0,
            'batches_completed': 0,
            'start_time': datetime.now()
        }
        
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
    
    def process_batch(self, batch_size=500):
        """Process a single batch of unclassified funders."""
        
        # Get unclassified funders
        self.cursor.execute("""
            SELECT id, name, description, ukcat_codes
            FROM funders 
            WHERE ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb
            ORDER BY id
            LIMIT %s
        """, (batch_size,))
        
        funders = self.cursor.fetchall()
        
        if not funders:
            logger.info("✅ No more funders to classify - all done!")
            return False
        
        logger.info(f"📊 Processing batch of {len(funders)} funders...")
        
        batch_stats = {
            'processed': 0,
            'matched': 0,
            'no_matches': 0,
            'errors': 0,
            'matched_codes': set()
        }
        
        # Load UKCAT patterns
        self.cursor.execute("""
            SELECT code, tag, regex_pattern, exclude_regex_pattern, category
            FROM ukcat_codes 
            WHERE regex_pattern IS NOT NULL AND regex_pattern != ''
            ORDER BY code
        """)
        
        patterns = {}
        for row in self.cursor.fetchall():
            code, tag, include_regex, exclude_regex, category = row
            
            if include_regex:
                try:
                    import re
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
        
        # Process each funder
        for funder_id, name, description, existing_codes in funders:
            try:
                # Skip if no name
                if not name:
                    batch_stats['no_matches'] += 1
                    continue
                
                # Get current codes (if any)
                current_codes = set()
                if existing_codes:
                    try:
                        current_codes = set(existing_codes) if isinstance(existing_codes, list) else set()
                    except:
                        current_codes = set()
                
                # Classify funder
                text_to_analyze = f"{name} {description or ''}".strip()
                matched_codes = []
                
                if len(text_to_analyze) >= 5:  # Skip very short texts
                    for code, pattern_info in patterns.items():
                        try:
                            # Check if pattern matches
                            if pattern_info['pattern'].search(text_to_analyze):
                                # Check exclude pattern if present
                                if pattern_info['exclude_pattern'] and pattern_info['exclude_pattern'].search(text_to_analyze):
                                    continue
                                
                                matched_codes.append(code)
                                
                        except Exception as e:
                            logger.warning(f"⚠️ Error matching pattern {code}: {e}")
                            continue
                
                # Combine with existing codes
                all_codes = list(current_codes.union(set(matched_codes)))
                
                # Update database
                self.cursor.execute("""
                    UPDATE funders 
                    SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (json.dumps(all_codes), funder_id))
                
                batch_stats['processed'] += 1
                batch_stats['matched_codes'].update(matched_codes)
                
                if matched_codes:
                    batch_stats['matched'] += 1
                    if len(batch_stats['matched_codes']) <= 10:  # Only log first few for readability
                        logger.info(f"  ✓ {name[:50]}: {', '.join(matched_codes)}")
                else:
                    batch_stats['no_matches'] += 1
                    
            except Exception as e:
                logger.error(f"❌ Error processing funder {funder_id}: {e}")
                batch_stats['errors'] += 1
                continue
        
        # Commit batch
        self.conn.commit()
        
        # Update overall stats
        self.stats['total_processed'] += batch_stats['processed']
        self.stats['total_matched'] += batch_stats['matched']
        self.stats['total_errors'] += batch_stats['errors']
        self.stats['batches_completed'] += 1
        
        # Log batch summary
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 3600  # hours
        rate_per_hour = batch_stats['processed'] / max(elapsed_time, 0.1)
        
        logger.info(f"📊 BATCH {self.stats['batches_completed']} COMPLETED:")
        logger.info(f"  Processed: {batch_stats['processed']}")
        logger.info(f"  Matched: {batch_stats['matched']} ({batch_stats['matched']/batch_stats['processed']*100:.1f}%)")
        logger.info(f"  No matches: {batch_stats['no_matches']}")
        logger.info(f"  Errors: {batch_stats['errors']}")
        logger.info(f"  Unique codes this batch: {len(batch_stats['matched_codes'])}")
        logger.info(f"  Processing rate: {rate_per_hour:.1f} funders/hour")
        
        return True
    
    def run_continuous(self, batch_size=500):
        """Run continuous classification until all funders are processed."""
        
        logger.info("🚀 Starting continuous UKCAT classification...")
        logger.info(f"📊 Database: {self.db_url[:50]}...")
        logger.info(f"🎯 Batch size: {batch_size}")
        logger.info(f"⏰ Started at: {self.stats['start_time']}")
        logger.info("=" * 60)
        
        try:
            while True:
                # Get current progress
                progress = self.get_progress()
                
                if progress['unclassified_funders'] == 0:
                    logger.info("🎉 ALL FUNDERS CLASSIFIED! Mission accomplished!")
                    break
                
                logger.info(f"📊 Current Progress: {progress['classified_funders']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
                logger.info(f"📊 Remaining: {progress['unclassified_funders']} funders")
                
                # Process next batch
                success = self.process_batch(batch_size)
                
                if not success:
                    logger.info("✅ No more funders to process")
                    break
                
                # Brief pause between batches
                logger.info("⏳ Waiting 5 seconds before next batch...")
                time.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("🛑 Classification interrupted by user")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
        finally:
            self.close()
        
        # Final summary
        self.print_final_summary()
    
    def print_final_summary(self):
        """Print final classification summary."""
        progress = self.get_progress()
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 3600
        
        logger.info("=" * 60)
        logger.info("🏁 FINAL CLASSIFICATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} hours")
        logger.info(f"📊 Total batches: {self.stats['batches_completed']}")
        logger.info(f"📊 Total processed: {self.stats['total_processed']}")
        logger.info(f"📊 Total matched: {self.stats['total_matched']}")
        logger.info(f"📊 Total errors: {self.stats['total_errors']}")
        logger.info(f"📊 Final progress: {progress['classified_funders']}/{progress['total_funders']} ({progress['progress_percentage']:.1f}%)")
        
        if progress['progress_percentage'] > 50:
            logger.info("🎉 EXCELLENT! More than 50% coverage achieved!")
        elif progress['progress_percentage'] > 25:
            logger.info("👍 GREAT! More than 25% coverage achieved!")
        else:
            logger.info("📈 GOOD START! Coverage will improve with more processing.")
            
        logger.info("=" * 60)
    
    def close(self):
        """Clean up database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    """Main function."""
    classifier = BackgroundClassifier()
    
    try:
        classifier.run_continuous()
    except Exception as e:
        logger.error(f"❌ Classification failed: {e}")
    finally:
        classifier.close()

if __name__ == "__main__":
    main()