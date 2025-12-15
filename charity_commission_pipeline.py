#!/usr/bin/env python3
"""
CHARITY COMMISSION PIPELINE - Specialized for Charity Commission Pages
========================================================================

This pipeline is specifically designed for processing Charity Commission profile pages.
Key differences from regular website pipeline:
- ONLY processes foundations with Charity Commission URLs
- Documents are CRITICAL - longer timeouts and retry logic
- Extended Docling timeout (15 minutes) for large PDFs with OCR
- Document processing is mandatory (foundations fail if documents can't be processed)
- Focuses on extracting annual accounts, articles of association, etc.

Author: Grant Seeker RAG Pipeline
Date: December 2025
"""

import asyncio
import argparse
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import SimpleConnectionPool
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import hashlib
import json
import os
import re
import csv
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
import time
from openai import OpenAI
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig, BrowserConfig
from langchain_core.documents import Document
from simple_llm_analysis import analyze_with_direct_llm
import logging
from concurrent.futures import ThreadPoolExecutor

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

# Azure PostgreSQL Configuration (load from environment variables)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'your-server.postgres.database.azure.com'),
    'user': os.getenv('DB_USER', 'your-admin-user'),
    'password': os.getenv('DB_PASSWORD', 'your-password'),
    'database': os.getenv('DB_NAME', 'postgres'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'sslmode': 'require'
}

# API Keys (load from environment variables)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-key-here')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'your-deepseek-key-here')

# OCR Configuration - Multiple providers supported
# Option 1: Azure Document Intelligence (BEST: $18 for 12k docs, uses Azure credits/subscription)
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', '')
AZURE_DOCUMENT_INTELLIGENCE_KEY = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_KEY', '')
# Option 2: Google Cloud Document AI (cheapest: $18 for 12k docs, but requires GCP setup)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', '')
GCP_PROCESSOR_LOCATION = os.getenv('GCP_PROCESSOR_LOCATION', 'us')  # 'us' or 'eu'
GCP_PROCESSOR_ID = os.getenv('GCP_PROCESSOR_ID', '')
# Option 3: LLMOCR (Easy setup: $53.88 for 12k docs)
LLMOCR_API_KEY = os.getenv('LLMOCR_API_KEY', '')
# Option 4: DeepSeek OCR via hosted service (SiliconFlow, Clarifai, etc.)
DEEPSEEK_OCR_API_KEY = os.getenv('DEEPSEEK_OCR_API_KEY', os.getenv('DS_OCR_API_KEY', ''))
DEEPSEEK_OCR_BASE_URL = os.getenv('DEEPSEEK_OCR_BASE_URL', os.getenv('DS_OCR_BASE_URL', ''))
# Option 5: Self-hosted vLLM (requires GPU)
# For self-hosted vLLM, set base_url to http://localhost:8000/v1 and use dummy API key

# Performance Configuration
MAX_CONCURRENT_FOUNDATIONS = 10  # Reduced to 10 to prevent DeepSeek timeouts
MAX_CONCURRENT_CRAWLS = 10  # Crawl 10 pages per foundation in parallel
DB_POOL_SIZE = 20  # Database connection pool size (kept high for safety)
CRAWL_MAX_DEPTH = 3  # Maximum crawl depth
CRAWL_MAX_PAGES = 50  # Maximum pages per foundation
# DeepSeek OCR Configuration (replacing Docling)
MAX_CONCURRENT_DEEPSEEK_OCR = 2  # Process 2 documents concurrently
DEEPSEEK_OCR_TIMEOUT = 60  # 60 seconds timeout per document (much faster than Docling)
DEEPSEEK_OCR_RETRIES = 2  # Retry failed documents up to 2 times
DEEPSEEK_OCR_REQUIRED = True  # Documents are REQUIRED for Charity Commission foundations
DEEPSEEK_OCR_RATE_LIMIT_DELAY = 0.6  # 100 requests/minute = 0.6 seconds between requests
# Legacy Docling config (kept for backward compatibility, but not used)
MAX_CONCURRENT_DOCLING = 2
DOCLING_TIMEOUT = 900
DOCLING_RETRIES = 2
DOCLING_REQUIRED = True

# Change Detection Configuration
CHANGE_DETECTION_ENABLED = True  # Enable HTTP HEAD change detection
SIMILARITY_THRESHOLD = 0.95  # 95% similarity = no change

# Test Configuration
TEST_MODE = False  # Set to False for production
TEST_FOUNDATIONS_COUNT = 1  # Number of foundations to test with
NO_DB_MODE = False  # Set to True to skip database operations entirely

# =============================================================================
# DATABASE CONNECTION POOL
# =============================================================================

db_pool = None

def init_db_pool():
    """Initialize database connection pool."""
    global db_pool
    db_pool = SimpleConnectionPool(
        1,  # Min connections
        DB_POOL_SIZE,  # Max connections
        **DB_CONFIG
    )
    logger.info(f"✅ Database pool initialized ({DB_POOL_SIZE} connections)")

def is_db_available():
    """Check if database connection pool is available."""
    logger.info("Checking database availability...")
    available = db_pool is not None
    logger.info(f"Database available: {available}")
    return available

def get_db_connection():
    """Get a connection from the pool."""
    logger.info("Getting database connection...")
    conn = db_pool.getconn()
    logger.info("Database connection retrieved successfully.")
    return conn

def release_db_connection(conn):
    """Release a connection back to the pool."""
    db_pool.putconn(conn)

# =============================================================================
# HTTP HEAD CHANGE DETECTION
# =============================================================================

def check_url_changed(url: str, stored_etag: Optional[str], stored_last_modified: Optional[str], stored_content_hash: Optional[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Check if a URL has changed using HTTP HEAD request and Content Hash fallback.
    
    Args:
        url: The URL to check
        stored_etag: Previously stored ETag
        stored_last_modified: Previously stored Last-Modified header
        stored_content_hash: Previously stored hash of homepage content
        
    Returns:
        Tuple of (changed, new_etag, new_last_modified, new_content_hash)
    """
    try:
        # 1. Try HEAD request first (fastest)
        response = requests.head(url, timeout=10, allow_redirects=True)
        new_etag = response.headers.get('ETag')
        new_last_modified = response.headers.get('Last-Modified')
        new_content_hash = None
        
        # 1a. If header data exists and matches, return False (unchanged) early
        if new_etag and stored_etag and new_etag == stored_etag:
            logger.info(f"  ✓ No change detected (ETag match) for {url}")
            return False, new_etag, new_last_modified, stored_content_hash
            
        if new_last_modified and stored_last_modified and new_last_modified == stored_last_modified:
            logger.info(f"  ✓ No change detected (Last-Modified match) for {url}")
            return False, new_etag, new_last_modified, stored_content_hash

        # 2. Fallback to Content Hash check if headers are missing or inconclusive
        logger.info(f"  ⚠️ Headers inconclusive/missing for {url}. Checking content hash...")
        try:
            # Fetch content body (GET request)
            get_response = requests.get(url, timeout=20, allow_redirects=True)
            content = get_response.text
            
            # Compute Hash (MD5 is fast and sufficient for change detection)
            new_content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Compare with stored hash
            if stored_content_hash and new_content_hash == stored_content_hash:
                logger.info(f"  ✓ No change detected (Content Hash match) for {url}")
                # We return the new headers (if any) so we can update them even if content is same
                return False, new_etag, new_last_modified, new_content_hash
            
            if stored_content_hash is None:
                 logger.info(f"  📍 First content check for {url}")
            else:
                 logger.info(f"  🔄 Content hash changed for {url}")
                 
            return True, new_etag, new_last_modified, new_content_hash
            
        except Exception as e:
            logger.warning(f"  ⚠️ Content fetch failed for {url}: {e}")
            return True, new_etag, new_last_modified, None

    except Exception as e:
        logger.warning(f"  ⚠️ HEAD request failed for {url}: {str(e)}")
        # On error, assume changed to be safe
        return True, None, None, None

def update_change_detection_headers(funder_id: int, etag: Optional[str], last_modified: Optional[str], content_hash: Optional[str]):
    """Update ETag, Last-Modified, and Content Hash in database."""
    if not is_db_available():
        logger.info(f"  📝 Skipping header update (no DB mode)")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE funders
            SET etag = %s, last_modified = %s, content_hash = %s, last_checked = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etag, last_modified, content_hash, funder_id))
        conn.commit()
        cursor.close()
    finally:
        release_db_connection(conn)

# =============================================================================
# CRAWLING & FILTERING
# =============================================================================

def is_relevant_path(path: str) -> bool:
    """
    Checks if a URL path is likely relevant to a grantseeker.
    Excludes common irrelevant pages like privacy, terms, settings, etc.
    """
    irrelevant_keywords = [
        "privacy", "terms", "conditions", "legal", "settings", "login",
        "register", "signup", "signin", "account", "cart", "checkout",
        "jobs", "careers", "press", "news", "blog", "events", "contact",
        "about", "team", "board", "donate", "giving", "support", "shop",
        "faq", "help", "sitemap", "404", "search", "admin", "wp-admin",
        "assets", "css", "js", "img", "image", "media", "file", "download"
    ]
    # Keywords that strongly suggest relevance
    relevant_keywords = [
        "grant", "apply", "funding", "guideline", "eligibility", "program",
        "initiative", "focus-area", "how-to-apply", "process", "criteria",
        "request-for-proposals", "rfp", "opportunities"
    ]

    path_lower = path.lower()

    # 1. Check for strong relevance keywords
    if any(kw in path_lower for kw in relevant_keywords):
        return True

    # 2. Check for strong irrelevance keywords
    if any(kw in path_lower for kw in irrelevant_keywords):
        return False

    # 3. Default to relevant if not strongly excluded
    return True

def filter_url(url: str, base_domain: str) -> bool:
    """
    Applies all filtering rules to a single URL.
    """
    try:
        parsed_url = urlparse(url)
        # 1. Exclude external links
        if parsed_url.netloc != base_domain:
            return False

        # 2. Exclude non-http/https schemes
        if parsed_url.scheme not in ["http", "https"]:
            return False

        # 3. Exclude file extensions (e.g., pdf, doc, jpg)
        # We capture documents separately for Docling
        if re.search(r"\.(jpg|jpeg|png|gif|zip|rar)$", parsed_url.path.lower()):
            return False

        # 4. Apply path relevance check
        if not is_relevant_path(parsed_url.path):
            return False

        return True
    except Exception:
        return False

def get_url_depth(url: str, base_url: str) -> int:
    """
    Calculates the path depth of a URL relative to the base URL.
    """
    try:
        base_path = urlparse(base_url).path.strip("/")
        url_path = urlparse(url).path.strip("/")
        
        # Remove the base path from the URL path if it's a sub-path
        if url_path.startswith(base_path) and base_path:
            url_path = url_path[len(base_path):].strip("/")

        # Count segments
        segments = [s for s in url_path.split("/") if s]
        return len(segments)
    except Exception:
        return 0

async def extract_charity_commission_documents(crawler: AsyncWebCrawler, base_url: str, charity_number: str, main_result=None) -> Tuple[List[str], Optional[str]]:
    """
    Extract 3 critical documents from Charity Commission pages:
    1. Last 2 annual accounts (most recent 2)
    2. Articles of association (governing document)
    
    Also crawls and scrapes all text on CC profiles (free, no OCR needed).
    
    Args:
        crawler: The AsyncWebCrawler instance
        base_url: The main Charity Commission profile URL
        charity_number: The charity registration number
        main_result: Optional CrawlResult from initial crawl (to avoid re-crawling)
    
    Returns:
        Tuple of (document_urls, profile_text):
        - document_urls: List of up to 3 document URLs: [last_annual_account, second_last_annual_account, articles_of_association]
        - profile_text: Combined text from all CC profile pages (main page + document pages)
    """
    import html
    documents_to_process = []
    base_domain = urlparse(base_url).netloc
    
    # Track documents separately by type
    annual_accounts = []
    articles_of_association = []
    
    # Collect profile text from all CC pages (free, no OCR needed)
    profile_text_parts = []
    
    # Use networkidle + wait_for to ensure dynamically loaded document links are captured
    # Based on crawl4ai docs: wait_for can wait for specific CSS selectors
    # Charity Commission loads document links dynamically via AJAX
    crawler_config = CrawlerRunConfig(
        wait_until="networkidle",  # Wait for network to be idle (AJAX requests complete)
        page_timeout=60000,  # 60 seconds timeout
        cache_mode="bypass",
        delay_before_return_html=5.0,  # Wait 5 seconds after page load
        # Wait for table to appear (document links are in tables)
        wait_for="table"  # Wait for table elements to appear
    )
    
    # Step 1: Crawl main profile page to discover links to document pages
    # IMPORTANT: Use links from main page (they may have different charity numbers due to redirects)
    # Reuse main_result if provided to avoid re-crawling
    doc_page_urls = []
    try:
        if main_result is None:
            main_result = await crawler.arun(url=base_url, config=crawler_config)
        
        # Extract text from main profile page
        if main_result.success and main_result.markdown:
            profile_text_parts.append(f"=== Main Profile Page ===\n{main_result.markdown[:100000]}\n\n")
            logger.debug(f"    Extracted {len(main_result.markdown)} chars from main profile page")
        
        if main_result.success and main_result.links:
            internal_links = main_result.links.get('internal', [])
            # Find links to accounts and governing document pages (don't filter by charity_number - 
            # the links may have different numbers due to how CC handles redirects)
            doc_page_links = [link.get('href', '') for link in internal_links if 
                            'accounts-and-annual-returns' in link.get('href', '') or
                            'governing-document' in link.get('href', '')]
            doc_page_urls = [urljoin(base_url, link) for link in doc_page_links if link]
            logger.debug(f"    Found {len(doc_page_urls)} document page links from main page")
    except Exception as e:
        logger.warning(f"    ⚠️ Could not get links from main page: {e}")
    
    # Fallback: construct URLs directly if we didn't find links
    if not doc_page_urls:
        doc_page_urls = [
            f"https://{base_domain}/en/charity-search/-/charity-details/{charity_number}/accounts-and-annual-returns?_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_organisationNumber={charity_number}",
            f"https://{base_domain}/en/charity-search/-/charity-details/{charity_number}/governing-document?_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_organisationNumber={charity_number}",
        ]
    
    # Step 2: Follow each document page link and extract download URLs + page text
    for doc_page_url in doc_page_urls:
        try:
            result = await crawler.arun(url=doc_page_url, config=crawler_config)
            page_docs = []  # Documents found on this specific page
            
            # Extract text from document page (summary text, not documents themselves)
            if result.success and result.markdown:
                page_name = doc_page_url.split('/')[-1].split('?')[0]
                profile_text_parts.append(f"=== {page_name.replace('-', ' ').title()} Page ===\n{result.markdown[:50000]}\n\n")
                logger.debug(f"    Extracted {len(result.markdown)} chars from {page_name} page")
            
            # Use BOTH approaches: regex on HTML AND crawl4ai's link discovery
            # The working solution used regex, but crawl4ai may also find JS-loaded links
            if result.success and result.html:
                html_content = result.html
                import re
                
                # Look for download links - Charity Commission uses specific patterns
                # Pattern 1: Links with p_p_resource_id=/accounts-resource (PDF downloads)
                # Pattern 2: Links with p_p_resource_id=/governing-document-resource
                # Pattern 3: Direct PDF links
                download_patterns = [
                    r'href=["\']([^"\']*p_p_resource_id=[^"\']*accounts-resource[^"\']*)["\']',
                    r'href=["\']([^"\']*p_p_resource_id=[^"\']*governing-document-resource[^"\']*)["\']',
                    r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                ]
                
                for pattern in download_patterns:
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    for match in matches:
                        # Decode HTML entities (&amp; -> &)
                        decoded_url = html.unescape(match)
                        # Make absolute URL
                        full_url = urljoin(doc_page_url, decoded_url)
                        if full_url not in page_docs:
                            page_docs.append(full_url)
                            logger.debug(f"    ✓ Found document link via regex: {full_url[:120]}")
            
            # Also check crawl4ai's discovered links (may find JS-loaded links)
            if result.success and result.links:
                internal_links = result.links.get('internal', [])
                external_links = result.links.get('external', [])
                all_links = internal_links + external_links
                
                for link_obj in all_links:
                    href = link_obj.get('href', '') or ''
                    text = (link_obj.get('text', '') or '').lower().strip()
                    
                    # Check for document patterns (same as regular crawl uses)
                    if ('p_p_resource_id' in href.lower() or 
                        '.pdf' in href.lower() or
                        ('download' in href.lower() and 'p_p_resource_id' in href.lower())):
                        full_url = urljoin(doc_page_url, href)
                        if full_url not in page_docs:
                            page_docs.append(full_url)
                            logger.debug(f"    ✓ Found document link via crawl4ai: {full_url[:120]}")
            
            # Separate documents by page type
            page_name = doc_page_url.split('/')[-1].split('?')[0]
            if 'accounts-and-annual-returns' in doc_page_url.lower():
                # These are annual accounts - take the first two (most recent 2)
                if page_docs:
                    annual_accounts.extend(page_docs)
                    logger.info(f"    ✓ Found {len(page_docs)} annual account(s) on {page_name}")
            elif 'governing-document' in doc_page_url.lower():
                # These are articles of association
                if page_docs:
                    articles_of_association.extend(page_docs)
                    logger.info(f"    ✓ Found {len(page_docs)} governing document(s) on {page_name}")
        except Exception as e:
            logger.warning(f"    ⚠️ Failed to extract documents from {doc_page_url}: {str(e)}")
    
    # Return only 3 documents: first 2 annual accounts + articles of association
    result_docs = []
    
    # Take first two annual accounts (most recent are usually first)
    if annual_accounts:
        # Take up to 2 annual accounts (most recent first)
        selected_accounts = annual_accounts[:2]
        result_docs.extend(selected_accounts)
        logger.info(f"    📄 Selected {len(selected_accounts)} annual account(s) (most recent)")
    
    # Take first articles of association
    if articles_of_association:
        result_docs.append(articles_of_association[0])
        logger.info(f"    📄 Selected articles of association")
    
    if len(result_docs) < 3:
        logger.warning(f"    ⚠️ Only found {len(result_docs)}/3 critical documents")
    
    # Combine all profile text
    profile_text = "\n".join(profile_text_parts) if profile_text_parts else None
    if profile_text:
        logger.info(f"    📝 Extracted {len(profile_text):,} chars of profile text (free, no OCR)")
    
    return result_docs, profile_text

async def crawl_foundation(url: str, name: str) -> List[Dict]:
    """
    Crawl a foundation website using crawl4ai with sitemap support and intelligent filtering.
    Special handling for Charity Commission pages to extract documents.
    """
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    # Configure crawler - use networkidle for Charity Commission pages to catch AJAX-loaded content
    # Don't use wait_for here as it causes timeouts on pages without tables
    crawler_config = CrawlerRunConfig(
        wait_until="networkidle",  # Wait for network to be idle (AJAX requests complete)
        page_timeout=60000,  # 60 seconds timeout
        cache_mode="bypass",
        delay_before_return_html=5.0  # Wait 5 seconds after page load for JS to execute
    )
    
    pages = []
    base_domain = urlparse(url).netloc
    is_charity_commission = 'charitycommission.gov.uk' in url.lower()
    
    # Track documents for Docling processing later
    documents_to_process = []
    
    logger.info(f"  🔍 Starting comprehensive crawl for: {url}")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            # 1. Initial crawl to get sitemap and base pages
            result = await crawler.arun(
                url=url,
                config=crawler_config
            )
            
            # Extract charity number if this is a Charity Commission page
            charity_number = None
            if is_charity_commission:
                import re
                match = re.search(r'regId=(\d+)', url)
                if match:
                    charity_number = match.group(1)
                    logger.info(f"    📋 Detected Charity Commission page for charity #{charity_number}")
                    # Extract documents from specific Charity Commission document pages
                    # Pass the initial crawl result to avoid re-crawling the main page
                    cc_docs, cc_profile_text = await extract_charity_commission_documents(crawler, url, charity_number, main_result=result)
                    documents_to_process.extend(cc_docs)
                    logger.info(f"    📄 Found {len(cc_docs)} Charity Commission documents")
                    
                    # Add CC profile text as a page (free, no OCR needed)
                    if cc_profile_text:
                        pages.append({
                            'url': url,
                            'title': f"Charity Commission Profile: {name}",
                            'content': cc_profile_text[:50000],  # Limit to 50k chars
                            'depth': 0,
                            'type': 'charity_commission_profile'
                        })
                        logger.info(f"    📝 Added CC profile text ({len(cc_profile_text):,} chars)")
            
            # Collect URLs from sitemap and crawl
            all_discovered_urls = set()
            if result.success:
                # Add the main page itself
                if result.markdown:
                     pages.append({
                        'url': url,
                        'title': result.metadata.get('title', ''),
                        'content': result.markdown[:50000],
                        'depth': 0
                    })
                
                # Get internal links
                internal_links = [link['href'] for link in result.links.get('internal', []) if link.get('href')]
                all_discovered_urls.update(internal_links)
                
                logger.info(f"    ✓ Initial crawl found {len(all_discovered_urls)} potential URLs")
            
            # 2. Filter and prioritize URLs
            urls_to_visit = []
            for discovered_url in all_discovered_urls:
                # Normalize
                normalized_url = urljoin(discovered_url, urlparse(discovered_url).path)
                
                # SPECIAL HANDLING: Always visit Charity Commission document pages
                # These pages contain document download links that need to be discovered
                is_cc_doc_page = (
                    is_charity_commission and 
                    ('accounts-and-annual-returns' in normalized_url.lower() or 
                     'governing-document' in normalized_url.lower())
                )
                
                if is_cc_doc_page:
                    depth = get_url_depth(normalized_url, url)
                    if depth <= CRAWL_MAX_DEPTH:
                        if normalized_url != url:  # Avoid duplicates
                            urls_to_visit.append((normalized_url, depth))
                            logger.debug(f"    ✓ Added CC document page to visit: {normalized_url[:100]}")
                    continue
                
                # Check for documents (PDF/DOCX) - including Charity Commission document links
                is_document = (
                    re.search(r"\.(pdf|doc|docx)$", normalized_url.lower()) or
                    ('download' in normalized_url.lower() and 'p_p_resource_id' in normalized_url.lower())
                )
                if is_document:
                    if is_relevant_path(urlparse(normalized_url).path) or 'charitycommission.gov.uk' in normalized_url:
                        if normalized_url not in documents_to_process:
                            documents_to_process.append(normalized_url)
                    continue

                # Filter regular pages
                if filter_url(normalized_url, base_domain):
                    depth = get_url_depth(normalized_url, url)
                    if depth <= CRAWL_MAX_DEPTH:
                         if normalized_url != url: # Avoid duplicates
                            urls_to_visit.append((normalized_url, depth))
            
            # Sort by depth (bfs)
            urls_to_visit.sort(key=lambda x: x[1])
            
            # Limit total pages
            urls_to_visit = urls_to_visit[:CRAWL_MAX_PAGES]
            
            logger.info(f"    ✓ Visiting {len(urls_to_visit)} relevant pages")
            
            # 3. Visit relevant pages
            for current_url, depth in urls_to_visit:
                 # Check if we have enough pages
                if len(pages) >= CRAWL_MAX_PAGES:
                    break

                try:
                    page_result = await crawler.arun(
                        url=current_url,
                        config=crawler_config
                    )
                    
                    if page_result.success and page_result.markdown:
                        pages.append({
                            'url': current_url,
                            'title': page_result.metadata.get('title', ''),
                            'content': page_result.markdown[:50000],
                            'depth': depth
                        })
                        logger.info(f"    ✓ Crawled: {current_url} (depth {depth})")
                except Exception as e:
                    logger.warning(f"    ⚠️ Failed to crawl {current_url}: {str(e)}")
            
            # 4. Process found documents with DeepSeek OCR (in parallel)
            if documents_to_process:
                import time as time_module
                doc_start_time = time_module.time()
                logger.info(f"    📄 Found {len(documents_to_process)} documents for OCR processing")
                
                # Extract cookies from browser session for authenticated downloads
                session_cookies = {}
                try:
                    # Access playwright browser through crawl4ai
                    if hasattr(crawler, '_browser') and crawler._browser:
                        browser = crawler._browser
                        if hasattr(browser, 'contexts') and browser.contexts:
                            context = browser.contexts[0]
                            cookies = await context.cookies()
                            session_cookies = {cookie['name']: cookie['value'] for cookie in cookies}
                            logger.debug(f"    Extracted {len(session_cookies)} cookies from browser session")
                except Exception as e:
                    logger.debug(f"    Could not extract browser cookies: {e}")
                
                # Process documents in parallel using ThreadPoolExecutor
                # Access global config variables for DeepSeek OCR
                max_concurrent = globals().get('MAX_CONCURRENT_DEEPSEEK_OCR', 2)
                ocr_timeout = globals().get('DEEPSEEK_OCR_TIMEOUT', 60)
                
                async def process_single_document(doc_url: str, idx: int, total: int, executor: ThreadPoolExecutor):
                    """Process a single document using DeepSeek OCR with retries (CRITICAL for CC)."""
                    doc_start = time_module.time()
                    max_retries = globals().get('DEEPSEEK_OCR_RETRIES', 2)
                    
                    for attempt in range(max_retries + 1):
                        try:
                            if attempt > 0:
                                logger.info(f"    🔄 [{idx}/{total}] Retry {attempt}/{max_retries} for: {doc_url[:80]}...")
                            else:
                                logger.info(f"    📄 [{idx}/{total}] Starting OCR processing: {doc_url[:80]}...")
                            
                            # Run OCR processing in thread pool executor (routes to Azure/GCP/LLMOCR/DeepSeek based on config)
                            loop = asyncio.get_event_loop()
                            doc_content = await asyncio.wait_for(
                                loop.run_in_executor(
                                    executor,
                                    process_document_with_ocr_sync,
                                    doc_url,
                                    name,
                                    session_cookies if session_cookies else None
                                ),
                                timeout=ocr_timeout
                            )
                            doc_elapsed = time_module.time() - doc_start
                            if doc_content:
                                content_len = len(doc_content.get('content', ''))
                                logger.info(f"    ✓ [{idx}/{total}] Successfully processed in {doc_elapsed:.1f}s ({content_len:,} chars)")
                                return doc_content
                            else:
                                logger.warning(f"    ⚠️ [{idx}/{total}] Processing returned no content after {doc_elapsed:.1f}s")
                                if attempt < max_retries:
                                    await asyncio.sleep(5)  # Wait before retry
                                    continue
                                return None
                        except asyncio.TimeoutError:
                            doc_elapsed = time_module.time() - doc_start
                            logger.warning(f"    ⚠️ [{idx}/{total}] Timed out after {doc_elapsed:.1f}s (attempt {attempt+1}/{max_retries+1}): {doc_url[:80]}...")
                            if attempt < max_retries:
                                logger.info(f"    🔄 Retrying document in 5 seconds...")
                                await asyncio.sleep(5)
                                continue
                            # For Charity Commission, we should log this as a critical failure
                            logger.error(f"    ❌ [{idx}/{total}] CRITICAL: Document failed after {max_retries+1} attempts: {doc_url[:80]}...")
                            return None
                        except Exception as e:
                            doc_elapsed = time_module.time() - doc_start
                            logger.warning(f"    ⚠️ [{idx}/{total}] Failed after {doc_elapsed:.1f}s (attempt {attempt+1}/{max_retries+1}): {e}")
                            if attempt < max_retries:
                                logger.info(f"    🔄 Retrying document in 5 seconds...")
                                await asyncio.sleep(5)
                                continue
                            logger.error(f"    ❌ [{idx}/{total}] CRITICAL: Document failed after {max_retries+1} attempts: {doc_url[:80]}...")
                            return None
                    
                    return None
                
                # Process all documents (up to 3 per foundation: 2 annual accounts + articles of association)
                doc_urls = documents_to_process
                
                # Create thread pool executor with controlled concurrency
                with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                    tasks = [
                        process_single_document(doc_url, idx + 1, len(doc_urls), executor)
                        for idx, doc_url in enumerate(doc_urls)
                    ]
                    
                    # Wait for all document processing tasks to complete
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Collect successful results
                processed_docs = [doc for doc in results if doc is not None and not isinstance(doc, Exception)]
                failed_count = len(documents_to_process[:10]) - len(processed_docs)
                
                # For Charity Commission, documents are CRITICAL - warn if many failed
                if failed_count > 0:
                    logger.warning(f"    ⚠️ {failed_count} document(s) failed to process (CRITICAL for CC foundations)")
                    if failed_count == len(doc_urls):
                        logger.error(f"    ❌ ALL documents failed! Foundation may have incomplete data.")
                
                pages.extend(processed_docs)
                processed_count = len(processed_docs)
                doc_total_time = time_module.time() - doc_start_time
                
                if processed_count > 0:
                    avg_time = doc_total_time / processed_count if processed_count > 0 else 0
                    logger.info(f"    ✅ Processed {processed_count}/{len(doc_urls)} documents in {doc_total_time:.1f}s (avg: {avg_time:.1f}s/doc, {max_concurrent} workers)")
                else:
                    logger.warning(f"    ⚠️ No documents were successfully processed after {doc_total_time:.1f}s")

        except Exception as e:
            logger.error(f"  ❌ Crawl failed for {url}: {str(e)}")
            
    logger.info(f"  📊 Crawled {len(pages)} pages + documents from {url}")
    return pages

async def process_document_content_with_docling(content: bytes, url: str, foundation_name: str) -> Optional[Dict]:
    """
    Process document content (already downloaded) with Docling.
    """
    try:
        from docling.document_converter import DocumentConverter
        
        logger.info(f"    📄 Processing document content with Docling: {url[:100]}...")
        
        # Save content to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf" # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            tmp_file.write(content)
        
        try:
            # Convert with Docling
            converter = DocumentConverter()
            result = converter.convert(temp_path)
            
            # Extract content (Markdown format is good for LLMs)
            markdown_content = result.document.export_to_markdown()
            
            # Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000], # Limit content
                'depth': 0, # Treat docs as depth 0 importance
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ Docling not installed. Please install 'docling' to process documents.")
        return None
    except Exception as e:
        logger.error(f"    ❌ Docling processing failed for {url}: {str(e)}")
        return None

def process_document_with_docling_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Synchronous version of document processing for use with executor.
    Downloads and processes a document (PDF/DOCX) using Docling.
    """
    try:
        from docling.document_converter import DocumentConverter
        
        logger.info(f"    📄 Processing document with Docling: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf" # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests - use session cookies for Charity Commission
            # Use more complete headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Accept-Language': 'en-GB,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://register-of-charities.charitycommission.gov.uk/',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin'
            }
            
            # Try download with cookies first
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    # If 403, try without cookies (some PDFs might be public)
                    logger.warning(f"    ⚠️ Got 403 with cookies, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            # Check if we got a PDF by checking Content-Type header
            content_type = response.headers.get('Content-Type', '').lower()
            if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
                logger.warning(f"    ⚠️ Response Content-Type is '{content_type}', may not be a PDF")
                # Still try to process it - could be PDF with wrong content-type
            
            # Download the file content
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            # Verify we got content
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Convert with Docling
            converter = DocumentConverter()
            result = converter.convert(temp_path)
            
            # 3. Extract content (Markdown format is good for LLMs)
            markdown_content = result.document.export_to_markdown()
            
            # 4. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000], # Limit content
                'depth': 0, # Treat docs as depth 0 importance
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ Docling not installed. Please install 'docling' to process documents.")
        return None
    except Exception as e:
        logger.error(f"    ❌ Docling processing failed for {url}: {str(e)}")
        return None

async def process_document_with_docling(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Downloads and processes a document (PDF/DOCX) using Docling.
    Uses session cookies if provided (for Charity Commission downloads).
    """
    try:
        from docling.document_converter import DocumentConverter
        
        logger.info(f"    📄 Processing document with Docling: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf" # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests - use session cookies for Charity Commission
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, stream=True, timeout=30, headers=headers, cookies=session_cookies)
            response.raise_for_status()
            
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
                
        try:
            # 2. Convert with Docling
            converter = DocumentConverter()
            result = converter.convert(temp_path)
            
            # 3. Extract content (Markdown format is good for LLMs)
            markdown_content = result.document.export_to_markdown()
            
            # 4. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000], # Limit content
                'depth': 0, # Treat docs as depth 0 importance
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ Docling not installed. Please install 'docling' to process documents.")
        return None
    except Exception as e:
        logger.error(f"    ❌ Docling processing failed for {url}: {str(e)}")
        return None

# =============================================================================
# OCR PROCESSING (Replacing Docling) - Supports Multiple Providers
# =============================================================================

def process_document_with_llmocr_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Process document using LLMOCR API (budget-friendly: $0.00449/doc, under $60 budget).
    """
    try:
        import base64
        
        logger.info(f"    📄 Processing document with LLMOCR: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf"  # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
            }
            
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"    ⚠️ Got 403, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Read file and convert to base64
            with open(temp_path, 'rb') as f:
                file_content = f.read()
            
            file_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # 3. Determine endpoint (try with API key as query parameter)
            if suffix.lower() == '.pdf':
                endpoint = f'https://llmocr.com/api/pdf-to-markdown?key={LLMOCR_API_KEY}'
                mime_type = 'application/pdf'
            else:
                endpoint = f'https://llmocr.com/api/image-to-markdown?key={LLMOCR_API_KEY}'
                mime_type = 'image/png'
            
            # 4. Call LLMOCR API
            # Try both methods: query parameter (as per docs) and Bearer token (fallback)
            api_headers = {
                'Content-Type': 'application/json',
            }
            
            # LLMOCR API expects document with 'type' and 'document_url' fields
            # Since we have the file locally, we need to use base64 data URL format
            # Format: data:[<mediatype>][;base64],<data>
            data_url = f'data:{mime_type};base64,{file_base64}'
            
            payload = {
                'document': {
                    'type': 'document_url',
                    'document_url': data_url
                }
            }
            
            # Try with API key in query parameter
            api_response = requests.post(endpoint, headers=api_headers, json=payload, timeout=120)  # Longer timeout for large PDFs
            
            # If that fails, try Bearer token method
            if api_response.status_code == 401:
                logger.debug("    Trying Bearer token authentication method...")
                endpoint_no_key = endpoint.split('?')[0]  # Remove query param
                api_headers['Authorization'] = f'Bearer {LLMOCR_API_KEY}'
                api_response = requests.post(endpoint_no_key, headers=api_headers, json=payload, timeout=120)
            
            # Log error details for debugging
            if api_response.status_code != 200:
                try:
                    error_detail = api_response.json()
                    logger.warning(f"    LLMOCR API error ({api_response.status_code}): {error_detail}")
                except:
                    logger.warning(f"    LLMOCR API error ({api_response.status_code}): {api_response.text[:500]}")
            
            api_response.raise_for_status()
            
            result = api_response.json()
            markdown_content = result.get('markdown', result.get('text', result.get('content', '')))
            
            if not markdown_content:
                logger.warning(f"    ⚠️ LLMOCR returned empty content for {url}")
                return None
            
            # 5. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000],  # Limit content to 50k chars
                'depth': 0,
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        error_msg = str(e)
        # Check if it's an API key exhaustion error (500) or other error
        if "500" in error_msg or "API keys exhausted" in error_msg or "statusText" in error_msg:
            logger.warning(f"    ⚠️ LLMOCR backend unavailable for {url}: {error_msg[:100]}")
            # Return None to trigger fallback
            return None
        else:
            logger.error(f"    ❌ LLMOCR processing failed for {url}: {str(e)}")
            return None

def process_document_with_azure_documentai_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Process document using Azure Document Intelligence (uses Azure subscription/credits: $18 for 12k docs).
    Requires AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY environment variables.
    Free tier: 500 pages/month included!
    """
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        
        logger.info(f"    📄 Processing document with Azure Document Intelligence: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf"  # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
            }
            
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"    ⚠️ Got 403, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Initialize Azure Document Intelligence client
            client = DocumentIntelligenceClient(
                endpoint=AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
                credential=AzureKeyCredential(AZURE_DOCUMENT_INTELLIGENCE_KEY)
            )
            
            # 3. Read file content
            with open(temp_path, "rb") as f:
                file_content = f.read()
            
            # 4. Analyze document using prebuilt-read model (OCR)
            # The body parameter accepts bytes directly (IO[bytes])
            # Note: Free tier only processes first 2 pages. Paid tier processes all pages.
            # pages parameter: None = all pages, "1-5" = pages 1-5, "1,3,5" = specific pages
            logger.info(f"    Processing PDF file: {file_size:,} bytes")
            # Try to process all pages - if free tier, it will only process 2
            poller = client.begin_analyze_document(
                model_id="prebuilt-read",
                body=file_content
                # Don't specify pages parameter - let it process all available pages
                # Free tier limitation: only first 2 pages will be processed
            )
            result = poller.result()
            
            # Debug: Check what we got from Azure
            num_pages = len(result.pages) if hasattr(result, 'pages') and result.pages else 0
            num_paragraphs = len(result.paragraphs) if hasattr(result, 'paragraphs') and result.paragraphs else 0
            content_len = len(result.content) if hasattr(result, 'content') and result.content else 0
            logger.info(f"    📊 Azure result: {num_pages} pages, {num_paragraphs} paragraphs, content={content_len} chars")
            
            # 5. Extract text content - try multiple methods to get full text
            text_content = ""
            
            # Method 1: Use result.content if available (contains full text)
            if hasattr(result, 'content') and result.content:
                text_content = result.content
                logger.debug(f"    Method 1: Extracted {len(text_content):,} chars from result.content")
            
            # Method 2: Extract from paragraphs (more structured, preserves formatting)
            # Try paragraphs even if content exists, as paragraphs might have more complete text
            if hasattr(result, 'paragraphs') and result.paragraphs:
                text_parts = []
                for para in result.paragraphs:
                    if hasattr(para, 'content') and para.content:
                        text_parts.append(para.content)
                paragraphs_text = "\n\n".join(text_parts)
                if len(paragraphs_text) > len(text_content):
                    text_content = paragraphs_text
                    logger.debug(f"    Method 2: Extracted {len(text_content):,} chars from {len(result.paragraphs)} paragraphs (better than content)")
            
            # Method 3: Extract from pages -> lines (fallback)
            if not text_content and hasattr(result, 'pages') and result.pages:
                text_lines = []
                for page in result.pages:
                    if hasattr(page, 'lines') and page.lines:
                        for line in page.lines:
                            if hasattr(line, 'content') and line.content:
                                text_lines.append(line.content)
                pages_text = "\n".join(text_lines)
                if len(pages_text) > len(text_content):
                    text_content = pages_text
                    logger.debug(f"    Method 3: Extracted {len(text_content):,} chars from {len(result.pages)} pages")
            
            if not text_content:
                logger.warning(f"    ⚠️ Azure Document Intelligence returned empty content for {url}")
                logger.warning(f"    Debug: result has content={hasattr(result, 'content')}, pages={hasattr(result, 'pages')}, paragraphs={hasattr(result, 'paragraphs')}")
                return None
            
            logger.info(f"    ✓ Extracted {len(text_content):,} characters from document")
            
            # 6. Format as markdown (Azure returns plain text, we format it)
            markdown_content = f"```\n{text_content}\n```"
            
            # 7. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000],  # Limit content to 50k chars
                'depth': 0,
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ azure-ai-documentintelligence not installed. Install with: pip install azure-ai-documentintelligence")
        return None
    except Exception as e:
        logger.error(f"    ❌ Azure Document Intelligence processing failed for {url}: {str(e)}")
        return None

def process_document_with_gcp_documentai_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Process document using Google Cloud Document AI (cheapest: $18 for 12k docs).
    Requires GOOGLE_APPLICATION_CREDENTIALS environment variable set to service account key path.
    Also requires GCP_PROJECT_ID, GCP_PROCESSOR_LOCATION, and GCP_PROCESSOR_ID environment variables.
    """
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai_v1 as documentai
        
        # Get GCP configuration from environment
        project_id = os.getenv('GCP_PROJECT_ID', '')
        location = os.getenv('GCP_PROCESSOR_LOCATION', 'us')  # Default to 'us'
        processor_id = os.getenv('GCP_PROCESSOR_ID', '')
        
        if not project_id or not processor_id:
            logger.error("    ❌ GCP configuration missing. Set GCP_PROJECT_ID and GCP_PROCESSOR_ID environment variables.")
            return None
        
        if not GOOGLE_APPLICATION_CREDENTIALS:
            logger.error("    ❌ GOOGLE_APPLICATION_CREDENTIALS not set. Set path to service account key JSON file.")
            return None
        
        logger.info(f"    📄 Processing document with Google Cloud Document AI: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf"  # Default to pdf if unknown
        
        # Determine MIME type
        mime_type_map = {
            '.pdf': 'application/pdf',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.gif': 'image/gif',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg'
        }
        mime_type = mime_type_map.get(suffix.lower(), 'application/pdf')
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
            }
            
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"    ⚠️ Got 403, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Process with Google Cloud Document AI
            # Create client with appropriate endpoint
            opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
            client = documentai.DocumentProcessorServiceClient(client_options=opts)
            
            # The full resource name of the processor
            name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
            
            # Read the file into memory
            with open(temp_path, "rb") as image_file:
                image_content = image_file.read()
            
            # Load binary data into a RawDocument
            raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
            
            # Configure the process request
            request = documentai.ProcessRequest(name=name, raw_document=raw_document)
            
            # Use the client to process the document
            result = client.process_document(request=request)
            
            # Get the document response
            document = result.document
            
            # Extract text (Document AI returns plain text, we'll format as markdown)
            text_content = document.text
            
            if not text_content:
                logger.warning(f"    ⚠️ Google Cloud Document AI returned empty content for {url}")
                return None
            
            # Convert to markdown-like format (Document AI doesn't return markdown, but we format it)
            # For now, we'll use plain text wrapped in markdown code blocks
            markdown_content = f"```\n{text_content}\n```"
            
            # 3. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000],  # Limit content to 50k chars
                'depth': 0,
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ google-cloud-documentai not installed. Install with: pip install google-cloud-documentai")
        return None
    except Exception as e:
        logger.error(f"    ❌ Google Cloud Document AI processing failed for {url}: {str(e)}")
        return None

def process_document_with_paddleocr_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Process document using PaddleOCR (FREE, open-source, local processing).
    No API keys needed - runs locally. Good fallback when cloud services fail.
    """
    try:
        from paddleocr import PaddleOCR
        
        logger.info(f"    📄 Processing document with PaddleOCR (free, local): {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf"  # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
            }
            
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"    ⚠️ Got 403, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Initialize PaddleOCR (use_textline_orientation=True for better accuracy, lang='en' for English)
            ocr = PaddleOCR(use_textline_orientation=True, lang='en')
            
            # 3. Process PDF - PaddleOCR can handle PDFs directly
            if suffix.lower() == '.pdf':
                # For PDFs, PaddleOCR processes page by page
                result = ocr.ocr(temp_path, cls=True)
            else:
                # For images
                result = ocr.ocr(temp_path, cls=True)
            
            # 4. Extract text from OCR results
            # PaddleOCR returns: [[[bbox, (text, confidence)], ...], ...] for each page
            text_lines = []
            if result and result[0]:
                for page_result in result:
                    if page_result:
                        for line in page_result:
                            if line and len(line) >= 2:
                                text_content = line[1][0] if isinstance(line[1], tuple) else str(line[1])
                                confidence = line[1][1] if isinstance(line[1], tuple) and len(line[1]) > 1 else 1.0
                                # Only include lines with reasonable confidence
                                if confidence > 0.5:
                                    text_lines.append(text_content)
            
            if not text_lines:
                logger.warning(f"    ⚠️ PaddleOCR returned no text for {url}")
                return None
            
            # 5. Combine text and format as markdown
            text_content = "\n".join(text_lines)
            markdown_content = f"```\n{text_content}\n```"
            
            # 6. Create page-like structure
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000],  # Limit content to 50k chars
                'depth': 0,
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.debug("    ⚠️ PaddleOCR not installed. Install with: pip install paddleocr")
        return None
    except Exception as e:
        logger.warning(f"    ⚠️ PaddleOCR processing failed for {url}: {str(e)}")
        return None

def process_document_with_ocr_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Main OCR processing function - routes to appropriate provider based on configuration.
    Priority: LLMOCR (CHEAPEST) > PaddleOCR (FREE fallback) > Azure Document Intelligence > Google Cloud Document AI > DeepSeek OCR
    
    If LLMOCR fails (e.g., backend API keys exhausted), automatically falls back to PaddleOCR.
    """
    # Try LLMOCR first (CHEAPEST: $0.00449/doc = $53.88 for 12k docs, 82% cheaper than Azure/GCP)
    if LLMOCR_API_KEY:
        result = process_document_with_llmocr_sync(url, foundation_name, session_cookies)
        # If LLMOCR fails due to backend issues, try PaddleOCR as backup
        if result is None:
            logger.info(f"    🔄 LLMOCR failed, trying PaddleOCR backup (free, local)...")
            result = process_document_with_paddleocr_sync(url, foundation_name, session_cookies)
            if result:
                return result
        elif result:
            return result
    
    # Try PaddleOCR as primary if LLMOCR not configured (FREE, open-source)
    result = process_document_with_paddleocr_sync(url, foundation_name, session_cookies)
    if result:
        return result
    
    # Fall back to Azure Document Intelligence ($1.50/1k pages = $306 for 12k docs)
    if AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY:
        return process_document_with_azure_documentai_sync(url, foundation_name, session_cookies)
    
    # Fall back to Google Cloud Document AI ($1.50/1k pages = $306 for 12k docs)
    if GOOGLE_APPLICATION_CREDENTIALS and GCP_PROJECT_ID and GCP_PROCESSOR_ID:
        return process_document_with_gcp_documentai_sync(url, foundation_name, session_cookies)
    
    # Fall back to DeepSeek OCR
    if DEEPSEEK_OCR_API_KEY or DEEPSEEK_OCR_BASE_URL:
        return process_document_with_deepseek_ocr_sync(url, foundation_name, session_cookies)
    
    logger.error("    ❌ No OCR provider configured. Set LLMOCR_API_KEY (cheapest), install PaddleOCR (free), AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT+KEY, GOOGLE_APPLICATION_CREDENTIALS+GCP_PROJECT_ID+GCP_PROCESSOR_ID, or DEEPSEEK_OCR_API_KEY")
    return None

def process_document_with_deepseek_ocr_sync(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Synchronous version of document processing using DeepSeek OCR API.
    Downloads and processes a document (PDF/DOCX) using DeepSeek OCR.
    
    Args:
        url: URL of the document to download and process
        foundation_name: Name of the foundation (for logging)
        session_cookies: Optional session cookies for authenticated downloads
    
    Returns:
        Dict with 'url', 'title', 'content' (markdown), 'depth', 'type' keys, or None if failed
    """
    try:
        from deepseek_ocr import DeepSeekOCR
        
        # Check if base_url is configured (required)
        if not DEEPSEEK_OCR_BASE_URL:
            logger.warning("    ⚠️ DeepSeek OCR base_url not configured. Defaulting to localhost:8000 (self-hosted vLLM).")
            logger.warning("    💡 To use a hosted service, set DEEPSEEK_OCR_BASE_URL environment variable.")
            logger.warning("    💡 For self-hosted vLLM, API key can be 'EMPTY' or any dummy string.")
        
        logger.info(f"    📄 Processing document with DeepSeek OCR: {url[:100]}...")
        
        # 1. Download document to temp file
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "document"
        suffix = Path(filename).suffix
        if not suffix:
            suffix = ".pdf"  # Default to pdf if unknown
            
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            temp_path = tmp_file.name
            
            # Download with requests - use session cookies for Charity Commission
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Accept-Language': 'en-GB,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://register-of-charities.charitycommission.gov.uk/',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin'
            }
            
            # Try download with cookies first
            try:
                response = requests.get(url, stream=True, timeout=60, headers=headers, cookies=session_cookies, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    # If 403, try without cookies (some PDFs might be public)
                    logger.warning(f"    ⚠️ Got 403 with cookies, retrying without cookies...")
                    response = requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True)
                    response.raise_for_status()
                else:
                    raise
            
            # Download the file content
            file_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    tmp_file.write(chunk)
                    file_size += len(chunk)
            
            # Verify we got content
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            
            logger.debug(f"    Downloaded {file_size:,} bytes")
                
        try:
            # 2. Process with DeepSeek OCR
            # Initialize client with rate limiting (100 requests/minute = 0.6s delay)
            # base_url is required - either from env var or default to localhost for self-hosted
            base_url = DEEPSEEK_OCR_BASE_URL or 'http://localhost:8000/v1'  # Default to local vLLM server
            
            # For self-hosted vLLM, API key can be "EMPTY" or any dummy string
            api_key = DEEPSEEK_OCR_API_KEY or 'EMPTY'
            
            client = DeepSeekOCR(
                api_key=api_key,
                base_url=base_url,
                request_delay=DEEPSEEK_OCR_RATE_LIMIT_DELAY,
                enable_rate_limit_retry=True,
                max_rate_limit_retries=3,
                rate_limit_retry_delay=1.0,
                timeout=DEEPSEEK_OCR_TIMEOUT
            )
            
            # Parse document (synchronous)
            markdown_content = client.parse(temp_path)
            
            if not markdown_content:
                logger.warning(f"    ⚠️ DeepSeek OCR returned empty content for {url}")
                return None
            
            # 3. Create page-like structure (same format as Docling output)
            return {
                'url': url,
                'title': f"Document: {filename}",
                'content': markdown_content[:50000],  # Limit content to 50k chars
                'depth': 0,  # Treat docs as depth 0 importance
                'type': 'document'
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except ImportError:
        logger.error("    ❌ DeepSeek OCR not installed. Please install 'deepseek-ocr' to process documents.")
        return None
    except Exception as e:
        logger.error(f"    ❌ DeepSeek OCR processing failed for {url}: {str(e)}")
        return None

async def process_document_with_deepseek_ocr(url: str, foundation_name: str, session_cookies: Optional[Dict] = None) -> Optional[Dict]:
    """
    Asynchronous wrapper for DeepSeek OCR document processing.
    Uses thread pool executor to run synchronous DeepSeek OCR processing.
    
    Args:
        url: URL of the document to download and process
        foundation_name: Name of the foundation (for logging)
        session_cookies: Optional session cookies for authenticated downloads
    
    Returns:
        Dict with 'url', 'title', 'content' (markdown), 'depth', 'type' keys, or None if failed
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # Use default executor
        process_document_with_deepseek_ocr_sync,
        url,
        foundation_name,
        session_cookies
    )

# =============================================================================
# EMBEDDINGS
# =============================================================================

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings using OpenAI.
    
    Args:
        texts: List of text chunks
        
    Returns:
        List of embedding vectors
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    embeddings = []
    batch_size = 100
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=batch
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            # Add zero vectors as fallback
            embeddings.extend([[0.0] * 1536] * len(batch))
    
    return embeddings

# =============================================================================
# ANALYSIS (Direct LLM / DeepSeek)
# =============================================================================

async def analyze_foundation_content(pages: List[Dict], foundation_name: str) -> Dict:
    """
    Analyze foundation pages using direct LLM API (DeepSeek).
    """
    logger.info(f"  🤖 Starting DeepSeek analysis...")
    try:
        analysis = await analyze_with_direct_llm(pages, foundation_name, use_deepseek=True)
        logger.info(f"  ✓ Analysis complete. Found {len(analysis.get('opportunities', []))} opportunities.")
        
        # Inject important URLs into opportunities if they don't have them
        important_urls = [page['url'] for page in pages[:5]]
        if 'opportunities' in analysis:
            for opp in analysis['opportunities']:
                if 'important_urls' not in opp or not opp['important_urls']:
                    opp['important_urls'] = important_urls
                    
        return analysis
    except Exception as e:
        logger.error(f"  ❌ Analysis failed: {e}")
        return {
            'opportunities': []
        }

# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def get_funder_charity_number(funder_id: int) -> Optional[str]:
    """Get charity number for a funder."""
    if not is_db_available():
        return None
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT charity_number FROM funders WHERE id = %s
        """, (funder_id,))
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result and result[0] else None
    finally:
        release_db_connection(conn)

def build_charity_commission_url(charity_number: str) -> str:
    """Build Charity Commission profile page URL from charity number."""
    return f"https://register-of-charities.charitycommission.gov.uk/charity-details/?regId={charity_number}&subId=0"

def store_foundation(name: str, url: str) -> int:
    """Store or update foundation in database."""
    if not is_db_available():
        # Return a dummy ID for test mode
        logger.info(f"  📝 Skipping foundation storage (no DB mode)")
        return hash(name) % 1000000  # Generate consistent dummy ID
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO funders (name, website, description, created_at, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE
            SET website = EXCLUDED.website, updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (name, url, f"Foundation: {name}"))
        
        funder_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return funder_id
    finally:
        release_db_connection(conn)

def create_scrape_session(funder_id: int) -> int:
    """Create a new scrape session."""
    if not is_db_available():
        logger.info(f"  📝 Skipping scrape session creation (no DB mode)")
        return hash(str(funder_id)) % 1000000  # Generate consistent dummy ID
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scrape_sessions (funder_id, session_date, status, created_at, updated_at)
            VALUES (%s, CURRENT_TIMESTAMP, 'in_progress', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, (funder_id,))
        
        session_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return session_id
    finally:
        release_db_connection(conn)

def cleanup_foundation_data(funder_id: int):
    """Delete all existing chunks, embeddings, and opportunities for a foundation to avoid duplicates."""
    if not is_db_available():
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Delete opportunities
        cursor.execute("DELETE FROM funding_opportunities WHERE funder_id = %s", (funder_id,))
        
        # Delete chunks (this should cascade to embeddings)
        cursor.execute("DELETE FROM funder_chunks WHERE funder_id = %s", (funder_id,))
        
        conn.commit()
        cursor.close()
        logger.info(f"  🧹 Cleaned up old data for foundation ID {funder_id}")
    finally:
        release_db_connection(conn)

def store_pages_and_embeddings(session_id: int, funder_id: int, pages: List[Dict]):
    """Store crawled pages and generate embeddings."""
    if not is_db_available():
        logger.info(f"  📝 Skipping page storage and embeddings (no DB mode)")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Chunk and generate embeddings
        all_chunks = []
        for page in pages:
            # Simple chunking (500 chars per chunk)
            content = page['content']
            chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
            
            for chunk_order, chunk_text in enumerate(chunks):
                all_chunks.append({
                    'text': chunk_text,
                    'url': page['url'],
                    'title': page['title'],
                    'chunk_order': chunk_order
                })
        
        if not all_chunks:
            return
        
        # Generate embeddings
        chunk_texts = [c['text'] for c in all_chunks]
        embeddings = generate_embeddings(chunk_texts)
        
        # Store chunks and embeddings
        for chunk, embedding in zip(all_chunks, embeddings):
            # Store chunk
            cursor.execute("""
                INSERT INTO funder_chunks (funder_id, scrape_session_id, chunk_text, chunk_order, source_url, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (funder_id, session_id, chunk['text'], chunk['chunk_order'], chunk['url']))
            
            chunk_id = cursor.fetchone()[0]
            
            # Store embedding
            cursor.execute("""
                INSERT INTO chunk_embeddings (chunk_id, embedding, created_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
            """, (chunk_id, embedding))
        
        conn.commit()
        cursor.close()
        
        logger.info(f"  ✓ Stored {len(all_chunks)} chunks with embeddings")
        
    finally:
        release_db_connection(conn)

def store_funding_opportunities(funder_id: int, session_id: int, analysis_result: Dict):
    """Store identified funding opportunities in the database with guaranteed coverage."""
    if not is_db_available():
        logger.info(f"  📝 Skipping opportunity storage (no DB mode)")
        opportunities = analysis_result.get('opportunities', [])
        logger.info(f"  📋 Found {len(opportunities)} opportunities")
        for opp in opportunities:
            logger.info(f"    - {opp.get('opportunity_title', 'Unknown')}")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        opportunities = analysis_result.get('opportunities', [])
        
        stored_count = 0
        ai_opportunities = 0
        
        # Store AI-generated opportunities first
        for opp in opportunities:
            cursor.execute("""
                INSERT INTO funding_opportunities (
                    funder_id, scrape_session_id,
                    opportunity_title, description,
                    eligibility_inclusion, eligibility_exclusion,
                    application_requirements, application_process,
                    application_questions, objectives_goals,
                    funding_focus, funding_amounts,
                    deadlines, evaluation_criteria,
                    contact_info, important_urls,
                    application_form_url, application_form_type,
                    application_questions_list, guidance_url, guidance_text,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (
                funder_id, session_id,
                opp.get('opportunity_title', 'General'),
                opp.get('description', ''),
                opp.get('eligibility_inclusion', ''),
                opp.get('eligibility_exclusion', ''),
                opp.get('application_requirements', ''),
                opp.get('application_process', ''),
                opp.get('application_questions', ''),
                opp.get('objectives_goals', ''),
                opp.get('funding_focus', ''),
                opp.get('funding_amounts', ''),
                opp.get('deadlines', ''),
                opp.get('evaluation_criteria', ''),
                opp.get('contact_info', ''),
                # Pass important_urls if available in the opp, otherwise generic ones
                json.dumps(opp.get('important_urls', [])),
                opp.get('application_form_url', ''),
                opp.get('application_form_type', ''),
                opp.get('application_questions_list', ''),
                opp.get('guidance_url', ''),
                opp.get('guidance_text', '')
            ))
            stored_count += 1
            ai_opportunities += 1
        
        # Check if any opportunities were stored for this funder in this session
        cursor.execute(
            "SELECT COUNT(*) FROM funding_opportunities WHERE funder_id = %s AND scrape_session_id = %s",
            (funder_id, session_id)
        )
        count_result = cursor.fetchone()
        total_stored = count_result[0] if count_result else 0
        
        # GUARANTEED COVERAGE: If no opportunities found, create a DEFAULT_TEMPLATE
        if total_stored == 0:
            logger.info(f"  ⚠️ No opportunities found for funder {funder_id}. Creating DEFAULT_TEMPLATE opportunity...")
            
            # Get funder details for the default template
            cursor.execute(
                "SELECT name, website FROM funders WHERE id = %s",
                (funder_id,)
            )
            funder_result = cursor.fetchone()
            funder_name = funder_result[0] if funder_result else "Unknown Foundation"
            funder_website = funder_result[1] if funder_result else ""
            
            cursor.execute("""
                INSERT INTO funding_opportunities (
                    funder_id, scrape_session_id,
                    opportunity_title, description,
                    eligibility_inclusion, eligibility_exclusion,
                    application_requirements, application_process,
                    application_questions, objectives_goals,
                    funding_focus, funding_amounts,
                    deadlines, evaluation_criteria,
                    contact_info, important_urls,
                    application_form_url, application_form_type,
                    application_questions_list, guidance_url, guidance_text,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (
                funder_id, session_id,
                f"Funding Opportunities - {funder_name}",
                f"This foundation offers funding opportunities. Please visit their website for current programs and application details.",
                "Please check the foundation's website for specific eligibility criteria.",
                "Please check the foundation's website for exclusion criteria.",
                "Visit the foundation's website for current application requirements.",
                "Visit the foundation's website for information about their application process.",
                "Please contact the foundation directly for specific application questions.",
                "The foundation supports various charitable causes and initiatives.",
                "General charitable funding - please see website for specific focus areas.",
                "Funding amounts vary - please check the foundation's website for current information.",
                "Deadlines vary by program - please check the foundation's website for current deadlines.",
                "Please check the foundation's website for evaluation criteria.",
                f"Visit {funder_website} for contact information and application details." if funder_website else "Please visit the foundation's website for contact information.",
                json.dumps([funder_website] if funder_website else []),
                funder_website,
                "Website",
                "Please see the foundation's website for application forms and questions.",
                funder_website,
                "Default template - please visit the foundation's website for detailed guidance."
            ))
            stored_count += 1
            logger.info(f"  ✓ Created DEFAULT_TEMPLATE opportunity for guaranteed coverage")
        
        conn.commit()
        cursor.close()
        
        logger.info(f"  ✓ Stored {stored_count} funding opportunities ({ai_opportunities} AI-generated, {stored_count - ai_opportunities} DEFAULT_TEMPLATE)")
        
    finally:
        release_db_connection(conn)

def complete_scrape_session(session_id: int):
    """Mark scrape session as completed."""
    if not is_db_available():
        logger.info(f"  📝 Skipping session completion (no DB mode)")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scrape_sessions
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (session_id,))
        conn.commit()
        cursor.close()
    finally:
        release_db_connection(conn)

def update_funder_classification(funder_id: int, is_grantmaking: Optional[bool], reason: Optional[str]):
    """Update the funder's classification (Grantmaking vs Operational)."""
    if not is_db_available():
        logger.info(f"  📝 Skipping classification update (no DB mode)")
        return

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE funders
            SET is_grantmaking_charity = %s, funder_type_reason = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_grantmaking, reason, funder_id))
        conn.commit()
        cursor.close()
        logger.info(f"  ✓ Updated funder classification: {'Grantmaking' if is_grantmaking else 'Operational'}")
    finally:
        release_db_connection(conn)

def get_foundation_change_headers(funder_id: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Get stored ETag, Last-Modified, and Content Hash."""
    if not is_db_available():
        logger.info(f"  📝 Skipping header retrieval (no DB mode)")
        return None, None, None
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT etag, last_modified, content_hash FROM funders WHERE id = %s
        """, (funder_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return result[0], result[1], result[2]
        return None, None, None
    finally:
        release_db_connection(conn)

# =============================================================================
# MAIN PROCESSING PIPELINE
# =============================================================================

async def process_foundation(name: str, url: str, semaphore: asyncio.Semaphore, stats: Dict, funder_id: Optional[int] = None):
    """
    Process a single foundation with change detection.
    
    Args:
        name: Foundation name
        url: Foundation website URL (can be regular website or Charity Commission page)
        semaphore: Concurrency control semaphore
        stats: Statistics dictionary
        funder_id: Optional funder ID (if already known)
    """
    foundation_start_time = time.time()
    async with semaphore:
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"Processing: {name}")
            logger.info(f"{'='*70}")
            
            # Store/get foundation
            if not funder_id:
                funder_id = store_foundation(name, url)
            logger.info(f"  ✓ Foundation ID: {funder_id}")
            
            # Determine if this is a Charity Commission page
            is_charity_commission = 'charitycommission.gov.uk' in url.lower() if url else False
            
            # Check for changes using HTTP HEAD
            if CHANGE_DETECTION_ENABLED:
                stored_etag, stored_last_modified, stored_content_hash = get_foundation_change_headers(funder_id)
                changed, new_etag, new_last_modified, new_content_hash = check_url_changed(url, stored_etag, stored_last_modified, stored_content_hash)
                
                # Update headers
                update_change_detection_headers(funder_id, new_etag, new_last_modified, new_content_hash)
                
                if not changed:
                    logger.info(f"  ⏭️  No changes detected - skipping scrape")
                    stats['skipped'] += 1
                    return
            
            # Create scrape session
            session_id = create_scrape_session(funder_id)
            logger.info(f"  ✓ Scrape session ID: {session_id}")
            
            # Crawl foundation website or Charity Commission page
            source_type = "Charity Commission page" if is_charity_commission else "website"
            logger.info(f"  🔍 Crawling {source_type}: {url}")
            crawl_start_time = time.time()
            pages = await crawl_foundation(url, name)
            crawl_elapsed = time.time() - crawl_start_time
            
            # Count documents vs regular pages
            doc_count = len([p for p in pages if p.get('type') == 'document'])
            page_count = len([p for p in pages if p.get('type') != 'document'])
            logger.info(f"  ⏱️ Crawling completed in {crawl_elapsed:.1f}s ({page_count} pages, {doc_count} documents)")
            
            logger.debug(f"  Crawled pages: {len(pages)}")
            
            if not pages:
                logger.warning(f"  ⚠️ No pages crawled")
                stats['failed'] += 1
                return
            
            # Clean up old data before storing new data
            cleanup_foundation_data(funder_id)
            
            # Store pages and generate embeddings
            logger.info(f"  💾 Storing pages and generating embeddings...")
            store_pages_and_embeddings(session_id, funder_id, pages)
            
            # Analyze content
            logger.info(f"  🤖 Analyzing with DeepSeek (direct API)...")
            analysis_start_time = time.time()
            analysis = await analyze_foundation_content(pages, name)
            analysis_elapsed = time.time() - analysis_start_time
            
            opp_count = len(analysis.get('opportunities', []))
            logger.info(f"  ⏱️ Analysis completed in {analysis_elapsed:.1f}s ({opp_count} opportunities found)")
            
            # Update classification
            is_grantmaking = analysis.get('is_grantmaking_charity')
            type_reason = analysis.get('funder_type_reason')
            update_funder_classification(funder_id, is_grantmaking, type_reason)
            
            # Store opportunities
            store_funding_opportunities(funder_id, session_id, analysis)
            
            # Complete session
            complete_scrape_session(session_id)
            
            foundation_total_time = time.time() - foundation_start_time
            logger.info(f"  ✅ Completed {name} in {foundation_total_time:.1f}s total")
            stats['completed'] += 1
            
        except Exception as e:
            foundation_total_time = time.time() - foundation_start_time
            logger.error(f"  ❌ Error processing {name} after {foundation_total_time:.1f}s: {str(e)}")
            stats['failed'] += 1

def load_foundations_from_csv(csv_path: str) -> List[tuple[str, str]]:
    csv_path = os.path.abspath(csv_path)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Foundation CSV not found at {csv_path}")

    logger.info(f"Loading foundations from {csv_path}")
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        foundations = []
        for row in reader:
            name = row.get('Charity Name', '').strip()
            url = row.get('URL', '').strip()
            if name and url and url.startswith('http'):
                foundations.append((name, url))

    if not foundations:
        raise ValueError(f"No valid foundations found in {csv_path}")

    return foundations

def load_funders_with_charity_commission_urls(limit: Optional[int] = None) -> List[tuple[int, str, str]]:
    """
    Load funders from database that have Charity Commission URLs as their website.
    Returns list of (funder_id, name, website_url) tuples.
    """
    if not is_db_available():
        logger.warning("Database not available - cannot load funders with Charity Commission URLs")
        return []
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, name, website 
            FROM funders 
            WHERE website LIKE 'https://register-of-charities.charitycommission.gov.uk/%'
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        
        funders = [(row[0], row[1], row[2]) for row in results]
        logger.info(f"Loaded {len(funders)} funders with Charity Commission URLs")
        return funders
    finally:
        release_db_connection(conn)


def load_test_foundations() -> List[tuple[str, str]]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, 'foundation_urls_20.txt')
    with open(file_path, 'r') as f:
        foundations = [tuple(line.strip().split(',')) for line in f]
    return foundations[:TEST_FOUNDATIONS_COUNT]


def load_new_trusts_from_queue() -> List[tuple[str, str]]:
    """Load new trusts from the monthly charity processor queue files."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    processed_dir = os.path.join(script_dir, 'data', 'processed')
    
    if not os.path.exists(processed_dir):
        logger.warning(f"Processed data directory not found: {processed_dir}")
        return []
    
    # Find the most recent queue file
    queue_files = [f for f in os.listdir(processed_dir) if f.startswith('trusts_to_crawl_') and f.endswith('.json')]
    
    if not queue_files:
        logger.warning("No trust queue files found in processed directory")
        return []
    
    # Sort by filename to get the most recent
    latest_queue_file = sorted(queue_files)[-1]
    queue_path = os.path.join(processed_dir, latest_queue_file)
    
    logger.info(f"Loading trusts from queue file: {queue_path}")
    
    try:
        with open(queue_path, 'r', encoding='utf-8-sig') as f:
            trusts = json.load(f)
        
        # Convert to the format expected by the main pipeline (name, website)
        # For now, we'll just use the trust name as placeholder since we don't have websites yet
        # This will trigger the crawler to search for the website
        foundation_list = []
        for trust in trusts:
            name = trust.get('name', '')
            if name:
                # Use empty website - crawler will search for it
                foundation_list.append((name, ''))
        
        logger.info(f"Loaded {len(foundation_list)} trusts from queue")
        return foundation_list
        
    except Exception as e:
        logger.error(f"Failed to load queue file {queue_path}: {e}")
        return []


def load_new_trusts_from_queue() -> List[tuple[str, str]]:
    """Load new trusts from the monthly charity processor queue files."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    processed_dir = os.path.join(script_dir, 'data', 'processed')
    
    if not os.path.exists(processed_dir):
        logger.warning(f"Processed data directory not found: {processed_dir}")
        return []
    
    # Find the most recent queue file
    queue_files = [f for f in os.listdir(processed_dir) if f.startswith('trusts_to_crawl_') and f.endswith('.json')]
    
    if not queue_files:
        logger.warning("No trust queue files found in processed directory")
        return []
    
    # Sort by filename to get the most recent
    latest_queue_file = sorted(queue_files)[-1]
    queue_path = os.path.join(processed_dir, latest_queue_file)
    
    logger.info(f"Loading trusts from queue file: {queue_path}")
    
    try:
        with open(queue_path, 'r', encoding='utf-8-sig') as f:
            trusts = json.load(f)
        
        # Convert to the format expected by the main pipeline (name, website)
        # For now, we'll just use the trust name as placeholder since we don't have websites yet
        # This will trigger the crawler to search for the website
        foundation_list = []
        for trust in trusts:
            name = trust.get('name', '')
            if name:
                # Use empty website - crawler will search for it
                foundation_list.append((name, ''))
        
        logger.info(f"Loaded {len(foundation_list)} trusts from queue")
        return foundation_list
        
    except Exception as e:
        logger.error(f"Failed to load queue file {queue_path}: {e}")
        return []


async def main(no_db_mode: bool = False, force: bool = False):
    """Main pipeline execution."""
    global NO_DB_MODE, CHANGE_DETECTION_ENABLED
    NO_DB_MODE = no_db_mode
    if force:
        CHANGE_DETECTION_ENABLED = False
    
    print("="*70)
    print("GRANT SEEKER RAG PIPELINE - PRODUCTION VERSION")
    print("="*70)
    print(f"Features:")
    print(f"  ✅ HTTP HEAD pre-scrape change detection")
    print(f"  ✅ DeepSeek V3 for GPT analysis (95% cheaper!)")
    print(f"  ✅ OpenAI embeddings (only for changed content)")
    print(f"  ✅ crawl4ai production crawler (depth-3)")
    print(f"  ✅ GPT-Researcher with local documents")
    print(f"  ✅ Parallel processing ({MAX_CONCURRENT_FOUNDATIONS} workers)")
    if not no_db_mode:
        print(f"  ✅ Azure PostgreSQL integration")
    else:
        print(f"  📝 NO DATABASE MODE (testing only)")
    print("="*70)
    print()
    
    # Initialize database pool (unless in no-db mode)
    if not no_db_mode:
        init_db_pool()
    else:
        logger.info("Running in NO DATABASE MODE - skipping DB initialization")
    
    # Load ONLY funders with Charity Commission URLs (skip regular websites)
    # This is specifically for processing Charity Commission pages only
    # Remove limit for production runs (only use limit in test mode)
    limit = None if not TEST_MODE else TEST_FOUNDATIONS_COUNT
    funders_with_cc_urls = load_funders_with_charity_commission_urls(limit=limit)
    
    if not funders_with_cc_urls:
        logger.error("No funders with Charity Commission URLs found. Exiting.")
        return
    
    print(f"Processing {len(funders_with_cc_urls)} funders via Charity Commission pages ONLY...")
    print(f"Concurrency: {MAX_CONCURRENT_FOUNDATIONS} workers")
    print(f"Change detection: {'ENABLED' if CHANGE_DETECTION_ENABLED else 'DISABLED'}")
    print()
    
    # Statistics
    stats = {
        'completed': 0,
        'skipped': 0,
        'failed': 0,
        'total_foundations': len(funders_with_cc_urls),
        'start_time': datetime.now()
    }
    
    start_time = datetime.now()
    total_foundations = len(funders_with_cc_urls)
    
    print(f"Total foundations to process: {total_foundations}")
    print(f"  - Charity Commission pages: {len(funders_with_cc_urls)}")
    print()
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FOUNDATIONS)
    
    # Process ONLY funders with Charity Commission URLs (treat them like regular websites)
    tasks = []
    for funder_id, name, website_url in funders_with_cc_urls:
        tasks.append(
            process_foundation(name, website_url, semaphore, stats, funder_id=funder_id)
        )
    
    # Progress tracking
    async def progress_tracker():
        """Print progress updates every 30 seconds."""
        while True:
            await asyncio.sleep(30)
            elapsed = (datetime.now() - start_time).total_seconds()
            processed = stats['completed'] + stats['skipped'] + stats['failed']
            remaining = total_foundations - processed
            if processed > 0:
                rate = processed / (elapsed / 3600) if elapsed > 0 else 0
                eta_seconds = (remaining / rate * 3600) if rate > 0 else 0
                eta_hours = eta_seconds / 3600
                print(f"\n📊 Progress: {processed}/{total_foundations} ({processed/total_foundations*100:.1f}%) | "
                      f"Completed: {stats['completed']} | Skipped: {stats['skipped']} | Failed: {stats['failed']} | "
                      f"Rate: {rate:.1f}/hr | ETA: {eta_hours:.1f} hours\n")
    
    # Start progress tracker
    progress_task = asyncio.create_task(progress_tracker())
    
    try:
        await asyncio.gather(*tasks)
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Print summary
    print()
    print("="*70)
    print("PIPELINE SUMMARY")
    print("="*70)
    print(f"Total foundations: {total_foundations}")
    print(f"  - Completed: {stats['completed']}")
    print(f"  - Skipped (no changes): {stats['skipped']}")
    print(f"  - Failed: {stats['failed']}")
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes / {duration/3600:.2f} hours)")
    if stats['completed'] > 0:
        print(f"Average time per foundation: {duration/stats['completed']:.1f} seconds")
        print(f"Processing rate: {stats['completed']/(duration/3600):.1f} foundations/hour")
    print()
    
    # Cost estimate
    changed = stats['completed']
    embedding_cost = (changed / 5000) * 50  # $50 per 5000
    gpt_cost = (changed / 5000) * 4.55  # DeepSeek cost
    total_cost = embedding_cost + gpt_cost
    
    print(f"📊 Cost Estimate (this run):")
    print(f"  Embeddings: ${embedding_cost:.2f}")
    print(f"  GPT Analysis (DeepSeek): ${gpt_cost:.2f}")
    print(f"  Total: ${total_cost:.2f}")
    print()
    
    if CHANGE_DETECTION_ENABLED and stats['skipped'] > 0:
        savings = (stats['skipped'] / stats['total_foundations']) * 100
        print(f"💰 Savings from change detection: {savings:.1f}%")
        print(f"   Skipped {stats['skipped']} unchanged foundations")
    
    print("="*70)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Grant Seeker RAG Pipeline")
    parser.add_argument("--no-db", action="store_true", help="Run in test mode without database connectivity")
    parser.add_argument("--test-foundations", type=int, default=TEST_FOUNDATIONS_COUNT,
                        help="Number of foundations to test with (default: 5)")
    parser.add_argument("--force", action="store_true", help="Force processing even if no changes detected (disables change detection)")
    args = parser.parse_args()
    
    # Update test foundations count if provided
    if args.test_foundations != TEST_FOUNDATIONS_COUNT:
        TEST_FOUNDATIONS_COUNT = args.test_foundations
    
    asyncio.run(main(no_db_mode=args.no_db, force=args.force))
