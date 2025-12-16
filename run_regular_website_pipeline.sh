#!/bin/bash
# Run Regular Website Pipeline in tmux session

SESSION_NAME="regular-website-pipeline"
SCRIPT_NAME="regular_website_pipeline.py"
LOG_DIR="$(pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/pipeline_run_${TIMESTAMP}.log"

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "⚠️  Session '$SESSION_NAME' already exists!"
    echo "Attach with: tmux attach -t $SESSION_NAME"
    echo "Or kill it first: tmux kill-session -t $SESSION_NAME"
    exit 1
fi

# Create new tmux session and run the pipeline
echo "🚀 Starting Regular Website Pipeline in tmux session: $SESSION_NAME"
echo "📝 Logging to: $LOG_FILE"
echo ""
echo "To attach: tmux attach -t $SESSION_NAME"
echo "To detach: Press Ctrl+B, then D"
echo "To kill: tmux kill-session -t $SESSION_NAME"
echo ""

tmux new-session -d -s "$SESSION_NAME" -c "$LOG_DIR" \
    "python3 $SCRIPT_NAME 2>&1 | tee $LOG_FILE"

sleep 2

# Check if session is running
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "✅ Session started successfully!"
    echo ""
    echo "Recent log output:"
    tail -20 "$LOG_FILE" 2>/dev/null || echo "(Log file not created yet)"
else
    echo "❌ Failed to start session"
    exit 1
fi
