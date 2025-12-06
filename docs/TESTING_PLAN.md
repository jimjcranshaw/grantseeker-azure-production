# Grant Seeker RAG Pipeline - Production Testing Plan

## 🎯 Testing Objectives

1. Verify all components work correctly
2. Validate cost savings from change detection
3. Confirm data quality and completeness
4. Test parallel processing performance
5. Ensure production readiness

---

## 📋 Testing Phases

### Phase 1: Environment Setup (30 minutes)
### Phase 2: Single Foundation Test (15 minutes)
### Phase 3: Small Batch Test - 5 Foundations (30 minutes)
### Phase 4: Change Detection Test (20 minutes)
### Phase 5: Parallel Processing Test (45 minutes)
### Phase 6: Data Validation (30 minutes)
### Phase 7: Production Readiness Check (15 minutes)

**Total Testing Time: ~3 hours**

---

## 🔧 Phase 1: Environment Setup

### Objective
Set up the testing environment and verify all dependencies.

### Steps

#### 1.1 Get API Keys

**DeepSeek API Key:**
1. Go to https://platform.deepseek.com/
2. Sign up for free account
3. Navigate to API Keys section
4. Create new API key
5. Copy the key (starts with `sk-...`)

**OpenAI API Key:**
1. You already have this
2. Verify it's still active at https://platform.openai.com/api-keys

#### 1.2 Set Up Azure VM

**Option A: Use existing VM (grantseeker-test-vm)**
```bash
# Connect via SSH
ssh azureuser@68.219.65.205
```

**Option B: Create new VM**
- Size: D4s_v3 (4 vCPUs, 16GB RAM) for testing
- OS: Ubuntu 22.04
- Follow previous VM setup steps

#### 1.3 Install Dependencies

```bash
# Update system
sudo apt update

# Install Python dependencies
pip3 install crawl4ai playwright openai psycopg2-binary gpt-researcher langchain requests

# Install Playwright browsers
python3 -m playwright install chromium

# Install Playwright system dependencies
sudo python3 -m playwright install-deps
```

#### 1.4 Upload Pipeline Script

**Method 1: Direct paste**
```bash
nano azure_production_final.py
# Paste content, Ctrl+O, Enter, Ctrl+X
```

**Method 2: SCP from local machine**
```bash
# On your local machine
scp azure_production_final.py azureuser@68.219.65.205:~/
```

#### 1.5 Configure API Keys

```bash
nano azure_production_final.py
```

Update these lines:
```python
OPENAI_API_KEY = "sk-your-openai-key-here"
DEEPSEEK_API_KEY = "sk-your-deepseek-key-here"
```

Also update database password:
```python
DB_CONFIG = {
    ...
    'password': 'YourActualPassword',
    ...
}
```

Save and exit (Ctrl+O, Enter, Ctrl+X)

### Validation

```bash
# Test database connection
python3 -c "import psycopg2; conn = psycopg2.connect(host='grantseeker-pg-server.postgres.database.azure.com', user='grantseekeradmin', password='YOUR_PASSWORD', database='postgres', sslmode='require'); print('✅ Database connection successful')"

# Test OpenAI API
python3 -c "from openai import OpenAI; client = OpenAI(api_key='YOUR_KEY'); print('✅ OpenAI API working')"

# Test DeepSeek API
python3 -c "from openai import OpenAI; client = OpenAI(api_key='YOUR_DEEPSEEK_KEY', base_url='https://api.deepseek.com'); print('✅ DeepSeek API working')"

# Test crawl4ai
python3 -c "import asyncio; from crawl4ai import AsyncWebCrawler; print('✅ crawl4ai installed')"
```

**Expected Output:**
```
✅ Database connection successful
✅ OpenAI API working
✅ DeepSeek API working
✅ crawl4ai installed
```

---

## 🧪 Phase 2: Single Foundation Test

### Objective
Test the pipeline with ONE foundation to verify all components work.

### Steps

#### 2.1 Run Test

```bash
python3 azure_production_final.py 2>&1 | tee test_single.log
```

(Script is already configured for TEST_MODE with 5 foundations, but will start with first one)

#### 2.2 Monitor Output

**Expected output:**
```
======================================================================
GRANT SEEKER RAG PIPELINE - PRODUCTION VERSION
======================================================================
Features:
  ✅ HTTP HEAD pre-scrape change detection
  ✅ DeepSeek V3 for GPT analysis (95% cheaper!)
  ✅ OpenAI embeddings (only for changed content)
  ✅ crawl4ai production crawler (depth-3)
  ✅ GPT-Researcher with local documents
  ✅ Parallel processing
  ✅ Azure PostgreSQL integration
======================================================================

Processing 5 foundations...
Concurrency: 3 workers
Change detection: ENABLED

======================================================================
Processing: Gates Foundation
======================================================================
  ✓ Foundation ID: 1
  📍 First check for https://www.gatesfoundation.org
  ✓ Scrape session ID: 1
  🔍 Crawling: https://www.gatesfoundation.org
    ✓ Crawled: https://www.gatesfoundation.org (depth 0, 15234 chars)
    ✓ Crawled: https://www.gatesfoundation.org/about/... (depth 1, 8456 chars)
    ...
  📊 Crawled 23 pages from https://www.gatesfoundation.org
  💾 Storing pages and generating embeddings...
  ✓ Stored 156 chunks with embeddings
  🤖 Analyzing with GPT-Researcher (DeepSeek)...
  🔬 Starting GPT-Researcher analysis...
  ✓ GPT-Researcher analysis complete (8543 chars)
  ✓ Stored GPT analysis (ID: 1)
  ✅ Completed Gates Foundation
```

### Validation

#### 2.3 Check Database

```bash
# Connect to PostgreSQL
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
SELECT 
    (SELECT COUNT(*) FROM funders) as funders,
    (SELECT COUNT(*) FROM scrape_sessions) as sessions,
    (SELECT COUNT(*) FROM funder_chunks) as chunks,
    (SELECT COUNT(*) FROM chunk_embeddings) as embeddings,
    (SELECT COUNT(*) FROM gpt_analyses) as analyses;
"
```

**Expected output:**
```
 funders | sessions | chunks | embeddings | analyses 
---------+----------+--------+------------+----------
       1 |        1 |    156 |        156 |        1
```

### Success Criteria

✅ Script runs without errors  
✅ All log messages appear  
✅ Database has 1 funder, 1 session, ~100-200 chunks  
✅ GPT analysis contains detailed information  
✅ Duration: 2-5 minutes  
✅ Cost: ~$0.01  

---

## 🧪 Phase 3: Small Batch Test (5 Foundations)

### Objective
Let the test complete for all 5 foundations to verify parallel processing.

### Steps

#### 3.1 Continue Watching

The script should continue processing the remaining 4 foundations in parallel.

#### 3.2 Monitor Progress

**Expected:** Multiple foundations processing simultaneously

```
Processing: Gates Foundation
Processing: Ford Foundation
Processing: Rockefeller Foundation
... (3 start at once)

✅ Completed Gates Foundation
✅ Completed Ford Foundation
... (next foundation starts)
```

### Validation

#### 3.3 Check Database Counts

```bash
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
SELECT 
    (SELECT COUNT(*) FROM funders) as funders,
    (SELECT COUNT(*) FROM scrape_sessions) as sessions,
    (SELECT COUNT(*) FROM gpt_analyses) as analyses;
"
```

**Expected:**
```
 funders | sessions | analyses 
---------+----------+----------
       5 |        5 |        5
```

### Success Criteria

✅ All 5 foundations processed  
✅ No errors or crashes  
✅ Parallel processing works (3 at once)  
✅ Duration: 5-10 minutes  
✅ Cost: ~$0.05  
✅ All foundations have ETag/Last-Modified headers  

---

## 🔄 Phase 4: Change Detection Test

### Objective
Verify HTTP HEAD change detection works and saves costs.

### Steps

#### 4.1 Run Same Batch Again

```bash
# Run the exact same script again (no changes to foundations)
python3 azure_production_final.py 2>&1 | tee test_change_detection.log
```

#### 4.2 Expected Output

```
======================================================================
Processing: Gates Foundation
======================================================================
  ✓ Foundation ID: 1
  ✓ No change detected for https://www.gatesfoundation.org
  ⏭️  No changes detected - skipping scrape

... (same for all 5 foundations)

======================================================================
PIPELINE SUMMARY
======================================================================
Foundations processed: 0/5
Skipped (no changes): 5
Failed: 0
Duration: 12.3 seconds
Rate: 1463.4 foundations/hour

📊 Cost Estimate (this run):
  Embeddings: $0.00
  GPT Analysis (DeepSeek): $0.00
  Total: $0.00

💰 Savings from change detection: 100.0%
   Skipped 5 unchanged foundations
======================================================================
```

### Validation

#### 4.3 Verify No New Sessions Created

```bash
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
SELECT COUNT(*) as total_sessions FROM scrape_sessions;
"
```

**Expected:** Still 5 (no new sessions created)

### Success Criteria

✅ All 5 foundations skipped  
✅ Duration: < 30 seconds (vs 5-10 minutes!)  
✅ Cost: $0.00  
✅ No new scrape sessions created  
✅ Change detection working perfectly!  

---

## ⚡ Phase 5: Parallel Processing Test

### Objective
Test higher concurrency and measure performance.

### Steps

#### 5.1 Modify Script for Higher Concurrency

```bash
nano azure_production_final.py
```

Change:
```python
MAX_CONCURRENT_FOUNDATIONS = 5  # All 5 at once!
```

#### 5.2 Clear Previous Data

```bash
# To test fresh scraping
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
TRUNCATE funders, scrape_sessions, funder_chunks, chunk_embeddings, gpt_analyses CASCADE;
"
```

#### 5.3 Run Test

```bash
time python3 azure_production_final.py 2>&1 | tee test_parallel.log
```

### Validation

#### 5.4 Calculate Throughput

From the output:
```
Duration: 180.5 seconds (3.0 minutes)
Rate: 100.0 foundations/hour
```

**Expected rates:**
- 1 worker: ~30 foundations/hour
- 3 workers: ~90-120 foundations/hour
- 5 workers: ~150-200 foundations/hour
- 10 workers: ~300-400 foundations/hour
- 20 workers: ~500-700 foundations/hour
- 40 workers: ~1000-1200 foundations/hour

### Success Criteria

✅ All 5 foundations processed simultaneously  
✅ No database connection errors  
✅ Throughput scales with concurrency  
✅ No memory issues  
✅ All data stored correctly  

---

## ✅ Phase 6: Data Validation

### Objective
Verify data quality and completeness.

### Steps

#### 6.1 Check Foundation Data

```bash
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
SELECT 
    id,
    name,
    website,
    LENGTH(description) as desc_length,
    etag IS NOT NULL as has_etag,
    last_modified IS NOT NULL as has_last_modified,
    last_checked
FROM funders
ORDER BY id;
"
```

#### 6.2 Sample Analysis Quality

```bash
PGPASSWORD='YOUR_PASSWORD' psql -h grantseeker-pg-server.postgres.database.azure.com -U grantseekeradmin -d postgres -c "
SELECT 
    f.name,
    LEFT(g.eligibility_criteria, 200) as eligibility,
    LEFT(g.funding_amounts, 100) as amounts
FROM gpt_analyses g
JOIN funders f ON g.funder_id = f.id
LIMIT 1;
"
```

**Manually review:**
- Is eligibility criteria specific and detailed?
- Are funding amounts realistic?
- Does it look like real analysis (not generic)?

### Success Criteria

✅ All foundations have complete data  
✅ All embeddings are 1536 dimensions  
✅ All GPT analyses have substantial content  
✅ Analysis quality is good (specific, detailed)  
✅ No NULL values in critical fields  

---

## 🚀 Phase 7: Production Readiness Check

### Objective
Verify the pipeline is ready for production deployment.

### Checklist

#### 7.1 Configuration

- [ ] Database credentials are correct
- [ ] API keys are set
- [ ] TEST_MODE can be toggled
- [ ] Concurrency settings are appropriate for VM size

#### 7.2 Performance

- [ ] Single foundation: 2-5 minutes
- [ ] 5 foundations (parallel): 5-10 minutes
- [ ] Change detection: < 30 seconds for 5 foundations
- [ ] Throughput: > 150 foundations/hour with 5 workers (testing)

#### 7.3 Cost

- [ ] Single foundation: ~$0.01
- [ ] 5 foundations: ~$0.05
- [ ] Change detection run: $0.00
- [ ] Projected monthly cost: ~$23.60 for 5000 foundations

#### 7.4 Data Quality

- [ ] All foundations scraped successfully
- [ ] Embeddings generated correctly
- [ ] GPT analyses are detailed and specific
- [ ] Change detection headers stored

---

## 📊 Testing Summary Report Template

```
GRANT SEEKER RAG PIPELINE - TESTING SUMMARY
============================================

Test Date: [DATE]
Tester: [NAME]
VM: [VM SIZE]
Duration: [TOTAL HOURS]

RESULTS:
--------
Phase 1 - Environment Setup: ✅ PASS
Phase 2 - Single Foundation: ✅ PASS
Phase 3 - Small Batch (5): ✅ PASS
Phase 4 - Change Detection: ✅ PASS
Phase 5 - Parallel Processing: ✅ PASS
Phase 6 - Data Validation: ✅ PASS
Phase 7 - Production Readiness: ✅ PASS

PERFORMANCE:
------------
Single Foundation: [X] minutes
5 Foundations (parallel): [X] minutes
Change Detection (5): [X] seconds
Throughput: [X] foundations/hour

COSTS:
------
Single Foundation: $[X]
5 Foundations: $[X]
Change Detection: $0.00
Projected Monthly (5000): $[X]

PRODUCTION READY: ✅ YES / ❌ NO
```

---

## 🐛 Common Issues & Solutions

### Issue: Playwright browsers not found
**Solution:**
```bash
python3 -m playwright install chromium
sudo python3 -m playwright install-deps
```

### Issue: Database connection failed
**Solutions:**
1. Check firewall rules (allow your VM IP)
2. Verify connection string
3. Test with psql command line

### Issue: DeepSeek API errors
**Solutions:**
1. Verify API key from https://platform.deepseek.com/
2. Check base_url is correct: `https://api.deepseek.com`
3. Ensure API key has no extra spaces

### Issue: Out of memory
**Solutions:**
1. Reduce MAX_CONCURRENT_FOUNDATIONS
2. Reduce CRAWL_MAX_PAGES
3. Use larger VM

---

## 🎉 Success Criteria Summary

**The pipeline is production-ready when:**

✅ All 7 testing phases pass  
✅ Change detection saves 90%+ of foundations  
✅ Cost is ~$0.01 per foundation  
✅ Throughput is > 100 foundations/hour  
✅ Data quality is high (detailed analyses)  
✅ No critical errors or crashes  
✅ All database tables populated correctly  

**Expected Results:**
- Week 1 (5000 foundations): 7-10 hours with 20 workers, $54.55
- Week 2+ (500 changed): 1-2 hours, $5.45
- Annual cost: ~$332 (vs $3,780 without optimizations)
- **91% cost savings achieved!** 🎊
