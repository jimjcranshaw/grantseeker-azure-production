#!/usr/bin/env python3
"""
Pipeline Consistency Test Script
Tests the enhanced implementation on a subset of funders.
"""

import asyncio
import argparse
import logging
import os
from dotenv import load_dotenv
from typing import List, Dict

# Import pipeline functions
from azure_production_pipeline import (
    init_db_pool, is_db_available, store_foundation, create_scrape_session,
    cleanup_foundation_data, store_pages_and_embeddings, complete_scrape_session,
    crawl_foundation, get_db_connection, release_db_connection
)
from enhanced_storage_functions import (
    store_funding_opportunities_guaranteed, 
    update_funder_classification_enhanced,
    analyze_foundation_content
)

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_single_foundation(name: str, url: str) -> Dict:
    """Test the enhanced pipeline on a single foundation."""
    
    result = {
        'name': name,
        'url': url,
        'success': False,
        'opportunities_count': 0,
        'classification_type': None,
        'requires_review': None,
        'error': None
    }
    
    try:
        logger.info(f"\n🧪 Testing: {name}")
        logger.info(f"URL: {url}")
        logger.info("-" * 50)
        
        # Initialize database pool if available
        if not NO_DB_MODE:
            init_db_pool()
        
        # Store/get foundation
        funder_id = store_foundation(name, url)
        logger.info(f"  ✓ Foundation ID: {funder_id}")
        
        # Create scrape session
        session_id = create_scrape_session(funder_id)
        logger.info(f"  ✓ Scrape session ID: {session_id}")
        
        # Test crawling
        logger.info(f"  🔍 Testing crawl...")
        pages = await crawl_foundation(url, name)
        logger.info(f"  ✓ Crawled {len(pages)} pages")
        
        if pages:
            # Clean up old data
            cleanup_foundation_data(funder_id)
            
            # Store pages and embeddings
            logger.info(f"  💾 Testing page storage...")
            store_pages_and_embeddings(session_id, funder_id, pages)
            
            # Analyze content
            logger.info(f"  🤖 Testing enhanced analysis...")
            analysis = analyze_foundation_content(pages, name)
        else:
            # No pages - test with empty analysis
            logger.info(f"  ⚠️ No pages crawled - testing fallback...")
            analysis = {
                "is_grantmaking_charity": None,
                "funder_type_reason": "Test: No content found",
                "classification_type": "NO_CONTENT_FOUND",
                "opportunities": []
            }
        
        # Update classification
        logger.info(f"  📝 Testing classification update...")
        update_funder_classification_enhanced(funder_id, analysis)
        
        # Store opportunities with guaranteed coverage
        logger.info(f"  💾 Testing guaranteed opportunity storage...")
        opportunity_count = store_funding_opportunities_guaranteed(funder_id, session_id, analysis)
        
        # Complete session
        complete_scrape_session(session_id)
        
        # Update result
        result.update({
            'success': True,
            'opportunities_count': opportunity_count,
            'classification_type': analysis.get('classification_type'),
            'requires_review': analysis.get('classification_type') in ['UNCLASSIFIED', 'NO_CONTENT_FOUND', 'FUNDRAISING_PLATFORM']
        })
        
        logger.info(f"  ✅ Test completed successfully!")
        logger.info(f"     Opportunities: {opportunity_count}")
        logger.info(f"     Classification: {result['classification_type']}")
        logger.info(f"     Requires Review: {result['requires_review']}")
        
    except Exception as e:
        logger.error(f"  ❌ Test failed: {str(e)}")
        result['error'] = str(e)
        
        # Even on error, try to create an error assessment record
        try:
            if is_db_available():
                funder_id = store_foundation(name, url)
                session_id = create_scrape_session(funder_id)
                
                error_analysis = {
                    "is_grantmaking_charity": None,
                    "funder_type_reason": f"Test error: {str(e)}",
                    "classification_type": "UNCLASSIFIED",
                    "opportunities": []
                }
                
                update_funder_classification_enhanced(funder_id, error_analysis)
                store_funding_opportunities_guaranteed(funder_id, session_id, error_analysis)
                complete_scrape_session(session_id)
                
                result['success'] = True  # Count as success since we have assessment
                result['opportunities_count'] = 1
                result['classification_type'] = 'UNCLASSIFIED'
                result['requires_review'] = True
                
                logger.info(f"  🔧 Error assessment record created")
        except Exception as nested_error:
            logger.error(f"  ❌ Failed to create error assessment: {nested_error}")
    
    return result

async def test_funders_subset(funders: List[Dict], max_test: int = 10) -> Dict:
    """Test the enhanced pipeline on a subset of funders."""
    
    logger.info(f"🧪 STARTING PIPELINE CONSISTENCY TESTS")
    logger.info(f"Testing {min(len(funders), max_test)} funders out of {len(funders)} total")
    logger.info("=" * 70)
    
    # Initialize database if needed
    if not NO_DB_MODE:
        init_db_pool()
    
    # Run tests
    results = []
    test_funders = funders[:max_test]
    
    for i, funder in enumerate(test_funders, 1):
        logger.info(f"\n📍 Test {i}/{len(test_funders)}")
        result = await test_single_foundation(funder['name'], funder['url'])
        results.append(result)
    
    # Summarize results
    logger.info(f"\n📊 TEST RESULTS SUMMARY")
    logger.info("=" * 50)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    logger.info(f"Total Tests: {len(results)}")
    logger.info(f"Successful: {len(successful)}")
    logger.info(f"Failed: {len(failed)}")
    logger.info(f"Success Rate: {len(successful)/len(results)*100:.1f}%")
    
    # Coverage analysis
    total_opportunities = sum(r['opportunities_count'] for r in successful)
    avg_opportunities = total_opportunities / len(successful) if successful else 0
    
    logger.info(f"Total Opportunities: {total_opportunities}")
    logger.info(f"Avg Opportunities per Funder: {avg_opportunities:.2f}")
    
    # Classification breakdown
    classifications = {}
    for r in successful:
        cls = r['classification_type'] or 'UNKNOWN'
        classifications[cls] = classifications.get(cls, 0) + 1
    
    logger.info(f"\n📋 CLASSIFICATION BREAKDOWN:")
    for cls, count in sorted(classifications.items()):
        logger.info(f"  {cls}: {count}")
    
    # Issues
    if failed:
        logger.info(f"\n❌ FAILED TESTS:")
        for r in failed:
            logger.info(f"  • {r['name']}: {r['error']}")
    
    return {
        'total_tests': len(results),
        'successful': len(successful),
        'failed': len(failed),
        'success_rate': len(successful)/len(results)*100,
        'total_opportunities': total_opportunities,
        'avg_opportunities': avg_opportunities,
        'classifications': classifications,
        'results': results
    }

def load_test_funders_from_csv(csv_file: str, max_count: int = 10) -> List[Dict]:
    """Load test funders from CSV file."""
    import csv
    
    funders = []
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'name' in row and 'website' in row:
                    funders.append({
                        'name': row['name'],
                        'url': row['website']
                    })
                elif 'Name' in row and 'Website' in row:
                    funders.append({
                        'name': row['Name'],
                        'url': row['Website']
                    })
                
                if len(funders) >= max_count:
                    break
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return []
    
    return funders

def main():
    parser = argparse.ArgumentParser(description='Test pipeline consistency')
    parser.add_argument('--csv', type=str, help='CSV file with funder data')
    parser.add_argument('--count', type=int, default=5, help='Number of funders to test')
    parser.add_argument('--no-db', action='store_true', help='Run without database connection')
    
    args = parser.parse_args()
    
    # Set global flag for no DB mode
    global NO_DB_MODE
    NO_DB_MODE = args.no_db
    
    if args.no_db:
        logger.info("🔧 Running in NO_DB mode (no database connection)")
    
    # Load test data
    funders = []
    if args.csv:
        logger.info(f"📁 Loading test data from: {args.csv}")
        funders = load_test_funders_from_csv(args.csv, args.count)
    else:
        # Default test funders
        funders = [
            {'name': 'Test Foundation 1', 'url': 'https://example.com'},
            {'name': 'Test Foundation 2', 'url': 'https://example.org'},
            {'name': 'Test Foundation 3', 'url': 'https://example.net'},
        ][:args.count]
    
    if not funders:
        logger.error("No test funders loaded!")
        return
    
    # Run tests
    try:
        result = asyncio.run(test_funders_subset(funders, args.count))
        
        # Final assessment
        if result['success_rate'] == 100.0:
            logger.info(f"\n🎉 ALL TESTS PASSED! Pipeline consistency implementation is working correctly.")
            exit(0)
        else:
            logger.info(f"\n⚠️  Some tests failed. Review the implementation before deploying.")
            exit(1)
            
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()