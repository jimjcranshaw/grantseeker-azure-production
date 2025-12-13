import requests
import zipfile
import io
import pandas as pd
import psycopg2
import os
import sys
import json
from dotenv import load_dotenv
from fuzzywuzzy import process

# Load env
dotenv_path = os.path.join(os.path.expanduser('~'), 'grantseeker-azure-production', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

# Charity Commission Public Data URL (JSON format is easiest)
# Using the stable lookup URL if possible, or asking user to provide if it changes.
# For now, let's use the standard publicly available huge CSV/JSON link logic.
# Actually, downloading 100MB+ might be slow. 
# Let's try to be smart.

def get_db_connection():
    try:
        return psycopg2.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT'),
            sslmode='require'
        )
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        sys.exit(1)

def download_register():
    print("⏳ Downloading Charity Register data (this may take a minute)...")
    # This URL is the standard public data extract (zip containing CSVs)
    # Using a generic placeholder if the direct link is dynamic. 
    # For this script, I'll ask the user to provide the path OR try a known one.
    # Let's assume the user downloads it for now to avoid broken links, 
    # OR better: Use the API for specific lookups if we can (but that requires keys).
    
    # Actually, let's use the 'charity-commission-extract' package logic or simple request.
    # DATA URL: https://ccewuksprdoneregsdata1.blob.core.windows.net/data/txt/publicextract.charity.zip
    url = "https://ccewuksprdoneregsdata1.blob.core.windows.net/data/txt/publicextract.charity.zip"
    
    try:
        r = requests.get(url, stream=True)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        
        # We need 'extract_charity.csv' or similar (main charity file)
        # The file inside is usually 'publicextract.charity.json' or .txt (bcp format)
        # The .txt files are BCP (pipe separated).
        
        # List files
        # print(z.namelist())
        
        # We look for the main charity file
        target_file = next((f for f in z.namelist() if 'charity' in f and 'part' not in f), None)
        
        if not target_file:
            print("❌ Could not find charity data in zip.")
            return None
            
        print(f"   Extracting {target_file}...")
        
        # Read BCP format (pipe separated)
        # Headers are usually: regno, subno, name, orgtype, ...
        # This is complex to parse blindly. 
        
        # SIMPLER APPROACH:
        # Just use pandas to read it assuming standard format.
        
        # Let's stick to the user's manual download if this is too fragile.
        # But wait, the user asked for AUTOMATED.
        
        df = pd.read_csv(z.open(target_file), sep='\t', encoding='latin1', error_bad_lines=False)
        return df
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return None

# Since the public file format is a bit messy (BCP files), 
# I will implement a safer "Search by Name" API approach for the MISSING numbers
# And a "Check Status" API approach for existing numbers.
# The API is: https://api.charitycommission.gov.uk/register/api/charitysearch
# But it requires a key.

# Backtrack: The user wants "Easiest way".
# Easiest way without API keys is downloading the file.
# I will implement a script that accepts the file path OR tries to download.

def sync_db(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Handle both JSON and DataFrame inputs
    if isinstance(data, str):
        # Assume it's a file path
        if data.endswith('.json'):
            with open(data, 'r', encoding='utf-8-sig') as f:
                charities = json.load(f)
        else:
            # Assume CSV
            data = pd.read_csv(data, encoding='latin1', on_bad_lines='skip')
            charities = data.to_dict('records')
    else:
        # Assume it's already a list of records
        charities = data
    
    print(f"   ⏳ Processing {len(charities):,} charity records...")
    
    # Filter for active (registered) charities only
    active_charities = {}
    for charity in charities:
        status = charity.get('charity_registration_status', '').lower()
        if status == 'registered':
            reg_no = str(charity.get('registered_charity_number', '')).strip()
            name = charity.get('charity_name', '').strip()
            if reg_no and name:
                active_charities[reg_no] = name
    
    print(f"   ✅ Found {len(active_charities):,} active registered charities")
    
    # Create Name -> RegNo map for lookup
    name_to_reg = {name.lower(): reg_no for reg_no, name in active_charities.items()}
    
    # 2. Iterate DB
    print("   🔍 Checking database for closed trusts...")
    cursor.execute("SELECT id, name, charity_number FROM funders WHERE is_active = TRUE")
    db_funders = cursor.fetchall()
    
    linked_count = 0
    deactivated_count = 0
    
    for f_id, f_name, f_num in db_funders:
        f_name_clean = f_name.lower().strip()
        
        # Step A: Link Missing Numbers (for trusts without charity numbers)
        if not f_num:
            # Try exact match
            if f_name_clean in name_to_reg:
                new_num = name_to_reg[f_name_clean]
                print(f"   🔗 Linked '{f_name}' to Charity #{new_num}")
                cursor.execute("UPDATE funders SET charity_number = %s WHERE id = %s", (new_num, f_id))
                f_num = new_num  # Set for next step
                linked_count += 1
        
        # Step B: Check Status (if we have a number)
        if f_num:
            f_num_str = str(f_num).strip()
            if f_num_str not in active_charities:
                # Check if this charity is in the register but marked as 'Removed'
                # Let's find this charity in our data to see its status
                charity_status = 'not_found'
                for charity in charities:
                    if str(charity.get('registered_charity_number', '')).strip() == f_num_str:
                        charity_status = charity.get('charity_registration_status', 'unknown')
                        break
                
                if charity_status == 'Removed':
                    print(f"   🔻 Deactivating '{f_name}' (#{f_num}) - Charity Removed from Register")
                    cursor.execute("UPDATE funders SET is_active = FALSE WHERE id = %s", (f_id,))
                    deactivated_count += 1
                elif charity_status == 'not_found':
                    print(f"   🔻 Deactivating '{f_name}' (#{f_num}) - Charity Not Found in Register")
                    cursor.execute("UPDATE funders SET is_active = FALSE WHERE id = %s", (f_id,))
                    deactivated_count += 1
    
    conn.commit()
    print("-" * 50)
    print(f"✅ Charity Status Sync Complete")
    print(f"   🔗 Linked charity numbers: {linked_count}")
    print(f"   🔻 Deactivated closed trusts: {deactivated_count}")
    conn.close()

if __name__ == "__main__":
    print("🔍 Charity Status Sync - Check for closed trusts")
    print("This script checks our database against the latest Charity Commission register")
    print("and deactivates trusts that have been removed from the register.")
    print()
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', help='Path to Charity Commission JSON or CSV file')
    args = parser.parse_args()
    
    if args.file:
        try:
            print(f"📥 Loading {args.file}...")
            if args.file.endswith('.json'):
                # Handle JSON files from monthly processor
                sync_db(args.file)
            else:
                # Handle CSV files
                df = pd.read_csv(args.file, encoding='latin1', on_bad_lines='skip')
                sync_db(df)
        except Exception as e:
            print(f"❌ Error loading file: {e}")
    else:
        print("❌ No file provided.")
        print("Usage: python3 auto_sync_charity_status.py --file <path_to_charity_register.json>")
        print()
        print("Tip: Use the JSON file from monthly_charity_processor.py:")
        print("   python3 auto_sync_charity_status.py --file data/processed/publicextract.charity/publicextract.charity.json")