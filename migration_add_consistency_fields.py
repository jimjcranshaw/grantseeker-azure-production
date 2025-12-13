#!/usr/bin/env python3
"""
Database Migration: Add Consistency Fields
Adds tracking columns to funders and funding_opportunities tables for pipeline consistency.
"""

import psycopg2
import os
from dotenv import load_dotenv

def migrate_database():
    """Add consistency fields to database."""
    
    # Load environment
    load_dotenv()
    
    # Database connection
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT'),
            sslmode='require'
        )
        
        cursor = conn.cursor()
        
        print("🔧 Starting database migration...")
        
        # Add columns to funders table
        print("📝 Adding columns to funders table...")
        
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS classification_type VARCHAR(50);
        """)
        print("  ✅ Added classification_type column")
        
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS assessment_notes TEXT;
        """)
        print("  ✅ Added assessment_notes column")
        
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS requires_manual_review BOOLEAN DEFAULT false;
        """)
        print("  ✅ Added requires_manual_review column")
        
        # Add columns to funding_opportunities table
        print("📝 Adding columns to funding_opportunities table...")
        
        cursor.execute("""
            ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS opportunity_source VARCHAR(50);
        """)
        print("  ✅ Added opportunity_source column")
        
        cursor.execute("""
            ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS is_default_assessment BOOLEAN DEFAULT false;
        """)
        print("  ✅ Added is_default_assessment column")
        
        # Add indexes for performance
        print("📝 Adding performance indexes...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_classification 
            ON funders(classification_type);
        """)
        print("  ✅ Added idx_funders_classification index")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_source 
            ON funding_opportunities(opportunity_source);
        """)
        print("  ✅ Added idx_opportunities_source index")
        
        # Commit all changes
        conn.commit()
        print("\n🎉 Database migration completed successfully!")
        
        # Verify columns were added
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'funders' 
            AND column_name IN ('classification_type', 'assessment_notes', 'requires_manual_review')
            ORDER BY column_name;
        """)
        
        print("\n📊 Verification - funders table columns:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")
        
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'funding_opportunities' 
            AND column_name IN ('opportunity_source', 'is_default_assessment')
            ORDER BY column_name;
        """)
        
        print("\n📊 Verification - funding_opportunities table columns:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")
            
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🚀 Starting Pipeline Consistency Database Migration")
    print("=" * 60)
    
    try:
        success = migrate_database()
        if success:
            print("\n✅ Migration completed successfully!")
            print("Database is now ready for enhanced pipeline consistency.")
        else:
            print("\n❌ Migration failed!")
            
    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        print("Please check database connection and permissions.")
        exit(1)