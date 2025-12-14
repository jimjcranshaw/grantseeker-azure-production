import psycopg2
import os
from dotenv import load_dotenv

# Explicitly load the .env file from the correct directory
dotenv_path = os.path.join(os.path.expanduser('~'), 'grantseeker-azure-production', '.env')
print(f"DEBUG: Looking for .env at {dotenv_path}")

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print("DEBUG: Loaded .env file")
else:
    print(f"Warning: .env file not found at {dotenv_path}")
    # Fallback for environments where .env might be in the current directory
    load_dotenv()

db_host = os.getenv('DB_HOST')
print(f"DEBUG: DB_HOST is set to: {db_host}")

conn = None  # Initialize conn to None

try:
    if not db_host:
        raise ValueError("DB_HOST environment variable is missing!")

    conn = psycopg2.connect(
        host=db_host,
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=os.getenv('DB_PORT'),
        sslmode='require'
    )

    cursor = conn.cursor()

    print("=" * 70)
    print("DATABASE ANALYSIS")
    print("=" * 70)

    # List all tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f"\n📋 Tables in database:")
    for table in tables:
        print(f"  - {table[0]}")

    print("\n" + "=" * 70)
    print("ROW COUNTS")
    print("=" * 70)

    # Count rows in each table
    for table in tables:
        table_name = table[0]
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  {table_name}: {count:,} rows")
        except psycopg2.Error as e:
            print(f"  Could not count rows in {table_name}: {e}")
            conn.rollback()


    print("\n" + "=" * 70)
    print("CHECK FOR ANALYSIS DATA")
    print("=" * 70)

    # Check if analyses are stored in funders table itself
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'funders'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    print(f"\nColumns in 'funders' table:")
    for col in columns:
        print(f"  - {col[0]}")

    # Check for a common analysis column name like 'description' or 'analysis'
    analysis_column = None
    funders_columns = [col[0] for col in columns]
    if 'description' in funders_columns:
        analysis_column = 'description'
    elif 'analysis' in funders_columns:
        analysis_column = 'analysis'

    if analysis_column:
        # Check if there's analysis data in the identified column in the funders table
        cursor.execute(f"""
            SELECT 
                name,
                CASE WHEN {analysis_column} IS NOT NULL AND LENGTH({analysis_column}) > 100 THEN 'Yes' ELSE 'No' END as has_analysis
            FROM funders
            WHERE {analysis_column} IS NOT NULL AND LENGTH({analysis_column}) > 100
            LIMIT 5
        """)
        print(f"\nFoundations with populated '{analysis_column}' column:")
        results = cursor.fetchall()
        if results:
            for name, has_analysis in results:
                print(f"  - {name}: {has_analysis}")
        else:
            print("  - None found.")
    else:
        print("\nNo 'description' or 'analysis' column found in 'funders' table.")


except psycopg2.OperationalError as e:
    print(f"Connection Error: Could not connect to the database. Please check your .env variables.")
    print(f"Details: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

finally:
    if conn:
        cursor.close()
        conn.close()