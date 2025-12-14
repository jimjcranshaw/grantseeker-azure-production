#!/usr/bin/env python3
"""
Debug UKCAT Classification Issues
================================
"""

import os
import psycopg2
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set DATABASE_URL from individual components
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}?"
        f"sslmode={os.getenv('DB_SSLMODE', 'require')}"
    )

print(f"🔗 Using DATABASE_URL: {os.getenv('DATABASE_URL')[:50]}...")

try:
    # Connect to database
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    print("✅ Database connection successful")
    
    # Check funders table structure
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name = 'funders' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    print("\n📊 Funders table structure:")
    for col in columns:
        print(f"  {col[0]}: {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
    
    # Check current classification status
    cursor.execute("SELECT COUNT(*) FROM funders")
    total_funders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM funders WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0")
    classified = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM funders WHERE ukcat_codes IS NULL")
    null_codes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM funders WHERE ukcat_codes = '[]'::jsonb")
    empty_codes = cursor.fetchone()[0]
    
    print(f"\n📊 Classification Status:")
    print(f"  Total funders: {total_funders}")
    print(f"  Classified: {classified}")
    print(f"  NULL codes: {null_codes}")
    print(f"  Empty codes: {empty_codes}")
    print(f"  Unclassified: {total_funders - classified}")
    
    # Get sample unclassified funder
    cursor.execute("""
        SELECT id, name, description, ukcat_codes 
        FROM funders 
        WHERE ukcat_codes IS NULL OR ukcat_codes = '[]'::jsonb
        LIMIT 3
    """)
    samples = cursor.fetchall()
    
    print(f"\n📋 Sample unclassified funders:")
    for funder_id, name, description, codes in samples:
        print(f"  ID {funder_id}: {name[:50]}{'...' if len(name) > 50 else ''}")
        if description:
            print(f"    Desc: {description[:80]}{'...' if len(description) > 80 else ''}")
        print(f"    Codes: {codes}")
        print()
    
    # Check UKCAT patterns
    cursor.execute("SELECT COUNT(*) FROM ukcat_codes")
    pattern_count = cursor.fetchone()[0]
    print(f"📊 UKCAT patterns in database: {pattern_count}")
    
    # Get some sample patterns
    cursor.execute("""
        SELECT code, tag, regex_pattern, category
        FROM ukcat_codes 
        WHERE regex_pattern IS NOT NULL AND regex_pattern != ''
        LIMIT 5
    """)
    patterns = cursor.fetchall()
    
    print(f"\n📋 Sample UKCAT patterns:")
    for code, tag, pattern, category in patterns:
        print(f"  {code} ({category}): {tag}")
        print(f"    Pattern: {pattern[:60]}{'...' if len(pattern) > 60 else ''}")
        print()
    
    # Test pattern matching on a sample
    if samples:
        test_funder = samples[0]
        test_name = test_funder[1]
        test_desc = test_funder[2] or ""
        test_text = f"{test_name} {test_desc}".strip()
        
        print(f"🔍 Testing pattern matching on: {test_name}")
        print(f"    Text to analyze: {test_text[:100]}{'...' if len(test_text) > 100 else ''}")
        
        # Load patterns and test
        cursor.execute("""
            SELECT code, regex_pattern
            FROM ukcat_codes 
            WHERE regex_pattern IS NOT NULL AND regex_pattern != ''
            LIMIT 10
        """)
        test_patterns = cursor.fetchall()
        
        matches = []
        for code, pattern_str in test_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                if pattern.search(test_text):
                    matches.append(code)
                    print(f"    ✅ MATCH: {code}")
            except re.error as e:
                print(f"    ❌ INVALID PATTERN {code}: {e}")
        
        print(f"\n📊 Total matches found: {len(matches)}")
        if matches:
            print(f"    Matching codes: {matches}")
        else:
            print("    No matches found - this explains the 0% rate!")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()