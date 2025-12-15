# Resuming Charity Commission Pipeline

## Current Status

**Paused due to:** LLMOCR backend API keys exhausted (not your credits - you still have 3,280 credits)

**Progress:** ~1,199 foundations processed (20% complete)

## To Resume Later

### 1. Check LLMOCR Status
Visit your LLMOCR dashboard to confirm the service is back online:
- Check if credits are still available (you have 3,280)
- Verify the API is responding

### 2. Restart the Pipeline
```bash
cd /home/azureuser/grantseeker-azure-production-1

# Kill any existing session
tmux kill-session -t charity-commission-pipeline 2>/dev/null

# Start fresh (it will skip already processed foundations via change detection)
./run_charity_commission_pipeline.sh
```

### 3. Monitor Progress
```bash
# Check status
./check_pipeline_status.sh

# Watch for LLMOCR errors
tail -f pipeline_run_*.log | grep -E "(LLMOCR|Successfully processed|API error)"
```

## What Happens on Resume

The pipeline uses **change detection** - it will:
- ✅ Skip foundations already processed (won't re-process)
- ✅ Only process remaining foundations
- ✅ Continue from where it left off

## Expected Behavior

Once LLMOCR backend is fixed:
- Documents will process successfully again
- Full text extraction will resume (25k-44k chars per document)
- Pipeline will complete remaining ~4,789 foundations

## Check Progress Before Resuming

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
print(f'Remaining: {total - processed}')

cursor.close()
conn.close()
"
```

## Notes

- **Change detection is enabled** - already processed foundations will be skipped
- **Your credits are safe** - 3,280 credits still available
- **Progress is saved** - all processed foundations are in the database
- **Resume anytime** - just restart the script when LLMOCR is back online

