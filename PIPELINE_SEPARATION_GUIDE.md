# Pipeline Separation Guide

## Overview

We've separated the pipeline into two specialized scripts to handle different types of foundations:

1. **`charity_commission_pipeline.py`** - For Charity Commission profile pages
2. **`regular_website_pipeline.py`** - For standard funder websites

## Why Separate?

### Charity Commission Foundations
- **Documents are CRITICAL** - Annual accounts, articles of association contain the key information
- Documents are often large PDFs requiring extensive OCR
- Need longer timeouts and retry logic
- Cannot skip document processing

### Regular Website Foundations
- Documents are **optional** - Website content is primary source
- Can skip documents if they fail/timeout
- Standard processing is sufficient
- Faster processing without document overhead

## Key Differences

| Feature | Charity Commission Pipeline | Regular Website Pipeline |
|---------|---------------------------|-------------------------|
| **Data Source** | Database (Charity Commission URLs) | CSV file (regular websites) |
| **Docling Timeout** | 15 minutes (900s) | 5 minutes (300s) |
| **Document Retries** | 2 retries | No retries |
| **Document Processing** | **REQUIRED** (critical) | Optional (can skip) |
| **Concurrent Docling Workers** | 2 (reduced for stability) | 3 |
| **Failure Handling** | Logs as CRITICAL if docs fail | Gracefully skips failed docs |

## Usage

### Charity Commission Pipeline

```bash
# Run in tmux (recommended for long runs)
./run_charity_commission_pipeline.sh

# Or directly
python3 charity_commission_pipeline.py

# With test mode
python3 charity_commission_pipeline.py --test-foundations 5
```

**Processes:** ~5,988 foundations with Charity Commission URLs

### Regular Website Pipeline

```bash
# Run in tmux (recommended for long runs)
./run_regular_website_pipeline.sh

# Or directly
python3 regular_website_pipeline.py

# With test mode
python3 regular_website_pipeline.py --test-foundations 5
```

**Processes:** ~5,298 foundations with regular websites

## Document Processing

### Charity Commission Pipeline
- **Extended timeout:** 15 minutes per document
- **Retry logic:** Up to 2 retries (3 total attempts)
- **Critical failures:** Logs errors if documents fail after all retries
- **No skipping:** Foundation processing continues but logs warnings

### Regular Website Pipeline
- **Standard timeout:** 5 minutes per document
- **No retries:** Single attempt only
- **Graceful skipping:** Documents that fail are skipped, foundation processing continues normally

## Configuration

Both pipelines share the same core configuration:
- `MAX_CONCURRENT_FOUNDATIONS = 10`
- `CHANGE_DETECTION_ENABLED = True`
- Same database and API configurations

Only document processing differs between the two.

## Monitoring

Use the same monitoring scripts for both:
- `check_pipeline_status.sh` - Check if pipeline is running
- `generate_progress_report.sh` - Generate progress report

Log files are named:
- `pipeline_run_YYYYMMDD_HHMMSS.log` (both pipelines use same naming)

## Recommendations

1. **Run Charity Commission pipeline separately** - It's slower due to document processing
2. **Run Regular Website pipeline separately** - Faster, can run more frequently
3. **Monitor document processing** - Check logs for CRITICAL failures in CC pipeline
4. **Use tmux** - Both pipelines benefit from running in detached sessions
