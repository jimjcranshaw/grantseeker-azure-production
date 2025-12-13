#!/usr/bin/env python3
"""
Pipeline Consistency Validation Script
Validates that 100% of funders have opportunities and proper classification.
"""

import psycopg2
import os
from dotenv import load_dotenv
import argparse

def validate_100_percent_coverage():
    """Validate that 100% of funders have opportunities."""
    
    # Load environment
    load_dotenv()
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT'),
            sslmode='require'
        )
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Please check your .env file and database connection.")
        return None
        
    cursor = conn.cursor()
    
    try:
        print("🔍 PIPELINE CONSISTENCY VALIDATION")
        print("=" * 60)
        
        # Check 1: No funders without opportunities
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funders f 
            WHERE f.is_active = TRUE 
            AND f.last_checked IS NOT NULL
            AND f.id NOT IN (SELECT DISTINCT funder_id FROM funding_opportunities WHERE funder_id IS NOT NULL)
        """)
        gap_count = cursor.fetchone()[0]
        
        # Check 2: All active funders have been processed
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funders 
            WHERE is_active = TRUE 
            AND last_checked IS NOT NULL
        """)
        processed_funders = cursor.fetchone()[0]
        
        # Check 3: All opportunities have proper classification
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funding_opportunities fo
            JOIN funders f ON fo.funder_id = f.id
            WHERE f.is_grantmaking_charity IS NULL
            AND f.is_active = TRUE
        """)
        unclassified_count = cursor.fetchone()[0]
        
        # Check 4: Assessment records are properly tagged
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funding_opportunities 
            WHERE is_default_assessment = true
            AND (opportunity_source IS NULL OR opportunity_source = '')
        """)
        untagged_assessments = cursor.fetchone()[0]
        
        # Check 5: Generate breakdown by classification
        cursor.execute("""
            SELECT 
                f.classification_type,
                COUNT(DISTINCT f.id) as funder_count,
                COUNT(fo.id) as opportunity_count,
                COUNT(CASE WHEN f.requires_manual_review = true THEN 1 END) as needing_review
            FROM funders f
            LEFT JOIN funding_opportunities fo ON f.id = fo.funder_id
            WHERE f.is_active = TRUE
            GROUP BY f.classification_type
            ORDER BY funder_count DESC
        """)
        breakdown = cursor.fetchall()
        
        # Check 6: Coverage by opportunity source
        cursor.execute("""
            SELECT 
                opportunity_source,
                COUNT(*) as count
            FROM funding_opportunities
            WHERE opportunity_source IS NOT NULL
            GROUP BY opportunity_source
            ORDER BY count DESC
        """)
        source_breakdown = cursor.fetchall()
        
        # Print results
        print(f"\n📊 COVERAGE ANALYSIS:")
        print(f"   Total Active Funders: {processed_funders}")
        print(f"   Funders WITHOUT Opportunities: {gap_count}")
        print(f"   Coverage Rate: {((processed_funders - gap_count) / processed_funders * 100):.1f}%")
        
        print(f"\n🔍 QUALITY CHECKS:")
        print(f"   Unclassified Funders: {unclassified_count}")
        print(f"   Untagged Assessments: {untagged_assessments}")
        
        print(f"\n📋 CLASSIFICATION BREAKDOWN:")
        print("-" * 50)
        total_opportunities = 0
        for classification, funder_count, opp_count, needing_review in breakdown:
            total_opportunities += opp_count
            classification_display = classification if classification else 'UNCLASSIFIED'
            funder_count_display = funder_count if funder_count else 0
            opp_count_display = opp_count if opp_count else 0
            needing_review_display = needing_review if needing_review else 0
            print(f"{classification_display:<25}: {funder_count_display:>4} funders, {opp_count_display:>4} opportunities, {needing_review_display:>3} need review")
        
        print(f"\n📈 OPPORTUNITY SOURCES:")
        print("-" * 30)
        for source, count in source_breakdown:
            print(f"{source:<25}: {count:>4} opportunities")
        
        # Summary statistics
        avg_opportunities = total_opportunities / processed_funders if processed_funders > 0 else 0
        coverage_rate = ((processed_funders - gap_count) / processed_funders * 100) if processed_funders > 0 else 0
        
        print(f"\n📊 SUMMARY STATISTICS:")
        print(f"   Total Active Funders: {processed_funders}")
        print(f"   Total Opportunities: {total_opportunities}")
        print(f"   Average Opportunities per Funder: {avg_opportunities:.2f}")
        print(f"   Coverage Rate: {coverage_rate:.1f}%")
        
        # Determine if validation passed
        validation_passed = (
            gap_count == 0 and 
            unclassified_count == 0 and 
            untagged_assessments == 0 and
            coverage_rate == 100.0
        )
        
        print(f"\n{'🎉 VALIDATION PASSED' if validation_passed else '❌ VALIDATION FAILED'}")
        print("=" * 60)
        
        if not validation_passed:
            print("\n🔧 ISSUES TO FIX:")
            if gap_count > 0:
                print(f"   • {gap_count} funders missing opportunities")
            if unclassified_count > 0:
                print(f"   • {unclassified_count} funders need classification")
            if untagged_assessments > 0:
                print(f"   • {untagged_assessments} assessments need proper tagging")
            if coverage_rate < 100.0:
                print(f"   • Coverage rate is {coverage_rate:.1f}%, needs to be 100%")
        
        return {
            'gap_count': gap_count,
            'processed_funders': processed_funders,
            'unclassified_count': unclassified_count,
            'untagged_assessments': untagged_assessments,
            'coverage_rate': coverage_rate,
            'breakdown': breakdown,
            'source_breakdown': source_breakdown,
            'validation_passed': validation_passed
        }
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return None
    finally:
        conn.close()

def validate_sample_funders(sample_size: int = 100):
    """Validate a sample of funders for testing."""
    
    load_dotenv()
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT'),
            sslmode='require'
        )
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None
        
    cursor = conn.cursor()
    
    try:
        print(f"🔍 SAMPLE VALIDATION ({sample_size} funders)")
        print("=" * 50)
        
        # Get a sample of funders
        cursor.execute("""
            SELECT id, name, website, classification_type, requires_manual_review
            FROM funders 
            WHERE is_active = TRUE 
            AND last_checked IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
        """, (sample_size,))
        
        sample_funders = cursor.fetchall()
        
        issues = []
        for funder_id, name, website, classification_type, requires_review in sample_funders:
            # Check if they have opportunities
            cursor.execute("""
                SELECT COUNT(*) FROM funding_opportunities WHERE funder_id = %s
            """, (funder_id,))
            opp_count = cursor.fetchone()[0]
            
            if opp_count == 0:
                issues.append(f"No opportunities: {name}")
            
            # Check classification quality
            if classification_type is None:
                issues.append(f"No classification: {name}")
            
            # Check for proper opportunity types
            if opp_count > 0:
                cursor.execute("""
                    SELECT DISTINCT application_form_type 
                    FROM funding_opportunities 
                    WHERE funder_id = %s
                """, (funder_id,))
                form_types = [row[0] for row in cursor.fetchall()]
                
                if 'UNKNOWN' in form_types:
                    issues.append(f"Unknown form type: {name}")
        
        print(f"\n📊 SAMPLE RESULTS:")
        print(f"   Sample Size: {len(sample_funders)}")
        print(f"   Issues Found: {len(issues)}")
        
        if issues:
            print(f"\n⚠️  ISSUES:")
            for issue in issues[:10]:  # Show first 10 issues
                print(f"   • {issue}")
            if len(issues) > 10:
                print(f"   ... and {len(issues) - 10} more issues")
        else:
            print(f"\n✅ Sample validation passed!")
        
        return len(issues) == 0
        
    except Exception as e:
        print(f"❌ Sample validation error: {e}")
        return False
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description='Validate pipeline consistency')
    parser.add_argument('--sample', type=int, help='Validate a random sample of funders')
    parser.add_argument('--full', action='store_true', help='Run full validation (default)')
    
    args = parser.parse_args()
    
    if args.sample:
        success = validate_sample_funders(args.sample)
    else:
        result = validate_100_percent_coverage()
        success = result['validation_passed'] if result else False
    
    if success:
        print("\n🎉 Pipeline consistency validated successfully!")
        exit(0)
    else:
        print("\n❌ Pipeline consistency validation failed!")
        exit(1)

if __name__ == "__main__":
    main()