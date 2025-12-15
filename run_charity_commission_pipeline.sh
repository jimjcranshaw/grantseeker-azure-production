#!/bin/bash
# Run Charity Commission pipeline in tmux session

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SESSION_NAME="charity-commission-pipeline"
LOG_FILE="pipeline_run_$(date +%Y%m%d_%H%M%S).log"

echo "Starting Charity Commission pipeline in tmux session: $SESSION_NAME"
echo "Log file: $LOG_FILE"
echo ""

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "⚠️  Session '$SESSION_NAME' already exists!"
    echo "Attach with: tmux attach -t $SESSION_NAME"
    echo "Or kill it first with: tmux kill-session -t $SESSION_NAME"
    exit 1
fi

# Create new tmux session and run pipeline
tmux new-session -d -s "$SESSION_NAME" -x 120 -y 40

# Send command to run pipeline with logging
tmux send-keys -t "$SESSION_NAME" "cd '$SCRIPT_DIR' && python3 azure_production_pipeline.py 2>&1 | tee '$LOG_FILE'" C-m

echo "✅ Pipeline started in tmux session: $SESSION_NAME"
echo ""
echo "Useful commands:"
echo "  Attach to session:    tmux attach -t $SESSION_NAME"
echo "  Detach from session:  Press Ctrl+B then D"
echo "  View logs:            tail -f $LOG_FILE"
echo "  Kill session:         tmux kill-session -t $SESSION_NAME"
echo ""
echo "Session will continue running even if you disconnect!"
