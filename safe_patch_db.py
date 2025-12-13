import psycopg2
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT'),
            sslmode='require'
        )
        return conn
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        sys.exit(1)

def patch_database():
    print("🛡️ Starting Database Patch Process...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if 'funders' table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'funders'
            );
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            print("❌ 'funders' table does not exist! Please run init_db.py first.")
            return

        # Check existing columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'funders';
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📋 Existing columns: {', '.join(columns)}")

        # 1. Add 'is_active' if missing
        if 'is_active' not in columns:
            print("⚠️ 'is_active' column missing. Adding it...")
            cursor.execute("ALTER TABLE funders ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
            print("✅ 'is_active' column added.")
        else:
            print("✅ 'is_active' column already exists.")

        # 2. Add 'charity_number' if missing
        if 'charity_number' not in columns:
            print("⚠️ 'charity_number' column missing. Adding it...")
            cursor.execute("ALTER TABLE funders ADD COLUMN charity_number TEXT;")
            print("✅ 'charity_number' column added.")
        else:
            print("✅ 'charity_number' column already exists.")

        # Commit changes
        conn.commit()
        print("🎉 Database verification & patching complete!")

    except Exception as e:
        print(f"❌ Patch failed: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    patch_database()