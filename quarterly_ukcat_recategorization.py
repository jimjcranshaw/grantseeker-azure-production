#!/usr/bin/env python3
"""
Quarterly UKCAT Recategorization System
=======================================

Automated quarterly recategorization of all funders to ensure classifications
stay current with both funder activities and UKCAT standards.

Usage:
    python quarterly_ukcat_recategorization.py [--dry-run] [--resume]
    
Scheduling:
    Add to crontab for quarterly execution:
    0 2 1 */3 * /path/to/python3 /path/to/quarterly_ukcat_recategorization.py

Author: Grant Seeker Pipeline
Date: December 2025
"""

import os
import csv
import json
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
import argparse
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'quarterly_recategorization_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class QuarterlyRecategorizer:
    """Quarterly UKCAT recategorization system."""
    
    def __init__(self, dry_run: bool = False):
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
        self.dry_run = dry_run
        
        # Load UKCAT mappings
        self.ukcat_mappings = self._load_ukcat_mappings()
        
        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'total_funders': 0,
            'processed': 0,
            'matched': 0,
            'no_match': 0,
            'changed': 0,
            'unchanged': 0,
            'errors': 0,
            'before_classification': {},  # code -> count
            'after_classification': {}     # code -> count
        }
        
        # Progress tracking
        self.progress_file = Path('quarterly_recategorization_progress.json')
    
    def _load_ukcat_mappings(self) -> Dict[str, List[str]]:
        """Load UKCAT charity number to code mappings from CSV files."""
        logger.info("📁 Loading UKCAT mappings...")
        
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
                            
                            if org_id.startswith('GB-CHC-'):
                                charity_number = org_id.replace('GB-CHC-', '')
                                
                                if charity_number not in mappings:
                                    mappings[charity_number] = []
                                
                                if ukcat_code not in mappings[charity_number]:
                                    mappings[charity_number].append(ukcat_code)
                                
                                total_records += 1
                except Exception as e:
                    logger.warning(f"⚠️ Error loading UKCAT file {file_path}: {e}")
        
        logger.info(f"✅ Loaded UKCAT mappings for {len(mappings)} charities ({total_records} records)")
        return mappings
    
    def _load_progress(self) -> Optional[Dict]:
        """Load progress from previous run if resuming."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Error loading progress file: {e}")
        return None
    
    def _save_progress(self, last_processed_id: int):
        """Save progress for resume capability."""
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if 'start_time' in stats_copy:
            stats_copy['start_time'] = stats_copy['start_time'].isoformat()
        
        progress = {
            'last_processed_id': last_processed_id,
            'timestamp': datetime.now().isoformat(),
            'stats': stats_copy
        }
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(progress, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Error saving progress: {e}")
    
    def _get_all_funders(self, resume_from_id: Optional[int] = None) -> List[Tuple]:
        """Get all funders with charity numbers for recategorization."""
        query = """
            SELECT id, name, charity_number, ukcat_codes
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
            ORDER BY id
        """
        
        if resume_from_id:
            query += f" AND id > {resume_from_id}"
        
        self.cursor.execute(query)
        return self.cursor.fetchall()
    
    def _get_classification_stats(self) -> Dict[str, int]:
        """Get current classification statistics."""
        self.cursor.execute("""
            SELECT jsonb_array_elements_text(ukcat_codes) as code
            FROM funders 
            WHERE ukcat_codes IS NOT NULL 
            AND jsonb_array_length(ukcat_codes) > 0
        """)
        
        stats = {}
        for row in self.cursor.fetchall():
            code = row[0]
            stats[code] = stats.get(code, 0) + 1
        
        return stats
    
    def _compare_classifications(self, old_codes: List[str], new_codes: List[str]) -> bool:
        """Compare two classification lists to see if they changed."""
        return set(old_codes) != set(new_codes)
    
    def recategorize_all_funders(self, batch_size: int = 1000):
        """Recategorize all funders in batches."""
        logger.info("🚀 Starting quarterly UKCAT recategorization...")
        logger.info("=" * 60)
        
        # Load progress if resuming
        progress = self._load_progress()
        resume_from_id = progress.get('last_processed_id') if progress else None
        
        if resume_from_id:
            logger.info(f"📂 Resuming from funder ID: {resume_from_id}")
        
        # Get before statistics
        logger.info("📊 Collecting before-classification statistics...")
        self.stats['before_classification'] = self._get_classification_stats()
        logger.info(f"  Total UKCAT code assignments: {sum(self.stats['before_classification'].values())}")
        logger.info(f"  Unique codes: {len(self.stats['before_classification'])}")
        
        # Get all funders
        funders = self._get_all_funders(resume_from_id)
        self.stats['total_funders'] = len(funders)
        
        logger.info(f"📊 Processing {len(funders)} funders...")
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No database changes will be made")
        
        # Process in batches
        batch_num = 0
        for i in range(0, len(funders), batch_size):
            batch = funders[i:i + batch_size]
            batch_num += 1
            
            logger.info(f"\n📦 Processing batch {batch_num} ({len(batch)} funders)...")
            
            batch_changed = 0
            batch_unchanged = 0
            batch_matched = 0
            batch_no_match = 0
            
            for funder_id, name, charity_number, existing_codes in batch:
                try:
                    # Get existing codes
                    old_codes = []
                    if existing_codes:
                        try:
                            old_codes = existing_codes if isinstance(existing_codes, list) else json.loads(existing_codes)
                        except:
                            old_codes = []
                    
                    # Get new UKCAT codes
                    charity_str = str(charity_number).strip()
                    new_codes = []
                    
                    if charity_str in self.ukcat_mappings:
                        new_codes = self.ukcat_mappings[charity_str]
                        batch_matched += 1
                        self.stats['matched'] += 1
                    else:
                        batch_no_match += 1
                        self.stats['no_match'] += 1
                    
                    # Compare classifications
                    changed = self._compare_classifications(old_codes, new_codes)
                    
                    if changed:
                        batch_changed += 1
                        self.stats['changed'] += 1
                        
                        if not self.dry_run:
                            # Update database
                            self.cursor.execute("""
                                UPDATE funders 
                                SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (json.dumps(new_codes), funder_id))
                            
                            logger.debug(f"  ✅ Updated {name} ({charity_number}): {old_codes} -> {new_codes}")
                    else:
                        batch_unchanged += 1
                        self.stats['unchanged'] += 1
                    
                    self.stats['processed'] += 1
                    
                    # Update progress every 100 funders
                    if self.stats['processed'] % 100 == 0:
                        self._save_progress(funder_id)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing funder {funder_id}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Commit batch
            if not self.dry_run:
                self.conn.commit()
            
            logger.info(f"  Batch {batch_num} complete: {batch_changed} changed, {batch_unchanged} unchanged, {batch_matched} matched, {batch_no_match} no match")
            
            # Show overall progress
            progress_pct = (self.stats['processed'] / self.stats['total_funders']) * 100 if self.stats['total_funders'] > 0 else 0
            logger.info(f"  Overall progress: {self.stats['processed']}/{self.stats['total_funders']} ({progress_pct:.1f}%)")
        
        # Get after statistics
        logger.info("\n📊 Collecting after-classification statistics...")
        self.stats['after_classification'] = self._get_classification_stats()
        
        # Generate final report
        self._generate_report()
        
        # Clean up progress file
        if self.progress_file.exists() and not self.dry_run:
            self.progress_file.unlink()
            logger.info("✅ Progress file cleaned up")
    
    def _generate_report(self):
        """Generate final recategorization report."""
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds() / 60
        
        logger.info("\n" + "=" * 60)
        logger.info("🏁 QUARTERLY UKCAT RECATEGORIZATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"⏰ Total time: {elapsed_time:.1f} minutes")
        logger.info(f"📊 Total funders processed: {self.stats['processed']}")
        logger.info(f"📊 Matched with UKCAT data: {self.stats['matched']}")
        logger.info(f"📊 No UKCAT data available: {self.stats['no_match']}")
        logger.info(f"📊 Classifications changed: {self.stats['changed']}")
        logger.info(f"📊 Classifications unchanged: {self.stats['unchanged']}")
        logger.info(f"📊 Errors: {self.stats['errors']}")
        
        # Before/after comparison
        logger.info("\n📈 Classification Statistics:")
        before_total = sum(self.stats['before_classification'].values())
        after_total = sum(self.stats['after_classification'].values())
        logger.info(f"  Before: {before_total} total code assignments, {len(self.stats['before_classification'])} unique codes")
        logger.info(f"  After: {after_total} total code assignments, {len(self.stats['after_classification'])} unique codes")
        logger.info(f"  Change: {after_total - before_total:+d} assignments ({((after_total - before_total) / before_total * 100):+.1f}%)" if before_total > 0 else "  Change: N/A")
        
        # Top codes
        logger.info("\n📊 Top 10 UKCAT Codes (After):")
        sorted_codes = sorted(self.stats['after_classification'].items(), key=lambda x: x[1], reverse=True)
        for code, count in sorted_codes[:10]:
            logger.info(f"  {code}: {count}")
        
        logger.info("=" * 60)
        
        # Save report to file
        report_file = Path(f'quarterly_recategorization_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if 'start_time' in stats_copy:
            stats_copy['start_time'] = stats_copy['start_time'].isoformat()
        
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': stats_copy,
            'elapsed_minutes': elapsed_time
        }
        
        try:
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            logger.info(f"📄 Report saved to: {report_file}")
        except Exception as e:
            logger.warning(f"⚠️ Error saving report: {e}")
    
    def close(self):
        """Clean up resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Quarterly UKCAT recategorization')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--resume', action='store_true', help='Resume from last progress checkpoint')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for processing')
    
    args = parser.parse_args()
    
    recategorizer = QuarterlyRecategorizer(dry_run=args.dry_run)
    
    try:
        recategorizer.recategorize_all_funders(batch_size=args.batch_size)
    except KeyboardInterrupt:
        logger.info("🛑 Recategorization interrupted by user")
        logger.info("💾 Progress saved - use --resume to continue")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        recategorizer.close()

if __name__ == "__main__":
    main()
