#!/usr/bin/env python3
"""
Test UKCAT matching on existing funders to verify the system works
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
db_url = os.getenv('DATABASE_URL')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

try:
    # Check current funders table structure
    print("📊 Checking funders table structure...")
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'funders' 
        ORDER BY ordinal_position
    """)
    
    columns = cursor.fetchall()
    for col_name, data_type in columns:
        print(f"  {col_name}: {data_type}")
    
    print(f"\n📊 Total funders in database: {cursor.execute('SELECT COUNT(*) FROM funders')}")
    total = cursor.fetchone()[0]
    print(f"  {total} funders")
    
    # Check some sample UK charity names
    print(f"\n🔍 Sample funder names:")
    cursor.execute("SELECT name FROM funders WHERE name LIKE '%Charity%' OR name LIKE '%Trust%' OR name LIKE '%Foundation%' LIMIT 5")
    uk_names = cursor.fetchall()
    
    for name_tuple in uk_names:
        name = name_tuple[0]
        print(f"  - {name}")
    
    # Check if any have descriptions
    print(f"\n🔍 Sample descriptions:")
    cursor.execute("SELECT name, description FROM funders WHERE description IS NOT NULL AND description != '' LIMIT 3")
    descriptions = cursor.fetchall()
    
    for name, desc in descriptions:
        print(f"Name: {name}")
        print(f"Description: {desc[:150]}...")
        print("---")

except Exception as e:
    print(f"❌ Error: {e}")
finally:
    conn.close()