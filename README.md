# Grant Foundation Scraper - Azure Production Pipeline

**Production-ready pipeline for scraping and analyzing 5000+ grant foundations with 90% cost optimization.**

---

## 🎯 Overview

This pipeline crawls foundation websites, extracts grant opportunity information using AI analysis, and stores structured data in Azure PostgreSQL. Built for scale, cost-efficiency, and production reliability.

### Key Features

✅ **HTTP HEAD Change Detection** - Only scrape changed websites (90% cost savings)  
✅ **DeepSeek V3 Integration** - 95% cheaper than OpenAI for GPT analysis  
✅ **Parallel Processing** - 500-700 foundations/hour with 20 workers  
✅ **crawl4ai Production Crawler** - Depth-3 multi-page crawling  
✅ **GPT-Researcher** - Autonomous analysis using only scraped content  
✅ **Azure PostgreSQL** - Full cloud database integration  

---

## 💰 Cost Analysis

### Production Costs

| Period | Foundations | Cost | Details |
|--------|-------------|------|---------|
| **Week 1 (Initial)** | 5,000 | $54.55 | Full scrape + analysis |
| **Week 2+ (Ongoing)** | 500 (10% change) | $5.45/week | Only changed sites |
| **Monthly (Ongoing)** | ~2,000 | **$23.60** | 90% cost reduction |
| **Annual** | ~26,000 | **$332** | vs $3,780 without optimization |

### Cost Breakdown

**Initial Scrape (Week 1):**
- HTTP HEAD checks: FREE
- Crawling: FREE
- Embeddings (OpenAI): $50
- GPT Analysis (DeepSeek): $4.55
- **Total: $54.55**

**Weekly Re-Scrape (10% change rate):**
- HTTP HEAD checks: FREE
- Crawling (500 changed): FREE
- Embeddings: $5
- GPT Analysis (DeepSeek): $0.45
- **Total: $5.45/week**

---

## 📊 Performance

| Workers | Throughput | 5000 Foundations | Use Case |
|---------|------------|------------------|----------|
| **20 (recommended)** | **500-700/hour** | **7-10 hours** | Production default |
| 40 (high-performance) | 1000-1200/hour | 4-5 hours | Large-scale operations |
| 1 (sequential) | ~30/hour | ~167 hours | Debugging |

---

## 🚀 Quick Start

### Prerequisites

- Azure VM (Ubuntu 22.04, 4 vCPUs, 16GB RAM recommended)
- Azure PostgreSQL Flexible Server
- OpenAI API key (for embeddings)
- DeepSeek API key (for GPT analysis)

### Installation

```bash
# Clone repository
git clone https://github.com/jimjcranshaw/grantseeker-azure-production.git
cd grantseeker-azure-production

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium
sudo python -m playwright install-deps

# Configure environment
cp .env.example .env
nano .env  # Add your credentials
```

### Configuration

Edit `.env` with your credentials:

```bash
# Azure PostgreSQL
DB_HOST=your-server.postgres.database.azure.com
DB_USER=your-admin-user
DB_PASSWORD=your-password
DB_NAME=postgres
DB_PORT=5432

# API Keys
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...

# Performance
MAX_CONCURRENT_FOUNDATIONS=20
TEST_MODE=True
```

### Run

```bash
# Test with 5 foundations (built-in)
python azure_production_pipeline.py

# Production run (5000 foundations)
# 1. Set TEST_MODE=False in .env
# 2. Prepare foundation_urls_5000.txt
# 3. Run:
nohup python azure_production_pipeline.py > production.log 2>&1 &
```

---

## 📁 Project Structure

```
grantseeker-azure-production/
├── README.md                      # This file
├── DEPLOYMENT.md                  # Detailed deployment guide
├── azure_production_pipeline.py   # Main pipeline script
├── requirements.txt               # Python dependencies
├── .env.example                   # Configuration template
├── .gitignore                     # Git ignore rules
└── docs/
    ├── TESTING_PLAN.md           # 7-phase testing plan
    ├── TESTING_CHECKLIST.md      # Testing checklist
    └── COST_ANALYSIS.md          # Detailed cost breakdown
```

---

## 🔧 How It Works

### 1. Change Detection (HTTP HEAD)

Before scraping each foundation, the pipeline checks if the website has changed:

```python
response = requests.head("https://foundation.org")
new_etag = response.headers.get('ETag')

if new_etag == stored_etag:
    # No change - skip scraping!
    return
else:
    # Changed - proceed with full scrape
    crawl_and_process()
```

**Result:** Only scrape ~10% of foundations each week (500 instead of 5000)

### 2. Multi-Page Crawling (crawl4ai)

Uses production-grade crawler with depth-3 traversal:

```python
crawler = WebCrawler()
result = await crawler.arun(
    url="https://foundation.org",
    max_depth=3,
    max_pages=50
)
```

**Result:** Comprehensive coverage of all grant information

### 3. AI Analysis (GPT-Researcher + DeepSeek)

Analyzes scraped content to extract structured data:

```python
researcher = GPTResearcher(
    query="Extract grant opportunities",
    report_source="langchain_documents",  # Local only
    llm_provider="openai",
    llm_base_url="https://api.deepseek.com"  # DeepSeek API
)
```

**Result:** 95% cheaper than OpenAI GPT-4

### 4. Data Storage (Azure PostgreSQL)

Stores 11 structured fields per foundation:

- Foundation name, URL, location
- Grant types, focus areas, eligibility
- Application process, deadlines
- Contact information
- Last updated timestamp

---

## 📋 Extracted Fields

| Field | Description | Example |
|-------|-------------|---------|
| `foundation_name` | Official name | "Gates Foundation" |
| `foundation_url` | Website URL | "https://gatesfoundation.org" |
| `grant_types` | Types of grants offered | "Project grants, Operating support" |
| `focus_areas` | Program areas | "Global health, Education" |
| `geographic_focus` | Geographic restrictions | "Global, US-based organizations" |
| `eligibility_criteria` | Who can apply | "501(c)(3) nonprofits" |
| `application_process` | How to apply | "Online application portal" |
| `deadlines` | Application deadlines | "Rolling, Quarterly" |
| `funding_range` | Grant amounts | "$50K - $5M" |
| `contact_info` | Contact details | "grants@foundation.org" |
| `last_updated` | Scrape timestamp | "2024-12-06 10:30:00" |

---

## 🧪 Testing

See `docs/TESTING_PLAN.md` for comprehensive 7-phase testing guide:

1. **Environment Setup** - Verify all dependencies
2. **Database Connection** - Test Azure PostgreSQL
3. **API Integration** - Validate OpenAI and DeepSeek
4. **Single Foundation** - End-to-end test
5. **Parallel Processing** - Benchmark throughput
6. **Change Detection** - Verify cost optimization
7. **Production Readiness** - Final validation

**Quick Test:**

```bash
# Run with 5 test foundations
python azure_production_pipeline.py

# Expected: 5-10 minutes, $0.05 cost
```

---

## 📈 Monitoring

```bash
# Check process status
ps aux | grep python

# View logs
tail -f production.log

# Database query
psql -h your-server.postgres.database.azure.com -U your-user -d postgres
SELECT COUNT(*) FROM foundations WHERE last_updated > NOW() - INTERVAL '1 day';
```

---

## 🔒 Security

- **Never commit `.env`** - Contains sensitive credentials
- **Use Azure Key Vault** - For production secrets (recommended)
- **Firewall rules** - Restrict PostgreSQL access to VM IP
- **SSL/TLS** - All database connections encrypted

---

## 🐛 Troubleshooting

### Database Connection Issues

```bash
# Test connection
psql -h your-server.postgres.database.azure.com -U your-user -d postgres

# Check Azure firewall rules
# Add your VM's IP in Azure Portal
```

### Playwright Issues

```bash
# Reinstall browsers
python -m playwright install chromium
sudo python -m playwright install-deps
```

### Memory Issues

```bash
# Check memory
free -h

# Reduce workers
# Edit .env: MAX_CONCURRENT_FOUNDATIONS=10
```

---

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment guide
- **[docs/TESTING_PLAN.md](docs/TESTING_PLAN.md)** - Testing procedures
- **[docs/COST_ANALYSIS.md](docs/COST_ANALYSIS.md)** - Detailed cost breakdown

---

## 🤝 Contributing

This is a production pipeline. For issues or improvements:

1. Create an issue describing the problem
2. Fork the repository
3. Create a feature branch
4. Submit a pull request

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🙋 Support

For questions or issues:
- GitHub Issues: https://github.com/jimjcranshaw/grantseeker-azure-production/issues
- Documentation: See `docs/` folder

---

**Built for production. Optimized for cost. Ready to scale.**
