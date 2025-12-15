# Running Charity Commission Pipeline Overnight

## Quick Start

### Start the Pipeline
```bash
cd /home/azureuser/grantseeker-azure-production-1
./run_charity_commission_pipeline.sh
```

This will:
- Start the pipeline in a detached tmux session
- Process all 5,988+ Charity Commission funders
- Show progress updates every 30 seconds
- Log everything to `pipeline_run_YYYYMMDD_HHMMSS.log`

### Check Progress (Without Attaching)
```bash
./check_pipeline_status.sh
```

### Attach to Watch Progress Live
```bash
tmux attach -t charity-commission-pipeline
```
Press `Ctrl+B` then `D` to detach without stopping

### View Logs
```bash
# Find latest log
LATEST=$(ls -t pipeline_run_*.log | head -1)

# Watch progress updates
tail -f "$LATEST" | grep -E "(📊 Progress|Completed|Failed|SUMMARY)"

# View last 50 lines
tail -50 "$LATEST"
```

## What's Being Processed

- **Total Funders**: ~5,988 with Charity Commission URLs
- **Documents per Funder**: 2 annual accounts (first 2 most recent)
- **OCR Service**: LLMOCR ($0.00449 per document)
- **Total Cost**: ~$53.77 for all documents
- **Estimated Time**: ~200 hours (8-9 days) at 2 min/funder

## Progress Tracking

The pipeline shows updates every 30 seconds:
```
📊 Progress: 150/5988 (2.5%) | Completed: 120 | Skipped: 25 | Failed: 5 | Rate: 8.5/hr | ETA: 687.5 hours
```

## Expected Output

For each foundation:
1. ✅ Crawl Charity Commission profile pages
2. ✅ Extract and download 2 annual accounts
3. ✅ Process documents with LLMOCR (full text extraction)
4. ✅ Chunk and store in database with embeddings
5. ✅ Run DeepSeek analysis to find opportunities
6. ✅ Store funding opportunities

## Monitoring

### Quick Status Check
```bash
./check_pipeline_status.sh
```

### Watch Logs in Real-Time
```bash
tail -f pipeline_run_*.log | grep -E "(Progress|Completed|Failed|ERROR)"
```

### Check Database Progress
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'sslmode': 'require'
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Count processed funders
cursor.execute(\"\"\"
    SELECT COUNT(DISTINCT f.id)
    FROM funders f
    JOIN scrape_sessions s ON s.funder_id = f.id
    WHERE f.website LIKE '%charitycommission.gov.uk%'
    AND s.status = 'completed'
\"\"\")
processed = cursor.fetchone()[0]

cursor.execute(\"\"\"
    SELECT COUNT(*) 
    FROM funders 
    WHERE website LIKE '%charitycommission.gov.uk%'
\"\"\")
total = cursor.fetchone()[0]

print(f'Processed: {processed}/{total} ({processed/total*100:.1f}%)')

cursor.close()
conn.close()
"
```

## Stopping the Pipeline

### Graceful Stop (Wait for Current Foundation)
```bash
tmux send-keys -t charity-commission-pipeline C-c
```

### Force Stop
```bash
tmux kill-session -t charity-commission-pipeline
```

## Troubleshooting

### Session Not Found
```bash
# Check if it crashed
ls -lt pipeline_run_*.log | head -1 | xargs tail -50

# Check for errors
grep -i error pipeline_run_*.log | tail -20
```

### Pipeline Seems Stuck
```bash
# Attach and see what's happening
tmux attach -t charity-commission-pipeline

# Check for LLMOCR errors
grep -i "llmocr.*error\|llmocr.*failed" pipeline_run_*.log | tail -10
```

### Restart After Crash
```bash
# Kill existing session
tmux kill-session -t charity-commission-pipeline 2>/dev/null

# Start fresh
./run_charity_commission_pipeline.sh
```

## Configuration

Current settings in `charity_commission_pipeline.py`:
- `MAX_CONCURRENT_FOUNDATIONS = 10` (foundations processed in parallel)
- `MAX_CONCURRENT_DEEPSEEK_OCR = 2` (documents processed concurrently)
- `DEEPSEEK_OCR_TIMEOUT = 60` (60 seconds per document)
- `TEST_MODE = False` (production mode - processes all funders)

## Cost Tracking

- **LLMOCR**: $0.00449 per document
- **Total Documents**: ~11,976 (5,988 funders × 2 documents)
- **Total Cost**: ~$53.77
- **DeepSeek Analysis**: Free (using DeepSeek API)
- **OpenAI Embeddings**: ~$0.01 per foundation

## Success Criteria

✅ All 5,988+ funders processed
✅ 2 annual accounts downloaded per funder
✅ Full text extracted (25k-44k chars per document)
✅ Chunks stored with embeddings
✅ Opportunities identified and stored
✅ Database updated with classifications

