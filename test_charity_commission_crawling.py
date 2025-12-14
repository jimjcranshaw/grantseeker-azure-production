#!/usr/bin/env python3
"""
Test Charity Commission Page Crawling
=====================================

Tests the pipeline's ability to crawl Charity Commission profile pages
for funders without websites and extract opportunities.
"""

import asyncio
import sys
import os
import psycopg2
from dotenv import load_dotenv
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from azure_production_pipeline import (
    init_db_pool,
    get_db_connection,
    release_db_connection,
    process_foundation,
    load_funders_with_charity_commission_urls
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_charity_commission_crawling(test_count: int = 5):
    """
    Test crawling Charity Commission pages for funders without websites.
    
    Args:
        test_count: Number of funders to test (default: 5)
    """
    print("="*70)
    print("CHARITY COMMISSION CRAWLING TEST")
    print("="*70)
    print()
    
    # Initialize database
    init_db_pool()
    
    # Load test funders (with Charity Commission URLs)
    funders = load_funders_with_charity_commission_urls(limit=test_count)
    
    if not funders:
        print("❌ No funders found with Charity Commission URLs")
        print("   Run populate_charity_commission_urls.py first to populate URLs")
        return
    
    print(f"Found {len(funders)} funders to test")
    print()
    
    # Statistics
    stats = {
        'completed': 0,
        'skipped': 0,
        'failed': 0
    }
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(3)  # Process 3 at a time for testing
    
    # Process test funders
    tasks = []
    for funder_id, name, website_url in funders:
        print(f"  📋 {name}")
        print(f"     URL: {website_url}")
        tasks.append(
            process_foundation(name, website_url, semaphore, stats, funder_id=funder_id)
        )
    
    print()
    print("Starting processing...")
    print()
    
    await asyncio.gather(*tasks)
    
    # Check results
    print()
    print("="*70)
    print("TEST RESULTS")
    print("="*70)
    print(f"Completed: {stats['completed']}/{len(funders)}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print()
    
    # Verify opportunities were created
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for funder_id, name, website_url in funders:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM funding_opportunities 
                WHERE funder_id = %s
            """, (funder_id,))
            opp_count = cursor.fetchone()[0]
            print(f"  {name}: {opp_count} opportunities extracted")
        cursor.close()
    finally:
        release_db_connection(conn)
    
    print()
    print("="*70)
    
    if stats['completed'] > 0:
        print("✅ Test completed successfully!")
        print(f"   {stats['completed']} funders processed via Charity Commission pages")
    else:
        print("⚠️  No funders were successfully processed")
        print("   Check logs above for errors")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test Charity Commission page crawling")
    parser.add_argument("--count", type=int, default=5, help="Number of funders to test (default: 5)")
    args = parser.parse_args()
    
    asyncio.run(test_charity_commission_crawling(test_count=args.count))
