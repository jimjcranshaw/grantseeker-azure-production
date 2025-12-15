# Running Charity Commission Pipeline in TMUX

## Quick Start

### Start the Pipeline
```bash
cd /home/azureuser/grantseeker-azure-production-1
./run_charity_commission_pipeline.sh
```

### Check Status
```bash
./check_pipeline_status.sh
```

### Attach to Session (to watch progress)
```bash
tmux attach -t charity-commission-pipeline
```

### Detach from Session
- Press `Ctrl+B` then `D` (while attached)

### View Logs (without attaching)
```bash
# View latest log
tail -f pipeline_run_*.log | tail -1

# Or find the latest log file
LATEST=$(ls -t pipeline_run_*.log | head -1)
tail -f "$LATEST"

# View progress updates only
grep "📊 Progress" "$LATEST" | tail -20
```

### Stop the Pipeline
```bash
tmux kill-session -t charity-commission-pipeline
```

## What Happens

1. **Pipeline starts** in detached tmux session
2. **Progress updates** every 30 seconds showing:
   - Current progress (X/Y foundations)
   - Completed/Skipped/Failed counts
   - Processing rate (foundations/hour)
   - ETA (estimated time remaining)
3. **Logs saved** to `pipeline_run_YYYYMMDD_HHMMSS.log`
4. **Runs overnight** - you can disconnect and reconnect anytime

## Monitoring Progress

### While Attached
You'll see real-time output with progress updates like:
```
📊 Progress: 150/6000 (2.5%) | Completed: 120 | Skipped: 25 | Failed: 5 | Rate: 8.5/hr | ETA: 687.5 hours
```

### Without Attaching
```bash
# Quick status check
./check_pipeline_status.sh

# Watch logs in real-time
tail -f pipeline_run_*.log | grep -E "(Progress|SUMMARY|Completed|Failed)"
```

## Expected Runtime

Based on current configuration:
- **Worst case**: ~4.7 days (if all documents take 5 minutes)
- **Realistic**: ~2-3 days (if documents average 2-3 minutes)
- **With change detection**: Much faster (skips unchanged foundations)

## Troubleshooting

### Session not found
```bash
# List all tmux sessions
tmux ls

# Check if it crashed
tail -50 pipeline_run_*.log | tail -1
```

### Pipeline seems stuck
```bash
# Attach and check what's happening
tmux attach -t charity-commission-pipeline

# Check for errors in logs
grep -i error pipeline_run_*.log | tail -20
```

### Need to restart
```bash
# Kill existing session
tmux kill-session -t charity-commission-pipeline

# Start fresh
./run_charity_commission_pipeline.sh
```

## Configuration

Current settings (in `azure_production_pipeline.py`):
- `MAX_CONCURRENT_FOUNDATIONS = 10` (foundations processed in parallel)
- `MAX_CONCURRENT_DOCLING = 3` (documents processed concurrently per foundation)
- `DOCLING_TIMEOUT = 300` (5 minutes per document)

Adjust these if needed based on performance.
