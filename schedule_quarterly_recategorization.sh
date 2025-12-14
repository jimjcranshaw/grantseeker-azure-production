#!/bin/bash
#
# Quarterly UKCAT Recategorization Cron Job
# ==========================================
#
# Schedule this script to run quarterly (every 3 months)
# Add to crontab:
#   0 2 1 */3 * /path/to/schedule_quarterly_recategorization.sh
#
# This runs at 2 AM on the 1st day of every 3rd month (Jan, Apr, Jul, Oct)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/quarterly_ukcat_recategorization.py"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/quarterly_recategorization_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Run the recategorization script
cd "$SCRIPT_DIR"
python3 "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1

# Check exit status
if [ $? -eq 0 ]; then
    echo "✅ Quarterly recategorization completed successfully" >> "$LOG_FILE"
else
    echo "❌ Quarterly recategorization failed - check logs" >> "$LOG_FILE"
    # Could add email notification here
fi
