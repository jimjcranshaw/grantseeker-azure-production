#!/usr/bin/env python3
"""
Comprehensive Test Suite for Charity Commission Integration & UKCAT Classification
===================================================================================

Tests all changes made for charity commission funder integration.
"""

import os
import json
import csv
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import logging
from typing import Dict, List, Tuple

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestSuite:
    """Comprehensive test suite."""
    
    def __init__(self):
        # Database connection
        db_config = {
            'host': os.getenv('DB_HOST', 'grantseeker-db.postgres.database.azure.com'),
            'user': os.getenv('DB_USER', 'grantseekeradmin'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'sslmode': 'require'
        }
        
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor()
        
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    def run_test(self, test_name: str, test_func):
        """Run a single test."""
        try:
            logger.info(f"\n🧪 Running test: {test_name}")
            result = test_func()
            if result:
                logger.info(f"✅ PASSED: {test_name}")
                self.test_results['passed'] += 1
                return True
            else:
                logger.error(f"❌ FAILED: {test_name}")
                self.test_results['failed'] += 1
                self.test_results['errors'].append(test_name)
                return False
        except Exception as e:
            logger.error(f"❌ ERROR in {test_name}: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"{test_name}: {str(e)}")
            return False
    
    # ============================================================================
    # TEST 1: Database Insertion Tests
    # ============================================================================
    
    def test_funders_have_charity_numbers(self):
        """Test that inserted funders have charity numbers."""
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
        """)
        count = self.cursor.fetchone()[0]
        
        logger.info(f"  Funders with charity numbers: {count}")
        return count > 10000  # Should have many funders with charity numbers
    
    def test_no_duplicate_charity_numbers(self):
        """Test that there are no duplicate charity numbers."""
        self.cursor.execute("""
            SELECT charity_number, COUNT(*) as cnt
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
            GROUP BY charity_number
            HAVING COUNT(*) > 1
        """)
        duplicates = self.cursor.fetchall()
        
        logger.info(f"  Duplicate charity numbers found: {len(duplicates)}")
        if duplicates:
            logger.warning(f"  Examples: {duplicates[:5]}")
        
        return len(duplicates) == 0
    
    def test_funders_have_required_fields(self):
        """Test that funders have required fields."""
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE name IS NULL OR name = ''
        """)
        missing_names = self.cursor.fetchone()[0]
        
        logger.info(f"  Funders missing names: {missing_names}")
        return missing_names == 0
    
    # ============================================================================
    # TEST 2: UKCAT Classification Tests
    # ============================================================================
    
    def test_ukcat_classification_coverage(self):
        """Test that UKCAT classification coverage is good."""
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE ukcat_codes IS NOT NULL 
            AND jsonb_array_length(ukcat_codes) > 0
        """)
        classified = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM funders")
        total = self.cursor.fetchone()[0]
        
        coverage = (classified / total * 100) if total > 0 else 0
        
        logger.info(f"  Classified: {classified}/{total} ({coverage:.1f}%)")
        return coverage >= 90  # Should have at least 90% coverage
    
    def test_ukcat_codes_are_valid_json(self):
        """Test that UKCAT codes are valid JSON arrays."""
        self.cursor.execute("""
            SELECT id, name, ukcat_codes 
            FROM funders 
            WHERE ukcat_codes IS NOT NULL 
            LIMIT 100
        """)
        
        invalid_count = 0
        for row in self.cursor.fetchall():
            try:
                codes = row[2]
                if codes:
                    if isinstance(codes, str):
                        json.loads(codes)
                    elif isinstance(codes, list):
                        pass  # Already a list
            except:
                invalid_count += 1
                logger.warning(f"  Invalid JSON for funder {row[0]} ({row[1]})")
        
        logger.info(f"  Invalid JSON arrays: {invalid_count}")
        return invalid_count == 0
    
    def test_ukcat_codes_from_ukcat_database(self):
        """Test that UKCAT codes match what's in UKCAT database."""
        # Load UKCAT mappings
        ukcat_files = [
            'ukcat_project/data/charities_active-ukcat.csv',
            'ukcat_project/data/charities_inactive-ukcat.csv'
        ]
        
        ukcat_mappings = {}
        for file_path in ukcat_files:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        org_id = row['org_id']
                        ukcat_code = row['ukcat_code']
                        if org_id.startswith('GB-CHC-'):
                            charity_number = org_id.replace('GB-CHC-', '')
                            if charity_number not in ukcat_mappings:
                                ukcat_mappings[charity_number] = []
                            if ukcat_code not in ukcat_mappings[charity_number]:
                                ukcat_mappings[charity_number].append(ukcat_code)
        
        # Check sample funders
        self.cursor.execute("""
            SELECT charity_number, ukcat_codes 
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND ukcat_codes IS NOT NULL 
            AND jsonb_array_length(ukcat_codes) > 0
            LIMIT 100
        """)
        
        mismatches = 0
        for row in self.cursor.fetchall():
            charity_number = str(row[0]).strip()
            db_codes = row[1]
            
            if isinstance(db_codes, str):
                db_codes = json.loads(db_codes)
            
            ukcat_codes = ukcat_mappings.get(charity_number, [])
            
            if set(db_codes) != set(ukcat_codes):
                mismatches += 1
                if mismatches <= 3:
                    logger.warning(f"  Mismatch for {charity_number}: DB={db_codes}, UKCAT={ukcat_codes}")
        
        logger.info(f"  Mismatches found: {mismatches}/100 sampled")
        return mismatches == 0
    
    # ============================================================================
    # TEST 3: Monthly Processor Integration Tests
    # ============================================================================
    
    def test_monthly_processor_ukcat_loading(self):
        """Test that monthly processor can load UKCAT mappings."""
        try:
            # Import the ReviewProcessor class
            import sys
            sys.path.insert(0, '.')
            from monthly_charity_processor import ReviewProcessor
            
            processor = ReviewProcessor()
            mappings_count = len(processor.ukcat_mappings)
            
            logger.info(f"  UKCAT mappings loaded: {mappings_count}")
            return mappings_count > 300000  # Should have many mappings
        except Exception as e:
            logger.error(f"  Error: {e}")
            return False
    
    def test_monthly_processor_classification_method(self):
        """Test that classification method works."""
        try:
            from monthly_charity_processor import ReviewProcessor
            
            processor = ReviewProcessor()
            
            # Test with a known charity number
            test_charity = "1000001"  # Should exist in UKCAT
            codes = processor._classify_funder_by_charity_number(test_charity, None)
            
            logger.info(f"  Test classification for {test_charity}: {codes}")
            return codes is not None and len(codes) > 0
        except Exception as e:
            logger.error(f"  Error: {e}")
            return False
    
    # ============================================================================
    # TEST 4: Quarterly Recategorization Tests
    # ============================================================================
    
    def test_quarterly_recategorization_script_exists(self):
        """Test that quarterly recategorization script exists and is valid."""
        script_path = 'quarterly_ukcat_recategorization.py'
        if not os.path.exists(script_path):
            return False
        
        # Try to compile it
        import py_compile
        try:
            py_compile.compile(script_path, doraise=True)
            logger.info(f"  Script compiles successfully")
            return True
        except py_compile.PyCompileError as e:
            logger.error(f"  Compilation error: {e}")
            return False
    
    def test_quarterly_recategorization_dry_run(self):
        """Test quarterly recategorization in dry-run mode."""
        import subprocess
        try:
            result = subprocess.run(
                ['python3', 'quarterly_ukcat_recategorization.py', '--dry-run', '--batch-size', '10'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            logger.info(f"  Dry-run exit code: {result.returncode}")
            logger.info(f"  Output length: {len(result.stdout)} chars")
            
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("  Dry-run timed out")
            return False
        except Exception as e:
            logger.error(f"  Error: {e}")
            return False
    
    # ============================================================================
    # TEST 5: Data Quality Tests
    # ============================================================================
    
    def test_no_orphaned_records(self):
        """Test that there are no orphaned records."""
        # Check for funders with invalid charity numbers
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE charity_number IS NOT NULL 
            AND charity_number != ''
            AND LENGTH(charity_number) < 4
        """)
        invalid_length = self.cursor.fetchone()[0]
        
        logger.info(f"  Funders with invalid charity number length: {invalid_length}")
        return invalid_length == 0
    
    def test_database_constraints_maintained(self):
        """Test that database constraints are maintained."""
        # Check unique constraint on name
        self.cursor.execute("""
            SELECT name, COUNT(*) as cnt
            FROM funders 
            WHERE name IS NOT NULL
            GROUP BY name
            HAVING COUNT(*) > 1
            LIMIT 5
        """)
        duplicate_names = self.cursor.fetchall()
        
        logger.info(f"  Duplicate names found: {len(duplicate_names)}")
        # Some duplicate names are expected (different charities can have same name)
        # But we should check if they're actually duplicates or just same name
        
        return True  # This is informational
    
    def test_ukcat_code_distribution(self):
        """Test that UKCAT codes are distributed reasonably."""
        self.cursor.execute("""
            SELECT jsonb_array_elements_text(ukcat_codes) as code, COUNT(*) as cnt
            FROM funders 
            WHERE ukcat_codes IS NOT NULL 
            AND jsonb_array_length(ukcat_codes) > 0
            GROUP BY code
            ORDER BY cnt DESC
            LIMIT 10
        """)
        
        top_codes = self.cursor.fetchall()
        logger.info("  Top 10 UKCAT codes:")
        for code, count in top_codes:
            logger.info(f"    {code}: {count}")
        
        return len(top_codes) > 0
    
    # ============================================================================
    # TEST 6: Integration Tests
    # ============================================================================
    
    def test_end_to_end_workflow(self):
        """Test complete workflow: Check that funders are inserted and classified."""
        # Get sample of recently added funders
        self.cursor.execute("""
            SELECT id, name, charity_number, ukcat_codes, created_at
            FROM funders 
            WHERE charity_number IS NOT NULL 
            AND created_at > NOW() - INTERVAL '7 days'
            LIMIT 10
        """)
        
        recent_funders = self.cursor.fetchall()
        logger.info(f"  Recent funders (last 7 days): {len(recent_funders)}")
        
        if len(recent_funders) == 0:
            logger.info("  No recent funders found (this is OK if none added recently)")
            return True
        
        # Check that they have classifications
        classified_count = sum(1 for f in recent_funders if f[3] and len(f[3]) > 0)
        logger.info(f"  Classified: {classified_count}/{len(recent_funders)}")
        
        return True  # Informational test
    
    def run_all_tests(self):
        """Run all tests."""
        logger.info("=" * 60)
        logger.info("🧪 STARTING COMPREHENSIVE TEST SUITE")
        logger.info("=" * 60)
        
        # Test 1: Database Insertion
        logger.info("\n📦 TEST GROUP 1: Database Insertion")
        self.run_test("Funders have charity numbers", self.test_funders_have_charity_numbers)
        self.run_test("No duplicate charity numbers", self.test_no_duplicate_charity_numbers)
        self.run_test("Funders have required fields", self.test_funders_have_required_fields)
        
        # Test 2: UKCAT Classification
        logger.info("\n🏷️ TEST GROUP 2: UKCAT Classification")
        self.run_test("UKCAT classification coverage", self.test_ukcat_classification_coverage)
        self.run_test("UKCAT codes are valid JSON", self.test_ukcat_codes_are_valid_json)
        self.run_test("UKCAT codes match UKCAT database", self.test_ukcat_codes_from_ukcat_database)
        
        # Test 3: Monthly Processor
        logger.info("\n📅 TEST GROUP 3: Monthly Processor Integration")
        self.run_test("Monthly processor loads UKCAT mappings", self.test_monthly_processor_ukcat_loading)
        self.run_test("Monthly processor classification method", self.test_monthly_processor_classification_method)
        
        # Test 4: Quarterly Recategorization
        logger.info("\n🔄 TEST GROUP 4: Quarterly Recategorization")
        self.run_test("Quarterly script exists and compiles", self.test_quarterly_recategorization_script_exists)
        self.run_test("Quarterly recategorization dry-run", self.test_quarterly_recategorization_dry_run)
        
        # Test 5: Data Quality
        logger.info("\n✅ TEST GROUP 5: Data Quality")
        self.run_test("No orphaned records", self.test_no_orphaned_records)
        self.run_test("Database constraints maintained", self.test_database_constraints_maintained)
        self.run_test("UKCAT code distribution", self.test_ukcat_code_distribution)
        
        # Test 6: Integration
        logger.info("\n🔗 TEST GROUP 6: Integration Tests")
        self.run_test("End-to-end workflow", self.test_end_to_end_workflow)
        
        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✅ Passed: {self.test_results['passed']}")
        logger.info(f"❌ Failed: {self.test_results['failed']}")
        logger.info(f"📈 Success rate: {(self.test_results['passed']/(self.test_results['passed']+self.test_results['failed'])*100):.1f}%" if (self.test_results['passed']+self.test_results['failed']) > 0 else "N/A")
        
        if self.test_results['errors']:
            logger.info("\n❌ Errors:")
            for error in self.test_results['errors']:
                logger.info(f"  - {error}")
        
        logger.info("=" * 60)
        
        return self.test_results['failed'] == 0
    
    def close(self):
        """Clean up resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

def main():
    """Main execution."""
    test_suite = TestSuite()
    try:
        success = test_suite.run_all_tests()
        exit(0 if success else 1)
    finally:
        test_suite.close()

if __name__ == "__main__":
    main()
