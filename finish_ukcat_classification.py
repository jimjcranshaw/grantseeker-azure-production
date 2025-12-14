#!/usr/bin/env python3
"""
Finish UKCAT Classification - Process remaining funders and mark those without matches
"""

import csv
import os
import psycopg2
import json
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load UKCAT mappings
logger.info("Loading UKCAT mappings...")
ukcat_files = ['ukcat_project/data/charities_active-ukcat.csv', 'ukcat_project/data/charities_inactive-ukcat.csv']
mappings = {}
for file_path in ukcat_files:
    if os.path.exists(file_path):
        logger.info(f"  Loading: {file_path}")
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

logger.info(f"✅ Loaded {len(mappings)} UKCAT mappings")

# Connect to DB
conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME'),
    port=os.getenv('DB_PORT'),
    sslmode='require'
)
cur = conn.cursor()

# Get all unclassified funders
cur.execute("""
    SELECT id, name, charity_number, ukcat_codes
    FROM funders 
    WHERE charity_number IS NOT NULL 
    AND charity_number != ''
    AND (ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb)
""")

funders = cur.fetchall()
logger.info(f"📊 Found {len(funders)} unclassified funders")

matched = 0
no_match = 0

for funder_id, name, charity_number, existing_codes in funders:
    charity_str = str(charity_number).strip()
    
    if charity_str in mappings:
        # Found UKCAT codes
        ukcat_codes = mappings[charity_str]
        
        # Get existing codes
        current_codes = []
        if existing_codes:
            try:
                current_codes = existing_codes if isinstance(existing_codes, list) else json.loads(existing_codes)
            except:
                current_codes = []
        
        # Merge codes
        all_codes = list(set(current_codes + ukcat_codes))
        
        # Update database
        cur.execute("""
            UPDATE funders 
            SET ukcat_codes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (json.dumps(all_codes), funder_id))
        
        matched += 1
        if matched % 50 == 0:
            logger.info(f"  ✅ Processed {matched} matched funders...")
    else:
        # No UKCAT mapping - mark as processed with empty array
        cur.execute("""
            UPDATE funders 
            SET ukcat_codes = '[]'::jsonb, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (funder_id,))
        
        no_match += 1
        if no_match % 50 == 0:
            logger.info(f"  ⚠️ Processed {no_match} funders without UKCAT data...")

# Commit all changes
conn.commit()
logger.info("✅ Committed all changes")

# Final stats
cur.execute('SELECT COUNT(*) FROM funders WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0')
classified = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM funders WHERE charity_number IS NOT NULL AND charity_number != '' AND (ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb)")
remaining = cur.fetchone()[0]

logger.info("=" * 60)
logger.info("🏁 CLASSIFICATION COMPLETE")
logger.info("=" * 60)
logger.info(f"📊 Matched with UKCAT codes: {matched}")
logger.info(f"📊 No UKCAT data available: {no_match}")
logger.info(f"📊 Total classified (with codes): {classified}")
logger.info(f"📊 Remaining unclassified: {remaining}")
logger.info("=" * 60)

cur.close()
conn.close()
