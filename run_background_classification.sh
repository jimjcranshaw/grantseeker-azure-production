#!/bin/bash
# Background UKCAT Classification Runner
# This script runs in tmux and processes all remaining funders

echo "🚀 Starting background UKCAT classification..."
echo "📅 Started at: $(date)"
echo "📊 Current progress will be shown as we go..."

# Change to the project directory
cd /home/azureuser/grantseeker-azure-production-1

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

# Run the classification in batches until done
python3 assign_ukcat_codes_to_funders.py --batch-size 1000

echo "✅ Classification complete or interrupted"
echo "📅 Finished at: $(date)"