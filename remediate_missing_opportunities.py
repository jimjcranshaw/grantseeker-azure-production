#!/usr/bin/env python3
"""
Remediation Script for Missing Funding Opportunities
==================================================

This script processes funders that have scraped content (in funder_chunks) 
but missing opportunity records. It uses the enhanced AI analysis pipeline
to generate the missing opportunities with guaranteed coverage.

Usage:
    python remediate_missing_opportunities.py [--batch-size N] [--dry-run] [--verbose]

Author: Grant Seeker RAG Pipeline
Date: December 2025
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

# Import our enhanced functions
from simple_llm_analysis import analyze_with_direct_llm
from azure_production_pipeline import (
    init_db_pool as init_azure_pool,
    is_db_available as is_azure_db_available,
    get_db_connection as get_azure_connection,
    release_db_connection as release_azure_connection
)
from enhanced_storage_functions import (
    store_funding_opportunities_guaranteed,
    update_funder_classification_enhanced
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Azure PostgreSQL Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'sslmode': 'require'
}

# Remediation Configuration
BATCH_SIZE = 50  # Process funders in batches
MAX_RETRIES = 3  # Maximum retries for failed analyses
REMEDIATION_SESSION_PREFIX = "REMEDIATION"
CHUNK_SIZE_LIMIT = 50000  # Maximum characters per chunk to process

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

db_pool = None

def init_db_pool():
    """Initialize database connection pool."""
    init_azure_pool()
    logger.info(f"✅ Database pool initialized via Azure pipeline")

def is_db_available():
    """Check if database connection pool is available."""
    return is_azure_db_available()

def get_db_connection():
    """Get a connection from the pool."""
    return get_azure_connection()

def release_db_connection(conn):
    """Release a connection back to the pool."""
    release_azure_connection(conn)

# =============================================================================
# CORE REMEDIATION FUNCTIONS
# =============================================================================

def find_missing_funders() -> List[Tuple[int, str, str]]:
    """
    Find funders that have scraped content but no opportunities.
    
    Returns:
        List of tuples: (funder_id, funder_name, website)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query to find funders with chunks but no opportunities
        query = """
            SELECT DISTINCT f.id, f.name, f.website
            FROM funders f
            WHERE EXISTS (
                SELECT 1 FROM funder_chunks fc 
                WHERE fc.funder_id = f.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM funding_opportunities fo 
                WHERE fo.funder_id = f.id
            )
            ORDER BY f.id
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        logger.info(f"📊 Found {len(results)} funders with content but missing opportunities")
        
        return [(row[0], row[1], row[2]) for row in results]
        
    except Exception as e:
        logger.error(f"❌ Error finding missing funders: {e}")
        return []
    finally:
        cursor.close()
        release_db_connection(conn)

def get_funder_chunks(funder_id: int) -> List[Dict]:
    """
    Retrieve chunked content for a specific funder.
    
    Args:
        funder_id: The funder ID to retrieve chunks for
        
    Returns:
        List of chunk dictionaries with reconstructed page structure
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT fc.chunk_text, fc.source_url as page_url, fc.chunk_order as chunk_index, f.name
            FROM funder_chunks fc
            JOIN funders f ON f.id = fc.funder_id
            WHERE fc.funder_id = %s
            ORDER BY fc.chunk_order
        """
        
        cursor.execute(query, (funder_id,))
        results = cursor.fetchall()
        
        if not results:
            logger.warning(f"⚠️ No chunks found for funder {funder_id}")
            return []
        
        # Group chunks by page URL and reconstruct page structure
        pages_dict = {}
        funder_name = None
        
        for chunk_text, page_url, chunk_index, name in results:
            if funder_name is None:
                funder_name = name
                
            # Skip if any critical field is None
            if not chunk_text or not page_url or chunk_index is None:
                logger.warning(f"  ⚠️ Skipping invalid chunk (chunk_text={bool(chunk_text)}, page_url={bool(page_url)}, chunk_index={chunk_index})")
                continue
                
            if page_url not in pages_dict:
                pages_dict[page_url] = {
                    'url': page_url,
                    'title': f"Page from {name}",
                    'content': '',
                    'chunks': []
                }
            
            # Add chunk to page content
            if len(chunk_text.strip()) > 50:  # Skip very short chunks
                pages_dict[page_url]['chunks'].append((chunk_index, chunk_text))
        
        # Reconstruct pages with sorted chunks
        pages = []
        for page_url, page_data in pages_dict.items():
            # Sort chunks by index, handling None values
            chunks = sorted(page_data['chunks'], key=lambda x: x[0] if x[0] is not None else 0)
            content = "\n\n---CHUNK SEPARATOR---\n\n".join([chunk[1] for chunk in chunks])
            
            # Limit content size
            if len(content) > CHUNK_SIZE_LIMIT:
                content = content[:CHUNK_SIZE_LIMIT] + "\n\n[Content truncated for processing]"
                logger.info(f"  📄 Truncated content for {page_url} ({len(content)} chars)")
            
            pages.append({
                'url': page_data['url'],
                'title': page_data['title'],
                'content': content
            })
        
        logger.info(f"  📄 Reconstructed {len(pages)} pages for funder {funder_id}")
        return pages, funder_name
        
    except Exception as e:
        logger.error(f"❌ Error retrieving chunks for funder {funder_id}: {e}")
        return [], None
    finally:
        cursor.close()
        release_db_connection(conn)

async def process_single_funder(funder_id: int, funder_name: str, website: str, dry_run: bool = False) -> Dict:
    """
    Process a single funder through the remediation pipeline.
    
    Args:
        funder_id: The funder ID
        funder_name: The funder name
        website: The funder website
        dry_run: If True, don't actually store anything
        
    Returns:
        Dictionary with processing results
    """
    result = {
        'funder_id': funder_id,
        'funder_name': funder_name,
        'website': website,
        'status': 'success',
        'error': None,
        'opportunities_found': 0,
        'session_id': None,
        'analysis_result': None
    }
    
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {funder_name} (ID: {funder_id})")
        logger.info(f"{'='*60}")
        
        # 1. Retrieve chunks and reconstruct pages
        pages, reconstructed_name = get_funder_chunks(funder_id)
        if not pages:
            result['status'] = 'no_content'
            result['error'] = 'No meaningful content found in chunks'
            logger.warning(f"  ⚠️ No meaningful content for {funder_name}")
            return result
        
        # Use reconstructed name if available
        analysis_name = reconstructed_name or funder_name
        
        # 2. Create remediation session - keep connection open for entire processing
        session_conn = None
        session_cursor = None
        if not dry_run:
            session_conn = get_db_connection()
            session_cursor = session_conn.cursor()
            
            try:
                session_cursor.execute("""
                    INSERT INTO scrape_sessions (funder_id, session_date, status, created_at, updated_at)
                    VALUES (%s, CURRENT_TIMESTAMP, 'REMEDIATION', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (funder_id,))
                
                session_id = session_cursor.fetchone()[0]
                result['session_id'] = session_id
                logger.info(f"  ✓ Created remediation session: {session_id}")
                
                # Commit the session creation
                session_conn.commit()
                logger.info(f"  ✓ Session creation committed")
                
            except Exception as e:
                logger.error(f"  ❌ Failed to create session: {e}")
                if session_conn:
                    session_conn.rollback()
                if session_cursor:
                    session_cursor.close()
                if session_conn:
                    release_db_connection(session_conn)
                result['status'] = 'session_error'
                result['error'] = f"Session creation failed: {e}"
                return result
        else:
            result['session_id'] = 'DRY_RUN'
        
        # 3. Analyze content with enhanced AI
        logger.info(f"  🤖 Analyzing content with DeepSeek...")
        start_time = time.time()
        
        try:
            analysis_result = await analyze_with_direct_llm(pages, analysis_name, use_deepseek=True)
            result['analysis_result'] = analysis_result
            elapsed_time = time.time() - start_time
            logger.info(f"  ⏱️ Analysis completed in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"  ❌ AI Analysis failed: {e}")
            result['status'] = 'analysis_failed'
            result['error'] = f"AI analysis failed: {e}"
            return result
        
        # 4. Update classification
        if not dry_run:
            try:
                update_funder_classification_enhanced(funder_id, analysis_result)
                logger.info(f"  ✓ Updated classification")
            except Exception as e:
                logger.warning(f"  ⚠️ Classification update failed: {e}")
        
        # 5. Store opportunities with guaranteed coverage
        if not dry_run:
            try:
                opportunity_count = store_funding_opportunities_guaranteed(
                    funder_id, result['session_id'], analysis_result
                )
                result['opportunities_found'] = opportunity_count
                logger.info(f"  ✅ Stored {opportunity_count} opportunities")
            except Exception as e:
                logger.error(f"  ❌ Opportunity storage failed: {e}")
                result['status'] = 'storage_failed'
                result['error'] = f"Opportunity storage failed: {e}"
                return result
        else:
            opportunities = analysis_result.get('opportunities', [])
            result['opportunities_found'] = len(opportunities)
            logger.info(f"  📋 DRY RUN: Would store {len(opportunities)} opportunities")
        
        logger.info(f"  ✅ Successfully processed {funder_name}")
        
        # Cleanup session connection
        if session_conn:
            session_cursor.close()
            release_db_connection(session_conn)
            
        return result
        
    except Exception as e:
        logger.error(f"  ❌ Unexpected error processing {funder_name}: {e}")
        result['status'] = 'unexpected_error'
        result['error'] = str(e)
        
        # Cleanup session connection on error
        if session_conn:
            session_cursor.close()
            release_db_connection(session_conn)
            
        return result

async def process_funders_batch(funders: List[Tuple[int, str, str]], dry_run: bool = False) -> List[Dict]:
    """
    Process a batch of funders.
    
    Args:
        funders: List of funder tuples (id, name, website)
        dry_run: If True, don't actually store anything
        
    Returns:
        List of processing results
    """
    results = []
    
    for funder_id, funder_name, website in funders:
        result = await process_single_funder(funder_id, funder_name, website, dry_run)
        results.append(result)
        
        # Small delay to prevent overwhelming the API
        await asyncio.sleep(0.5)
    
    return results

def generate_remediation_report(results: List[Dict], total_missing: int, dry_run: bool = False) -> Dict:
    """
    Generate a comprehensive remediation report.
    
    Args:
        results: List of processing results
        total_missing: Total number of missing funders found
        dry_run: Whether this was a dry run
        
    Returns:
        Dictionary containing report data
    """
    # Count statuses
    status_counts = {}
    total_opportunities = 0
    failed_funders = []
    
    for result in results:
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1
        total_opportunities += result['opportunities_found']
        
        if status != 'success':
            failed_funders.append({
                'id': result['funder_id'],
                'name': result['funder_name'],
                'status': status,
                'error': result['error']
            })
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'dry_run': dry_run,
        'total_missing_funders': total_missing,
        'processed_funders': len(results),
        'success_rate': (status_counts.get('success', 0) / len(results) * 100) if results else 0,
        'status_breakdown': status_counts,
        'total_opportunities_created': total_opportunities,
        'average_opportunities_per_funder': (total_opportunities / len(results)) if results else 0,
        'failed_funders': failed_funders,
        'coverage_achieved': status_counts.get('success', 0) / total_missing * 100 if total_missing > 0 else 0
    }
    
    return report

def save_report(report: Dict, filename: str = None):
    """Save the remediation report to a file."""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"remediation_report_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    logger.info(f"📊 Report saved to: {filename}")
    return filename

# =============================================================================
# MAIN REMEDIATION PIPELINE
# =============================================================================

async def run_remediation_pipeline(args):
    """
    Main remediation pipeline execution.
    
    Args:
        args: Command line arguments
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"🚀 REMEDIATION PIPELINE STARTING")
    logger.info(f"{'='*80}")
    
    # Initialize database pool
    init_db_pool()
    
    try:
        # 1. Find missing funders
        logger.info(f"\n🔍 Step 1: Finding funders with content but missing opportunities...")
        missing_funders = find_missing_funders()
        
        if not missing_funders:
            logger.info(f"✅ No missing funders found. All funders have opportunities!")
            return
        
        logger.info(f"📊 Found {len(missing_funders)} funders to remediate")
        
        # 2. Process in batches
        all_results = []
        batch_count = 0
        
        for i in range(0, len(missing_funders), args.batch_size):
            batch = missing_funders[i:i + args.batch_size]
            batch_count += 1
            
            logger.info(f"\n📦 Processing batch {batch_count} ({len(batch)} funders)...")
            logger.info(f"Progress: {i + len(batch)}/{len(missing_funders)} funders")
            
            # Process batch
            batch_start_time = time.time()
            batch_results = await process_funders_batch(batch, args.dry_run)
            batch_elapsed = time.time() - batch_start_time
            
            all_results.extend(batch_results)
            
            logger.info(f"  ⏱️ Batch completed in {batch_elapsed:.2f} seconds")
            
            # Progress update
            success_count = sum(1 for r in batch_results if r['status'] == 'success')
            logger.info(f"  ✅ Batch success: {success_count}/{len(batch)} funders")
            
            # Brief pause between batches
            if i + args.batch_size < len(missing_funders):
                logger.info(f"  ⏸️ Pausing 2 seconds before next batch...")
                await asyncio.sleep(2)
        
        # 3. Generate and save report
        logger.info(f"\n📊 Step 2: Generating remediation report...")
        report = generate_remediation_report(all_results, len(missing_funders), args.dry_run)
        
        # Save report
        report_filename = save_report(report)
        
        # 4. Display summary
        logger.info(f"\n{'='*80}")
        logger.info(f"📋 REMEDIATION SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"Total missing funders: {report['total_missing_funders']}")
        logger.info(f"Processed funders: {report['processed_funders']}")
        logger.info(f"Success rate: {report['success_rate']:.1f}%")
        logger.info(f"Total opportunities created: {report['total_opportunities_created']}")
        logger.info(f"Average opportunities per funder: {report['average_opportunities_per_funder']:.1f}")
        logger.info(f"Coverage achieved: {report['coverage_achieved']:.1f}%")
        
        if report['failed_funders']:
            logger.info(f"\n❌ Failed funders ({len(report['failed_funders'])}):")
            for failed in report['failed_funders'][:10]:  # Show first 10
                logger.info(f"  - {failed['name']} (ID: {failed['id']}): {failed['status']}")
            if len(report['failed_funders']) > 10:
                logger.info(f"  ... and {len(report['failed_funders']) - 10} more")
        
        logger.info(f"\n📄 Full report saved to: {report_filename}")
        
        if report['coverage_achieved'] >= 95.0:
            logger.info(f"🎉 REMEDIATION SUCCESSFUL! High coverage achieved.")
        elif report['coverage_achieved'] >= 80.0:
            logger.info(f"⚠️ REMEDIATION PARTIALLY SUCCESSFUL. Some failures occurred.")
        else:
            logger.info(f"❌ REMEDIATION FAILED. Low coverage achieved.")
        
    except KeyboardInterrupt:
        logger.info(f"\n⚠️ Remediation interrupted by user")
    except Exception as e:
        logger.error(f"❌ Remediation pipeline failed: {e}")
        raise
    finally:
        # Cleanup database pool
        if db_pool:
            db_pool.closeall()
            logger.info(f"🧹 Database pool closed")

# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remediation script for missing funding opportunities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python remediate_missing_opportunities.py
    python remediate_missing_opportunities.py --batch-size 25 --verbose
    python remediate_missing_opportunities.py --dry-run --batch-size 10
        """
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=BATCH_SIZE,
        help=f'Number of funders to process in each batch (default: {BATCH_SIZE})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in dry-run mode (analyze but don\'t store results)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    global logger
    logger = logging.getLogger(__name__)
    
    # Display configuration
    logger.info(f"🔧 REMEDIATION CONFIGURATION")
    logger.info(f"  Batch size: {args.batch_size}")
    logger.info(f"  Dry run: {args.dry_run}")
    logger.info(f"  Verbose: {args.verbose}")
    
    # Run remediation
    asyncio.run(run_remediation_pipeline(args))

if __name__ == "__main__":
    main()