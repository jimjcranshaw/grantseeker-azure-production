#!/usr/bin/env python3
"""
Database Migration for Monthly Charity Tracking
==============================================

Adds tables and columns needed for the monthly charity processing system.

Author: Grant Seeker Pipeline  
Date: December 2025
"""

import psycopg2
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=os.getenv('DB_PORT'),
        sslmode='require'
    )

def run_migration():
    """Run the database migration."""
    print("🔧 Starting database migration...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Create monthly_imports table
        print("📋 Creating monthly_imports table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_imports (
                id SERIAL PRIMARY KEY,
                import_date DATE NOT NULL,
                source_file VARCHAR(500),
                total_processed INTEGER DEFAULT 0,
                grantmakers_found INTEGER DEFAULT 0,
                crawler_triggered INTEGER DEFAULT 0,
                review_completed INTEGER DEFAULT 0,
                database_imported INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Add columns to funders table
        print("📝 Adding columns to funders table...")
        
        # Check if columns exist before adding
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'funders' AND table_schema = 'public'
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        columns_to_add = [
            ('monthly_import_id', 'INTEGER REFERENCES monthly_imports(id)'),
            ('initial_classification', 'VARCHAR(100)'),
            ('manual_review_classification', 'VARCHAR(100)'),
            ('review_notes', 'TEXT'),
            ('reviewer_name', 'VARCHAR(100)'),
            ('review_date', 'TIMESTAMP'),
            ('import_batch_id', 'VARCHAR(100)')
        ]
        
        for column_name, column_def in columns_to_add:
            if column_name not in existing_columns:
                print(f"  Adding column: {column_name}")
                cursor.execute(f"""
                    ALTER TABLE funders ADD COLUMN {column_name} {column_def}
                """)
            else:
                print(f"  Column already exists: {column_name}")
        
        # 3. Create index on charity_number for faster lookups
        print("🔍 Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_charity_number 
            ON funders(charity_number)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_monthly_import 
            ON funders(monthly_import_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_manual_review 
            ON funders(manual_review_classification)
        """)
        
        # 4. Create trigger to update updated_at timestamp
        print("⏰ Creating update trigger...")
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        
        cursor.execute("""
            DROP TRIGGER IF EXISTS update_funders_updated_at ON funders;
            CREATE TRIGGER update_funders_updated_at
            BEFORE UPDATE ON funders
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)
        
        cursor.execute("""
            DROP TRIGGER IF EXISTS update_monthly_imports_updated_at ON monthly_imports;
            CREATE TRIGGER update_monthly_imports_updated_at
            BEFORE UPDATE ON monthly_imports
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)
        
        # 5. Create views for reporting
        print("📊 Creating reporting views...")
        
        # View for current month imports
        cursor.execute("""
            CREATE OR REPLACE VIEW current_month_imports AS
            SELECT 
                mi.*,
                COUNT(f.id) as total_funders,
                COUNT(CASE WHEN f.manual_review_classification IS NOT NULL THEN 1 END) as reviewed_funders,
                COUNT(CASE WHEN f.website IS NOT NULL THEN 1 END) as with_websites
            FROM monthly_imports mi
            LEFT JOIN funders f ON mi.id = f.monthly_import_id
            WHERE mi.import_date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY mi.id
            ORDER BY mi.created_at DESC;
        """)
        
        # View for review status
        cursor.execute("""
            CREATE OR REPLACE VIEW review_status_summary AS
            SELECT 
                manual_review_classification,
                COUNT(*) as count,
                COUNT(CASE WHEN website IS NOT NULL THEN 1 END) as with_websites
            FROM funders
            WHERE monthly_import_id IS NOT NULL
            GROUP BY manual_review_classification
            ORDER BY count DESC;
        """)
        
        conn.commit()
        print("✅ Migration completed successfully!")
        
        # 6. Show summary
        print("\n📈 Migration Summary:")
        
        cursor.execute("SELECT COUNT(*) FROM monthly_imports")
        import_count = cursor.fetchone()[0]
        print(f"  Monthly imports tracked: {import_count}")
        
        cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE monthly_import_id IS NOT NULL
        """)
        tracked_funders = cursor.fetchone()[0]
        print(f"  Funders with tracking data: {tracked_funders}")
        
        cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE monthly_import_id IS NOT NULL 
            AND manual_review_classification IS NOT NULL
        """)
        reviewed_funders = cursor.fetchone()[0]
        print(f"  Reviewed funders: {reviewed_funders}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

def rollback_migration():
    """Rollback the migration (use with caution)."""
    print("⚠️  Rolling back migration...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Drop views
        cursor.execute("DROP VIEW IF EXISTS review_status_summary")
        cursor.execute("DROP VIEW IF EXISTS current_month_imports")
        
        # Drop trigger
        cursor.execute("DROP TRIGGER IF EXISTS update_monthly_imports_updated_at ON monthly_imports")
        cursor.execute("DROP TRIGGER IF EXISTS update_funders_updated_at ON funders")
        cursor.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
        
        # Drop indexes
        cursor.execute("DROP INDEX IF EXISTS idx_funders_manual_review")
        cursor.execute("DROP INDEX IF EXISTS idx_funders_monthly_import")
        cursor.execute("DROP INDEX IF EXISTS idx_funders_charity_number")
        
        # Remove columns from funders table
        columns_to_remove = [
            'import_batch_id',
            'review_date',
            'reviewer_name',
            'review_notes',
            'manual_review_classification',
            'initial_classification',
            'monthly_import_id'
        ]
        
        for column in columns_to_remove:
            cursor.execute(f"ALTER TABLE funders DROP COLUMN IF EXISTS {column}")
        
        # Drop monthly_imports table
        cursor.execute("DROP TABLE IF EXISTS monthly_imports")
        
        conn.commit()
        print("✅ Migration rollback completed!")
        
    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Database migration for monthly charity tracking")
    parser.add_argument('--rollback', action='store_true', help='Rollback migration')
    
    args = parser.parse_args()
    
    if args.rollback:
        confirm = input("Are you sure you want to rollback the migration? (yes/no): ")
        if confirm.lower() == 'yes':
            rollback_migration()
        else:
            print("Rollback cancelled.")
    else:
        run_migration()

if __name__ == "__main__":
    main()