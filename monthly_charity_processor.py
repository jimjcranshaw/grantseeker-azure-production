#!/usr/bin/env python3
"""
Monthly Charity Register Processing System
==========================================

Automated system for processing UK Charity Commission register downloads,
filtering for new grantmaking trusts and foundations, and managing the review workflow.

Author: Grant Seeker Pipeline
Date: December 2025
"""

import os
import sys
import json
import csv
import zipfile
import logging
import argparse
import psycopg2
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monthly_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Directory Structure
BASE_DIR = Path("./data")
RAW_DOWNLOADS_DIR = BASE_DIR / "raw_downloads"
PROCESSED_DIR = BASE_DIR / "processed"
REVIEW_QUEUE_DIR = BASE_DIR / "review_queue"
REVIEWED_DIR = BASE_DIR / "reviewed"
ARCHIVE_DIR = BASE_DIR / "archive"
LOGS_DIR = BASE_DIR / "logs"

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': os.getenv('DB_PORT'),
    'sslmode': 'require'
}

# Charity Commission Data URLs
CHARITY_DATA_URLS = {
    'charity': 'https://ccewuksprdoneregsadata1.blob.core.windows.net/data/json/publicextract.charity.zip',
    'classification': 'https://ccewuksprdoneregsadata1.blob.core.windows.net/data/json/publicextract.charity_classification.zip'
}

# Classification Codes for Grantmaking (from Data Definition)
# Note: These would be extracted from the Data Definition document
GRANTMAKING_CODES = {
    'operational_methods': [
        'makes_grants_to_organisations',
        'main_way_grant_making'
    ],
    'beneficiaries': [
        'other_charities_or_voluntary_bodies'
    ]
}

# =============================================================================
# FOLDER STRUCTURE MANAGEMENT
# =============================================================================

def setup_directories():
    """Create required directory structure."""
    directories = [
        RAW_DOWNLOADS_DIR,
        PROCESSED_DIR,
        REVIEW_QUEUE_DIR,
        REVIEWED_DIR,
        ARCHIVE_DIR,
        LOGS_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Directory ready: {directory}")

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)

# =============================================================================
# FILE MONITORING
# =============================================================================

class FileMonitor(FileSystemEventHandler):
    """Monitor directories for new files."""
    
    def __init__(self, processor):
        self.processor = processor
        
    def on_created(self, event):
        """Handle new file creation."""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        logger.info(f"📁 New file detected: {file_path}")
        
        # Handle different file types
        if file_path.suffix.lower() == '.zip' and file_path.parent == RAW_DOWNLOADS_DIR:
            self.processor.process_charity_download(file_path)
        elif file_path.suffix.lower() == '.csv' and file_path.parent == REVIEWED_DIR:
            self.processor.process_reviewed_file(file_path)

def start_file_monitoring(processor):
    """Start monitoring directories for new files."""
    event_handler = FileMonitor(processor)
    observer = Observer()
    
    # Watch raw downloads folder
    observer.schedule(event_handler, str(RAW_DOWNLOADS_DIR), recursive=False)
    
    # Watch reviewed folder  
    observer.schedule(event_handler, str(REVIEWED_DIR), recursive=False)
    
    observer.start()
    logger.info("🔍 File monitoring started...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

# =============================================================================
# CHARITY DATA PROCESSING
# =============================================================================

class CharityDataProcessor:
    """Process Charity Commission register data."""
    
    def __init__(self):
        self.current_month = datetime.now()
        self.last_month_start = (self.current_month.replace(day=1) - timedelta(days=1)).replace(day=1)
        self.last_month_end = self.current_month.replace(day=1) - timedelta(days=1)
        
        logger.info(f"📅 Processing period: {self.last_month_start.date()} to {self.last_month_end.date()}")
    
    def download_charity_data(self, output_dir: Path) -> bool:
        """Download latest charity register data."""
        logger.info("📥 Downloading charity register data...")
        
        try:
            for data_type, url in CHARITY_DATA_URLS.items():
                output_file = output_dir / f"charity_{data_type}.zip"
                
                logger.info(f"  Downloading {data_type} from {url}")
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(output_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"  ✅ Downloaded {data_type}: {output_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Download failed: {e}")
            return False
    
    def extract_zip_files(self, zip_dir: Path, extract_dir: Path) -> bool:
        """Extract ZIP files to directory."""
        logger.info("📦 Extracting ZIP files...")
        
        try:
            extract_dir.mkdir(exist_ok=True)
            
            # Look for any ZIP file in the directory
            zip_files = list(zip_dir.glob("*.zip"))
            if not zip_files:
                logger.error(f"❌ No ZIP files found in: {zip_dir}")
                return False
            
            for zip_file in zip_files:
                logger.info(f"  Extracting {zip_file.name}")
                
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                    
                logger.info(f"  ✅ Extracted {zip_file.name}")
                
                # List extracted files for debugging
                extracted_files = list(extract_dir.rglob("*"))
                logger.info(f"  📁 Extracted files: {len(extracted_files)}")
                for f in extracted_files[:5]:  # Show first 5
                    logger.info(f"    - {f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            return False
    
    def process_charity_data(self, data_dir: Path) -> List[Dict]:
        """Process charity data and filter for new grantmaking trusts."""
        logger.info("🔍 Processing charity data...")
        
        try:
            # Load charity data - look for any JSON file in the directory
            json_files = list(data_dir.glob("*.json"))
            if not json_files:
                logger.error(f"❌ No JSON files found in: {data_dir}")
                return []
            
            charity_file = json_files[0]  # Use the first JSON file found
            logger.info(f"📄 Using charity data file: {charity_file}")
            
            if not charity_file.exists():
                logger.error(f"❌ Charity file not found: {charity_file}")
                return []
            
            # Load charity data as JSON array
            with open(charity_file, 'r', encoding='utf-8-sig') as f:
                charities = json.load(f)
            
            logger.info(f"📊 Loaded {len(charities)} charities")
            
            # Load classification data (if available)
            classification_file = data_dir / "publicextract.charity_classification.json"
            classifications = {}
            
            if classification_file.exists():
                with open(classification_file, 'r', encoding='utf-8-sig') as f:
                    classification_data = json.load(f)
                
                # Process classification data
                for item in classification_data:
                    regno = item.get('registered_charity_number')
                    if regno:
                        classifications[regno] = item
                
                logger.info(f"📊 Loaded {len(classifications)} classifications")
            else:
                logger.warning("⚠️ Classification file not found - proceeding with charity data only")
            
            # Filter for new grantmaking trusts
            filtered_trusts = self.filter_grantmaking_trusts(charities, classifications)
            
            logger.info(f"🎯 Found {len(filtered_trusts)} new grantmaking trusts")
            
            return filtered_trusts
            
        except Exception as e:
            logger.error(f"❌ Processing failed: {e}")
            return []
    
    def filter_grantmaking_trusts(self, charities: List[Dict], classifications: Dict) -> List[Dict]:
        """Filter charities for grantmaking trusts registered in the last month."""
        logger.info("🎯 Filtering for new grantmaking trusts...")
        
        filtered_trusts = []
        
        for charity in charities:
            regno = charity.get('registered_charity_number')
            reg_status = charity.get('charity_registration_status')
            reg_date = charity.get('date_of_registration')
            
            # Filter for active charities
            if reg_status != 'Registered':
                continue
            
            # Filter for new registrations (last month)
            if not reg_date:
                continue
                
            try:
                # Handle both formats: '2025-11-15' and '2025-11-15T00:00:00'
                if 'T' in reg_date:
                    charity_reg_date = datetime.strptime(reg_date, '%Y-%m-%dT%H:%M:%S').date()
                else:
                    charity_reg_date = datetime.strptime(reg_date, '%Y-%m-%d').date()
                    
                if not (self.last_month_start.date() <= charity_reg_date <= self.last_month_end.date()):
                    continue
            except ValueError:
                logger.warning(f"⚠️ Invalid date format for charity {regno}: {reg_date}")
                continue
            
            # Check classification
            classification = classifications.get(regno, {})
            if self.is_grantmaking_classification(classification):
                # Add to filtered results
                trust_data = {
                    'regno': regno,
                    'name': charity.get('charity_name', ''),
                    'reg_status': reg_status,
                    'reg_date': reg_date,
                    'classification': classification,
                    'initial_classification': self.classify_trust(charity, classification)
                }
                filtered_trusts.append(trust_data)
        
        return filtered_trusts
    
    def is_grantmaking_classification(self, classification: Dict) -> bool:
        """Check if classification indicates grantmaking."""
        # Use exact classification codes from Charity Commission
        classification_code = classification.get('classification_code')
        classification_type = classification.get('classification_type')
        
        # Grantmaking classifications (codes 301 and 302)
        grantmaking_codes = [301, 302]
        
        if classification_code in grantmaking_codes:
            return True
        
        return False
    
    def classify_trust(self, charity: Dict, classification: Dict) -> str:
        """Provide initial classification of the trust."""
        # This would use AI or rules-based classification
        # For now, using simple heuristics
        
        name = charity.get('name', '').lower()
        operational_method = classification.get('operational_method', '').lower()
        
        # Simple heuristics for initial classification
        if 'trust' in name and 'grant' in operational_method:
            return 'Grantmaking Trust'
        elif 'foundation' in name and 'grant' in operational_method:
            return 'Grantmaking Foundation'
        elif 'charity' in name and 'operational' in operational_method:
            return 'Operational Charity'
        else:
            return 'Needs Review'
    
    def create_review_queue(self, trusts: List[Dict]) -> Path:
        """Create review queue file for manual review."""
        logger.info("📋 Creating review queue...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        review_file = REVIEW_QUEUE_DIR / f"review_queue_{timestamp}.csv"
        
        fieldnames = [
            'regno',
            'name', 
            'reg_status',
            'reg_date',
            'website_url',
            'initial_classification',
            'manual_classification',
            'review_notes',
            'reviewer',
            'review_date'
        ]
        
        with open(review_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for trust in trusts:
                writer.writerow({
                    'regno': trust['regno'],
                    'name': trust['name'],
                    'reg_status': trust['reg_status'],
                    'reg_date': trust['reg_date'],
                    'website_url': '',  # To be filled by reviewer
                    'initial_classification': trust['initial_classification'],
                    'manual_classification': '',  # To be filled by reviewer
                    'review_notes': '',  # To be filled by reviewer
                    'reviewer': '',  # To be filled by reviewer
                    'review_date': ''  # To be filled by reviewer
                })
        
        logger.info(f"✅ Review queue created: {review_file}")
        return review_file
    
    def trigger_crawler(self, trusts: List[Dict]) -> bool:
        """Trigger crawler for qualifying trusts."""
        logger.info("🕷️ Triggering crawler for qualifying trusts...")
        
        try:
            # Create list of trusts to process
            trusts_file = PROCESSED_DIR / f"trusts_to_crawl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(trusts_file, 'w') as f:
                json.dump(trusts, f, indent=2)
            
            # Here you would integrate with the main pipeline
            # For now, just logging
            logger.info(f"📝 Crawler queue created: {trusts_file}")
            logger.info(f"🎯 {len(trusts)} trusts ready for crawling")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Crawler trigger failed: {e}")
            return False

# =============================================================================
# REVIEW PROCESSING
# =============================================================================

class ReviewProcessor:
    """Process reviewed charity data."""
    
    def __init__(self):
        self.ukcat_mappings = self._load_ukcat_mappings()
    
    def _load_ukcat_mappings(self) -> Dict[str, List[str]]:
        """Load UKCAT charity number to code mappings from CSV files."""
        ukcat_files = [
            'ukcat_project/data/charities_active-ukcat.csv',
            'ukcat_project/data/charities_inactive-ukcat.csv'
        ]
        
        mappings = {}
        
        for file_path in ukcat_files:
            if os.path.exists(file_path):
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
                except Exception as e:
                    logger.warning(f"⚠️ Error loading UKCAT file {file_path}: {e}")
        
        logger.info(f"📊 Loaded UKCAT mappings for {len(mappings)} charities")
        return mappings
    
    def _classify_funder_by_charity_number(self, charity_number: str, cursor) -> Optional[List[str]]:
        """Classify a funder using charity number matching."""
        if not charity_number:
            return None
        
        charity_str = str(charity_number).strip()
        
        if charity_str in self.ukcat_mappings:
            return self.ukcat_mappings[charity_str]
        
        return None
    
    def process_reviewed_file(self, review_file: Path) -> bool:
        """Process a reviewed CSV file."""
        logger.info(f"📋 Processing reviewed file: {review_file}")
        
        try:
            # Read reviewed data
            reviewed_data = []
            with open(review_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                reviewed_data = list(reader)
            
            logger.info(f"📊 Loaded {len(reviewed_data)} reviewed entries")
            
            # Import to database
            imported_count = self.import_to_database(reviewed_data)
            
            # Move to archive
            archive_file = ARCHIVE_DIR / f"reviewed_{review_file.name}"
            review_file.rename(archive_file)
            
            logger.info(f"✅ Review processing complete: {imported_count} imported")
            return True
            
        except Exception as e:
            logger.error(f"❌ Review processing failed: {e}")
            return False
    
    def import_to_database(self, reviewed_data: List[Dict]) -> int:
        """Import reviewed data to database."""
        logger.info("💾 Importing to database...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        imported_count = 0
        
        try:
            for entry in reviewed_data:
                # Skip if manual classification not provided
                if not entry.get('manual_classification'):
                    continue
                
                # Check if already exists
                cursor.execute(
                    "SELECT id FROM funders WHERE charity_number = %s",
                    (entry['regno'],)
                )
                
                existing = cursor.fetchone()
                
                # Get UKCAT codes for this charity number
                ukcat_codes = self._classify_funder_by_charity_number(entry['regno'], cursor)
                
                if existing:
                    # Update existing record
                    update_query = """
                        UPDATE funders SET 
                            name = %s,
                            manual_review_classification = %s,
                            review_notes = %s,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    update_params = [
                        entry['name'],
                        entry['manual_classification'],
                        entry['review_notes']
                    ]
                    
                    # Add UKCAT codes if available
                    if ukcat_codes:
                        update_query += ", ukcat_codes = %s"
                        update_params.append(json.dumps(ukcat_codes))
                    
                    update_query += " WHERE charity_number = %s"
                    update_params.append(entry['regno'])
                    
                    cursor.execute(update_query, tuple(update_params))
                    
                    if ukcat_codes:
                        logger.debug(f"✅ Updated UKCAT codes for {entry['name']} ({entry['regno']}): {ukcat_codes}")
                else:
                    # Insert new record (only if website provided)
                    if entry.get('website_url'):
                        insert_query = """
                            INSERT INTO funders (
                                name, website, charity_number, 
                                initial_classification, manual_review_classification,
                                review_notes, is_active, created_at, updated_at
                        """
                        insert_params = [
                            entry['name'],
                            entry['website_url'],
                            entry['regno'],
                            entry['initial_classification'],
                            entry['manual_classification'],
                            entry['review_notes']
                        ]
                        
                        # Add UKCAT codes if available
                        if ukcat_codes:
                            insert_query += ", ukcat_codes"
                            insert_params.append(json.dumps(ukcat_codes))
                        
                        insert_query += ") VALUES (" + ",".join(["%s"] * len(insert_params)) + ", TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        
                        cursor.execute(insert_query, tuple(insert_params))
                        imported_count += 1
                        
                        if ukcat_codes:
                            logger.info(f"✅ Inserted {entry['name']} ({entry['regno']}) with UKCAT codes: {ukcat_codes}")
                        else:
                            logger.debug(f"⚠️ Inserted {entry['name']} ({entry['regno']}) but no UKCAT data available")
            
            conn.commit()
            logger.info(f"✅ Database import complete: {imported_count} records")
            
        except Exception as e:
            logger.error(f"❌ Database import failed: {e}")
            conn.rollback()
        finally:
            conn.close()
        
        return imported_count

# =============================================================================
# MAIN PROCESSOR
# =============================================================================

class MonthlyCharityProcessor:
    """Main monthly charity processing system."""
    
    def __init__(self):
        self.data_processor = CharityDataProcessor()
        self.review_processor = ReviewProcessor()
        
    def process_charity_download(self, zip_file: Path):
        """Process a new charity register download."""
        logger.info(f"📥 Processing charity download: {zip_file}")
        
        try:
            # Extract ZIP file
            extract_dir = PROCESSED_DIR / zip_file.stem
            if not self.data_processor.extract_zip_files(zip_file.parent, extract_dir):
                return False
            
            # Process charity data
            trusts = self.data_processor.process_charity_data(extract_dir)
            
            if not trusts:
                logger.warning("⚠️ No new grantmaking trusts found")
                return False
            
            # Create review queue
            review_file = self.data_processor.create_review_queue(trusts)
            
            # Trigger crawler
            self.data_processor.trigger_crawler(trusts)
            
            # Move processed file to archive
            archive_file = ARCHIVE_DIR / zip_file.name
            zip_file.rename(archive_file)
            
            logger.info("✅ Charity download processing complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Processing failed: {e}")
            return False
    
    def process_reviewed_file(self, review_file: Path):
        """Process a reviewed file."""
        return self.review_processor.process_reviewed_file(review_file)

# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Monthly Charity Register Processing System")
    parser.add_argument('--mode', choices=['download', 'process', 'monitor'], 
                       default='monitor', help='Operation mode')
    parser.add_argument('--file', type=Path, help='Path to file to process')
    
    args = parser.parse_args()
    
    # Setup directories
    setup_directories()
    
    # Initialize processor
    processor = MonthlyCharityProcessor()
    
    if args.mode == 'download':
        # Download latest charity data
        download_dir = RAW_DOWNLOADS_DIR
        success = processor.data_processor.download_charity_data(download_dir)
        if success:
            logger.info("✅ Download complete")
        else:
            logger.error("❌ Download failed")
    
    elif args.mode == 'process':
        # Process existing file
        if not args.file:
            logger.error("❌ --file required for process mode")
            return
        
        if args.file.suffix.lower() == '.zip':
            processor.process_charity_download(args.file)
        elif args.file.suffix.lower() == '.csv':
            processor.process_reviewed_file(args.file)
    
    elif args.mode == 'monitor':
        # Start file monitoring
        logger.info("🔍 Starting file monitoring...")
        start_file_monitoring(processor)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
