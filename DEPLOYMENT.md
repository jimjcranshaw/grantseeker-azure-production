# Azure Production Deployment Guide

## Quick Start

### 1. Create Azure VM

**Recommended Specs:**
- Size: Standard_D4s_v3 (4 vCPUs, 16GB RAM)
- OS: Ubuntu 22.04 LTS
- Disk: 128GB Standard SSD
- Region: Same as PostgreSQL server

### 2. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install system dependencies
sudo apt install -y git curl wget

# Clone repository
git clone https://github.com/jimjcranshaw/grantseeker-rag-pipeline.git
cd grantseeker-rag-pipeline
git checkout feature/azure-production-pipeline

# Navigate to production folder
cd azure_production

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium
sudo python -m playwright install-deps
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

Update these values:
- `DB_HOST`: Your Azure PostgreSQL hostname
- `DB_USER`: Your database username
- `DB_PASSWORD`: Your database password
- `OPENAI_API_KEY`: Your OpenAI API key
- `DEEPSEEK_API_KEY`: Your DeepSeek API key

### 4. Test the Pipeline

```bash
# Run with 5 test foundations (built-in)
python azure_production_final.py
```

Expected output:
- Duration: ~5-10 minutes
- Foundations processed: 5/5
- Cost: ~$0.05

### 5. Production Run

```bash
# Prepare your foundation URLs file
# Format: Foundation Name,URL
# Example: Gates Foundation,https://www.gatesfoundation.org

# Edit script to disable test mode
nano azure_production_final.py
# Change: TEST_MODE = False

# Run production pipeline
nohup python azure_production_final.py > production.log 2>&1 &

# Monitor progress
tail -f production.log
```

## Performance Expectations

| Workers | Throughput | 5000 Foundations | Cost (Week 1) |
|---------|------------|------------------|---------------|
| 20 (default) | 500-700/hour | 7-10 hours | $54.55 |
| 40 (high-perf) | 1000-1200/hour | 4-5 hours | $54.55 |

## Monitoring

```bash
# Check process status
ps aux | grep python

# View logs
tail -f production.log

# Check database
psql -h your-server.postgres.database.azure.com -U your-user -d postgres
```

## Troubleshooting

### Database Connection Issues
```bash
# Test PostgreSQL connection
psql -h your-server.postgres.database.azure.com -U your-user -d postgres

# Check firewall rules in Azure Portal
# Add your VM's IP to allowed list
```

### Playwright Issues
```bash
# Reinstall browsers
python -m playwright install chromium
sudo python -m playwright install-deps
```

### Memory Issues
```bash
# Check memory usage
free -h

# Reduce concurrent workers if needed
# Edit: MAX_CONCURRENT_FOUNDATIONS = 10
```

## Cost Optimization

**Week 1 (Initial):** $54.55
**Week 2+ (10% change):** $5.45/week = $23.60/month

The pipeline automatically:
- Checks for changes before scraping (HTTP HEAD)
- Only processes changed foundations
- Uses DeepSeek V3 (95% cheaper than OpenAI)
- Generates embeddings only for new content

## Support

For issues or questions:
1. Check the testing documentation in `docs/testing/`
2. Review the main README in this folder
3. Check GitHub issues

## Next Steps

After successful testing:
1. Set up scheduled runs (cron)
2. Configure monitoring/alerting
3. Set up automated backups
4. Review cost reports weekly
