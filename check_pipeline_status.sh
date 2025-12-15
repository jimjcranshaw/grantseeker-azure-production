#!/bin/bash
# Check status of Charity Commission pipeline

SESSION_NAME="charity-commission-pipeline"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "="*70
echo "CHARITY COMMISSION PIPELINE STATUS"
echo "="*70
echo ""

# Check if session exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "✅ Session '$SESSION_NAME' is running"
    echo ""
    
    # Get session info
    tmux list-sessions | grep "$SESSION_NAME"
    echo ""
    
    # Find latest log file
    LATEST_LOG=$(ls -t "$SCRIPT_DIR"/pipeline_run_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "Latest log file: $LATEST_LOG"
        echo ""
        echo "Recent progress updates:"
        grep -E "(📊 Progress|PIPELINE SUMMARY|Completed|Skipped|Failed|Rate|ETA)" "$LATEST_LOG" | tail -10
        echo ""
        echo "Last 5 lines:"
        tail -5 "$LATEST_LOG"
    else
        echo "No log file found yet"
    fi
    
    echo ""
    echo "To attach: tmux attach -t $SESSION_NAME"
else
    echo "❌ Session '$SESSION_NAME' is not running"
    echo ""
    
    # Check for recent log files
    LATEST_LOG=$(ls -t "$SCRIPT_DIR"/pipeline_run_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "Latest log file: $LATEST_LOG"
        echo ""
        echo "Final summary:"
        grep -A 20 "PIPELINE SUMMARY" "$LATEST_LOG" | tail -20
    fi
fi

echo ""
echo "="*70
