# Production Pipeline Testing Checklist

## Pre-Test Setup ✓

- [ ] Azure VM created and accessible
- [ ] SSH connection working
- [ ] DeepSeek API key obtained
- [ ] OpenAI API key verified
- [ ] Azure PostgreSQL accessible
- [ ] Database password known
- [ ] Script uploaded to VM

---

## Phase 1: Environment Setup ✓

- [ ] System packages updated (`sudo apt update`)
- [ ] Python dependencies installed (`pip3 install ...`)
- [ ] Playwright installed (`python3 -m playwright install chromium`)
- [ ] Playwright system deps installed (`sudo python3 -m playwright install-deps`)
- [ ] Script configured with API keys
- [ ] Script configured with database password
- [ ] Database connection test passed
- [ ] OpenAI API test passed
- [ ] DeepSeek API test passed
- [ ] crawl4ai import test passed

**Duration:** _____ minutes  
**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 2: Single Foundation Test ✓

- [ ] Script executed successfully
- [ ] First foundation processed
- [ ] No errors in output
- [ ] Crawling completed (multiple pages)
- [ ] Embeddings generated
- [ ] GPT-Researcher analysis completed
- [ ] Data stored in database
- [ ] Database has 1 funder
- [ ] Database has 1 scrape session
- [ ] Database has ~100-200 chunks
- [ ] Database has matching embeddings
- [ ] Database has 1 GPT analysis

**Duration:** _____ minutes  
**Cost:** $_____ 
**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 3: Small Batch Test (5 Foundations) ✓

- [ ] All 5 foundations processed
- [ ] Parallel processing observed (3 concurrent)
- [ ] No crashes or errors
- [ ] All foundations completed successfully
- [ ] Database has 5 funders
- [ ] Database has 5 scrape sessions
- [ ] Database has 5 GPT analyses
- [ ] All funders have ETag or Last-Modified
- [ ] All funders have last_checked timestamp
- [ ] Chunk counts reasonable (~100-300 per funder)

**Duration:** _____ minutes  
**Cost:** $_____  
**Throughput:** _____ foundations/hour  
**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 4: Change Detection Test ✓

- [ ] Script re-run with same foundations
- [ ] All 5 foundations skipped
- [ ] "No change detected" messages shown
- [ ] No new scrape sessions created
- [ ] Duration < 30 seconds
- [ ] Cost = $0.00
- [ ] last_checked timestamps updated
- [ ] No new chunks created
- [ ] No new embeddings generated
- [ ] No new GPT analyses created

**Duration:** _____ seconds  
**Cost:** $0.00  
**Foundations skipped:** _____/5  
**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 5: Parallel Processing Test ✓

- [ ] Concurrency increased to 5
- [ ] Database cleared for fresh test
- [ ] All 5 foundations started simultaneously
- [ ] High CPU usage observed
- [ ] No database connection errors
- [ ] No memory errors
- [ ] All 5 completed successfully
- [ ] Throughput improved vs sequential
- [ ] Data stored correctly
- [ ] No data corruption

**Duration:** _____ minutes  
**Cost:** $_____  
**Throughput:** _____ foundations/hour  
**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 6: Data Validation ✓

### Foundation Data
- [ ] All foundations have names
- [ ] All foundations have websites
- [ ] All have ETag or Last-Modified
- [ ] All have recent last_checked
- [ ] Descriptions present

### Scrape Sessions
- [ ] All sessions have status='completed'
- [ ] All sessions have chunks
- [ ] Session dates are correct

### Chunks & Embeddings
- [ ] All chunks have content
- [ ] All chunks have embeddings
- [ ] Embedding dimensions = 1536
- [ ] Chunk counts reasonable

### GPT Analyses
- [ ] All analyses have full_report
- [ ] All analyses have eligibility_criteria
- [ ] All analyses have funding_amounts
- [ ] All analyses have deadlines
- [ ] Report lengths > 1000 chars
- [ ] Content is specific (not generic)
- [ ] Important URLs populated

**Sample Analysis Quality:**
- [ ] Eligibility criteria is detailed
- [ ] Funding amounts are realistic
- [ ] Deadlines mentioned
- [ ] Analysis is foundation-specific

**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Phase 7: Production Readiness ✓

### Configuration
- [ ] Database credentials correct
- [ ] API keys configured
- [ ] TEST_MODE can be toggled
- [ ] Concurrency appropriate for VM

### Performance
- [ ] Single foundation: 2-5 minutes ✓
- [ ] 5 foundations (parallel): 5-10 minutes ✓
- [ ] Change detection: < 30 seconds ✓
- [ ] Throughput: > 150 foundations/hour (5 workers) ✓

### Cost
- [ ] Single foundation: ~$0.01 ✓
- [ ] 5 foundations: ~$0.05 ✓
- [ ] Change detection: $0.00 ✓
- [ ] Projected monthly: ~$23.60 ✓

### Data Quality
- [ ] All foundations scraped ✓
- [ ] Embeddings correct ✓
- [ ] Analyses detailed ✓
- [ ] Change detection working ✓

**Status:** ✅ PASS / ❌ FAIL  
**Notes:** _____________________

---

## Overall Test Results

| Phase | Duration | Cost | Status |
|-------|----------|------|--------|
| 1. Environment Setup | _____ min | $0 | ☐ PASS ☐ FAIL |
| 2. Single Foundation | _____ min | $_____ | ☐ PASS ☐ FAIL |
| 3. Small Batch (5) | _____ min | $_____ | ☐ PASS ☐ FAIL |
| 4. Change Detection | _____ sec | $0.00 | ☐ PASS ☐ FAIL |
| 5. Parallel Processing | _____ min | $_____ | ☐ PASS ☐ FAIL |
| 6. Data Validation | _____ min | $0 | ☐ PASS ☐ FAIL |
| 7. Production Readiness | _____ min | $0 | ☐ PASS ☐ FAIL |

**Total Duration:** _____ hours  
**Total Cost:** $_____  
**Pass Rate:** _____/7 (_____%)

---

## Production Readiness Decision

### ✅ PRODUCTION READY if:
- [ ] All 7 phases passed
- [ ] Pass rate ≥ 90% (6/7 or 7/7)
- [ ] No critical issues
- [ ] Cost within budget (~$0.01/foundation)
- [ ] Performance acceptable (>100/hour)
- [ ] Data quality good

### ❌ NOT READY if:
- [ ] Multiple phase failures
- [ ] Critical errors encountered
- [ ] Cost too high
- [ ] Performance too slow
- [ ] Data quality issues

---

## Final Decision

**Production Ready:** ☐ YES ☐ NO

**Tester:** _____________________  
**Date:** _____________________  
**Signature:** _____________________

---

## Next Steps

### If READY ✅
1. [ ] Set TEST_MODE = False
2. [ ] Prepare foundation_urls_5000.txt
3. [ ] Schedule weekly runs
4. [ ] Monitor first production run
5. [ ] Set up cost alerts
6. [ ] Document any issues

### If NOT READY ❌
1. [ ] Document all issues
2. [ ] Fix critical problems
3. [ ] Re-run failed phases
4. [ ] Get approval for workarounds
5. [ ] Schedule re-test

---

## Issues Log

| Issue # | Phase | Description | Severity | Status | Resolution |
|---------|-------|-------------|----------|--------|------------|
| 1 | | | ☐ Critical ☐ Major ☐ Minor | ☐ Open ☐ Resolved | |
| 2 | | | ☐ Critical ☐ Major ☐ Minor | ☐ Open ☐ Resolved | |
| 3 | | | ☐ Critical ☐ Major ☐ Minor | ☐ Open ☐ Resolved | |

---

## Approvals

**Technical Lead:** _____________________ Date: _____  
**Product Owner:** _____________________ Date: _____  
**DevOps:** _____________________ Date: _____
