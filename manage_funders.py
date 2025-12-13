import argparse
import csv
import psycopg2
import os
import sys
from dotenv import load_dotenv

# Load env
dotenv_path = os.path.join(os.path.expanduser('~'), 'grantseeker-azure-production', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

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

def normalize_column_name(name):
    return name.lower().strip().replace(' ', '_').replace('.', '')

def import_funders(csv_file):
    print(f"📥 Importing funders from: {csv_file}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added_count = 0
    skipped_count = 0
    updated_count = 0
    
    try:
        with open(csv_file, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.DictReader(f)
            
            # Normalize headers to find the right columns
            headers = [normalize_column_name(h) for h in reader.fieldnames]
            
            # Map columns
            name_col = next((h for h in reader.fieldnames if 'name' in normalize_column_name(h) and 'charity' in normalize_column_name(h)), None)
            if not name_col: name_col = next((h for h in reader.fieldnames if 'name' in normalize_column_name(h)), None)
            
            url_col = next((h for h in reader.fieldnames if 'url' in normalize_column_name(h) or 'website' in normalize_column_name(h) or 'web' in normalize_column_name(h)), None)
            
            id_col = next((h for h in reader.fieldnames if 'number' in normalize_column_name(h) or 'reg' in normalize_column_name(h)), None)
            
            if not name_col:
                print("❌ Could not find a 'Name' column in CSV.")
                return

            print(f"   Mapping: Name='{name_col}', URL='{url_col}', ID='{id_col}'")
            
            for row in reader:
                name = row.get(name_col, '').strip()
                url = row.get(url_col, '').strip() if url_col else None
                charity_number = row.get(id_col, '').strip() if id_col else None
                
                if not name:
                    continue
                    
                # Skip if no URL (optional, but usually we want websites)
                if not url:
                    # check if we should skip or just add
                    pass 

                # Check if exists by Charity Number OR Name
                exists_query = "SELECT id FROM funders WHERE "
                params = []
                
                if charity_number:
                    exists_query += "charity_number = %s OR "
                    params.append(charity_number)
                
                exists_query += "name = %s"
                params.append(name)
                
                cursor.execute(exists_query, tuple(params))
                existing = cursor.fetchone()
                
                if existing:
                    # Update charity number if missing
                    if charity_number:
                        cursor.execute("UPDATE funders SET charity_number = %s, is_active = TRUE WHERE id = %s", (charity_number, existing[0]))
                        updated_count += 1
                    skipped_count += 1
                else:
                    # Insert new
                    if url:
                        cursor.execute("""
                            INSERT INTO funders (name, website, charity_number, is_active, created_at, updated_at)
                            VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """, (name, url, charity_number))
                        added_count += 1
                    else:
                        # Log that we skipped a new one because it had no URL? 
                        # Or insert it anyway? Let's insert only if URL exists for now as per pipeline logic
                        skipped_count += 1

        conn.commit()
        print(f"✅ Import Complete!")
        print(f"   ➕ Added: {added_count}")
        print(f"   🔄 Updated/Skipped: {skipped_count}")
        
    except Exception as e:
        print(f"❌ Import Failed: {e}")
        conn.rollback()
    finally:
        conn.close()

def sync_status(master_csv):
    print(f"🔄 Syncing active status against Master List: {master_csv}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    active_charity_numbers = set()
    
    try:
        # 1. Load Master List IDs
        print("   ⏳ Loading master list...")
        with open(master_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.DictReader(f)
            # Find ID column
            id_col = next((h for h in reader.fieldnames if 'number' in normalize_column_name(h) or 'reg' in normalize_column_name(h)), None)
            
            if not id_col:
                print("❌ Could not find 'Charity Number' column in Master CSV.")
                return
                
            for row in reader:
                num = row.get(id_col, '').strip()
                if num:
                    active_charity_numbers.add(num)
        
        print(f"   📋 Loaded {len(active_charity_numbers)} active charity numbers.")
        
        # 2. Check DB
        print("   🔍 Checking database...")
        cursor.execute("SELECT id, name, charity_number FROM funders WHERE is_active = TRUE AND charity_number IS NOT NULL")
        db_funders = cursor.fetchall()
        
        deactivated_count = 0
        
        for funder in db_funders:
            f_id, f_name, f_num = funder
            
            if f_num not in active_charity_numbers:
                print(f"   ❌ Deactivating: {f_name} (ID: {f_num}) - Not in Master List")
                cursor.execute("UPDATE funders SET is_active = FALSE WHERE id = %s", (f_id,))
                deactivated_count += 1
        
        conn.commit()
        print(f"✅ Sync Complete!")
        print(f"   🔻 Deactivated: {deactivated_count} foundations")
        
    except Exception as e:
        print(f"❌ Sync Failed: {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Grant Seeker Data Management Tool")
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Import Command
    import_parser = subparsers.add_parser('import', help='Import new foundations from CSV')
    import_parser.add_argument('--file', required=True, help='Path to CSV file containing new trusts')
    
    # Sync Command
    sync_parser = subparsers.add_parser('sync', help='Sync status against Master Charity List CSV')
    sync_parser.add_argument('--file', required=True, help='Path to Master List CSV (from Charity Commission)')
    
    args = parser.parse_args()
    
    if args.command == 'import':
        import_funders(args.file)
    elif args.command == 'sync':
        sync_status(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()