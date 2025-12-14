# Quarterly UKCAT Recategorization System

Automated quarterly recategorization of all funders to ensure classifications stay current with both funder activities and UKCAT standards.

## Overview

This system re-runs UKCAT classification on all funders in the database every quarter to:
- Account for changes in funder activities
- Respond to UKCAT taxonomy updates
- Maintain classification accuracy over time
- Improve matching quality

## Components

1. **quarterly_ukcat_recategorization.py** - Main recategorization script
2. **schedule_quarterly_recategorization.sh** - Cron job wrapper script
3. Progress tracking and resume capability
4. Quality comparison (before/after analysis)
5. Detailed reporting

## Usage

### Manual Execution

```bash
# Dry run (see what would change without making changes)
python3 quarterly_ukcat_recategorization.py --dry-run

# Full recategorization
python3 quarterly_ukcat_recategorization.py

# Resume from last checkpoint
python3 quarterly_ukcat_recategorization.py --resume

# Custom batch size
python3 quarterly_ukcat_recategorization.py --batch-size 500
```

### Automated Scheduling

Add to crontab for quarterly execution (runs at 2 AM on 1st day of every 3rd month):

```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed):
0 2 1 */3 * /home/azureuser/grantseeker-azure-production-1/schedule_quarterly_recategorization.sh
```

This will run on:
- January 1st at 2 AM
- April 1st at 2 AM
- July 1st at 2 AM
- October 1st at 2 AM

## Features

### Progress Tracking
- Saves progress every 100 funders
- Can resume from last checkpoint if interrupted
- Progress file: `quarterly_recategorization_progress.json`

### Quality Monitoring
- Collects before/after classification statistics
- Tracks code assignment changes
- Identifies top UKCAT codes
- Generates detailed reports

### Reporting
- Console output with progress updates
- Log file: `quarterly_recategorization_YYYYMMDD.log`
- JSON report: `quarterly_recategorization_report_YYYYMMDD_HHMMSS.json`

## Process Flow

1. **Load UKCAT Mappings** - Loads charity number to UKCAT code mappings from CSV files
2. **Collect Before Stats** - Records current classification statistics
3. **Process All Funders** - Re-classifies each funder by matching charity number with UKCAT database
4. **Update Database** - Updates funder UKCAT codes if they've changed
5. **Collect After Stats** - Records new classification statistics
6. **Generate Report** - Creates detailed before/after comparison report

## Output Example

```
🚀 Starting quarterly UKCAT recategorization...
============================================================
📊 Collecting before-classification statistics...
  Total UKCAT code assignments: 35,234
  Unique codes: 127

📊 Processing 11,286 funders...

📦 Processing batch 1 (1000 funders)...
  Batch 1 complete: 234 changed, 766 unchanged, 932 matched, 68 no match
  Overall progress: 1000/11286 (8.9%)

...

🏁 QUARTERLY UKCAT RECATEGORIZATION COMPLETE
============================================================
⏰ Total time: 12.3 minutes
📊 Total funders processed: 11,286
📊 Matched with UKCAT data: 10,526
📊 No UKCAT data available: 760
📊 Classifications changed: 1,234
📊 Classifications unchanged: 10,052
📊 Errors: 0

📈 Classification Statistics:
  Before: 35,234 total code assignments, 127 unique codes
  After: 36,123 total code assignments, 128 unique codes
  Change: +889 assignments (+2.5%)
```

## Monitoring

Check logs for:
- `quarterly_recategorization_YYYYMMDD.log` - Daily execution logs
- `logs/quarterly_recategorization_YYYYMMDD_HHMMSS.log` - Cron job logs (if using wrapper)
- `quarterly_recategorization_report_*.json` - Detailed reports

## Error Handling

- Gracefully handles funders without UKCAT data
- Continues processing on individual funder errors
- Saves progress for resume capability
- Logs all errors for investigation

## Performance

- Processes ~1,000 funders per batch
- Typical runtime: 10-15 minutes for ~11,000 funders
- Minimal database load (batched commits)
- Can be run during off-peak hours

## Maintenance

- Ensure UKCAT CSV files are up to date before running
- Review reports for significant classification changes
- Monitor logs for errors or warnings
- Clean up old log files periodically
