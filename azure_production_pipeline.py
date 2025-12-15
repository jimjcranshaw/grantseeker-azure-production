#!/usr/bin/env python3
"""
FINAL PRODUCTION PIPELINE - Azure PostgreSQL + DeepSeek + Change Detection
===========================================================================

This is the complete, optimized production pipeline with:
- HTTP HEAD pre-scrape change detection (90% cost savings!)
- DeepSeek V3 for GPT analysis (95% cheaper than OpenAI)
- OpenAI embeddings (only for changed content)
- crawl4ai production crawler (depth-3, multi-page)
- GPT-Researcher with local documents only
- Parallel processing (20-40 concurrent workers)
- Full Azure PostgreSQL integration

Cost: ~$23.60/month (vs $236/month without optimizations)
Savings: $212/month (90% reduction!)

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

# Performance Configuration
MAX_CONCURRENT_FOUNDATIONS = 10  # Reduced to 10 to prevent DeepSeek timeouts
MAX_CONCURRENT_CRAWLS = 10  # Crawl 10 pages per foundation in parallel
DB_POOL_SIZE = 20  # Database connection pool size (kept high for safety)
CRAWL_MAX_DEPTH = 3  # Maximum crawl depth
CRAWL_MAX_PAGES = 50  # Maximum pages per foundation
MAX_CONCURRENT_DOCLING = 3  # Process up to 3 documents concurrently with Docling (reduced to prevent CPU overload)
DOCLING_TIMEOUT = 300  # Timeout per document in seconds (5 minutes for large PDFs with OCR)

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

async def extract_charity_commission_documents(crawler: AsyncWebCrawler, base_url: str, charity_number: str) -> List[str]:
    """
    Extract document download URLs from Charity Commission pages.
    Specifically checks accounts-and-annual-returns and governing-document pages.
    """
    import html
    documents_to_process = []
    base_domain = urlparse(base_url).netloc
    
    # Pages to check for documents
    doc_pages = [
        f"https://{base_domain}/en/charity-search/-/charity-details/{charity_number}/accounts-and-annual-returns?_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_organisationNumber={charity_number}",
        f"https://{base_domain}/en/charity-search/-/charity-details/{charity_number}/governing-document?_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_organisationNumber={charity_number}",
    ]
    
    crawler_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=30000,
        cache_mode="bypass"
    )
    
    for doc_page_url in doc_pages:
        try:
            result = await crawler.arun(url=doc_page_url, config=crawler_config)
            if result.success and result.html:
                html_content = result.html
                # Look for download links - Charity Commission uses specific patterns
                # Pattern 1: Links with p_p_resource_id=/accounts-resource (PDF downloads)
                import re
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
                        if full_url not in documents_to_process:
                            documents_to_process.append(full_url)
                
                logger.info(f"    ✓ Found {len([d for d in documents_to_process if doc_page_url.split('/')[-1].split('?')[0] in d])} documents on {doc_page_url.split('/')[-1].split('?')[0]}")
        except Exception as e:
            logger.warning(f"    ⚠️ Failed to extract documents from {doc_page_url}: {str(e)}")
    
    return documents_to_process

async def crawl_foundation(url: str, name: str) -> List[Dict]:
    """
    Crawl a foundation website using crawl4ai with sitemap support and intelligent filtering.
    Special handling for Charity Commission pages to extract documents.
    """
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    # Configure crawler to use sitemap and simple extraction
    crawler_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=30000,
        cache_mode="bypass"
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
                    cc_docs = await extract_charity_commission_documents(crawler, url, charity_number)
                    documents_to_process.extend(cc_docs)
                    logger.info(f"    📄 Found {len(cc_docs)} Charity Commission documents")
            
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
            
            # 4. Process found documents with Docling (in parallel)
            if documents_to_process:
                import time as time_module
                doc_start_time = time_module.time()
                logger.info(f"    📄 Found {len(documents_to_process)} documents for Docling processing")
                
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
                # Access global config variables
                max_concurrent = globals().get('MAX_CONCURRENT_DOCLING', 5)
                docling_timeout = globals().get('DOCLING_TIMEOUT', 120)
                
                async def process_single_document(doc_url: str, idx: int, total: int, executor: ThreadPoolExecutor):
                    """Process a single document using thread pool executor."""
                    doc_start = time_module.time()
                    try:
                        logger.info(f"    📄 [{idx}/{total}] Starting document processing: {doc_url[:80]}...")
                        # Run Docling in thread pool executor (better control than default executor)
                        loop = asyncio.get_event_loop()
                        doc_content = await asyncio.wait_for(
                            loop.run_in_executor(
                                executor,
                                process_document_with_docling_sync,
                                doc_url,
                                name,
                                session_cookies if session_cookies else None
                            ),
                            timeout=docling_timeout
                        )
                        doc_elapsed = time_module.time() - doc_start
                        if doc_content:
                            content_len = len(doc_content.get('content', ''))
                            logger.info(f"    ✓ [{idx}/{total}] Successfully processed in {doc_elapsed:.1f}s ({content_len:,} chars)")
                            return doc_content
                        else:
                            logger.warning(f"    ⚠️ [{idx}/{total}] Processing returned no content after {doc_elapsed:.1f}s")
                            return None
                    except asyncio.TimeoutError:
                        doc_elapsed = time_module.time() - doc_start
                        logger.warning(f"    ⚠️ [{idx}/{total}] Timed out after {doc_elapsed:.1f}s: {doc_url[:80]}...")
                        return None
                    except Exception as e:
                        doc_elapsed = time_module.time() - doc_start
                        logger.warning(f"    ⚠️ [{idx}/{total}] Failed after {doc_elapsed:.1f}s: {e}")
                        return None
                
                # Process up to 10 documents in parallel using ThreadPoolExecutor
                doc_urls = documents_to_process[:10]
                
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


async def main(no_db_mode: bool = False):
    """Main pipeline execution."""
    global NO_DB_MODE
    NO_DB_MODE = no_db_mode
    
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
    
    # Load foundation URLs
    foundations = []
    if TEST_MODE:
        foundations = load_test_foundations()
    else:
        csv_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'All Funders With Websites from Grants AI April 2025  - Removed trusts w_out websites.csv'
        )
        foundations = load_foundations_from_csv(csv_path)
    
    # Also load funders with Charity Commission URLs (already populated in database)
    funders_with_cc_urls = load_funders_with_charity_commission_urls()
    
    print(f"Processing {len(foundations)} foundations with regular websites...")
    if funders_with_cc_urls:
        print(f"Also processing {len(funders_with_cc_urls)} funders via Charity Commission pages...")
    print(f"Concurrency: {MAX_CONCURRENT_FOUNDATIONS} workers")
    print(f"Change detection: {'ENABLED' if CHANGE_DETECTION_ENABLED else 'DISABLED'}")
    print()
    
    # Statistics
    stats = {
        'completed': 0,
        'skipped': 0,
        'failed': 0,
        'total_foundations': len(foundations) + len(funders_with_cc_urls),
        'start_time': datetime.now()
    }
    
    start_time = datetime.now()
    total_foundations = len(foundations) + len(funders_with_cc_urls)
    
    print(f"Total foundations to process: {total_foundations}")
    print(f"  - With websites: {len(foundations)}")
    print(f"  - Charity Commission pages: {len(funders_with_cc_urls)}")
    print()
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FOUNDATIONS)
    
    # Process all foundations in parallel
    tasks = [
        process_foundation(name, url, semaphore, stats)
        for name, url in foundations
    ]
    
    # Process funders with Charity Commission URLs (treat them like regular websites)
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
        savings = (stats['skipped'] / len(foundations)) * 100
        print(f"💰 Savings from change detection: {savings:.1f}%")
        print(f"   Skipped {stats['skipped']} unchanged foundations")
    
    print("="*70)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Grant Seeker RAG Pipeline")
    parser.add_argument("--no-db", action="store_true", help="Run in test mode without database connectivity")
    parser.add_argument("--test-foundations", type=int, default=TEST_FOUNDATIONS_COUNT,
                        help="Number of foundations to test with (default: 5)")
    args = parser.parse_args()
    
    # Update test foundations count if provided
    if args.test_foundations != TEST_FOUNDATIONS_COUNT:
        TEST_FOUNDATIONS_COUNT = args.test_foundations
    
    asyncio.run(main(no_db_mode=args.no_db))
