# Cost Analysis - Azure Production Pipeline

## Executive Summary

**Monthly Cost:** $23.60 (after initial scrape)  
**Annual Cost:** $332.50  
**Savings vs Unoptimized:** 91% reduction ($3,447/year saved)

---

## Cost Components

### 1. HTTP HEAD Checks
**Cost:** FREE  
**Volume:** 5,000 requests/week  
**Purpose:** Check if website changed before scraping

### 2. Web Crawling (crawl4ai)
**Cost:** FREE  
**Volume:** 500-5,000 sites/week  
**Purpose:** Extract content from foundation websites

### 3. OpenAI Embeddings
**Cost:** $0.02 per 1M tokens  
**Volume:** ~2.5M tokens per 500 foundations  
**Weekly Cost:** $5.00 (for 500 changed foundations)  
**Purpose:** Generate vector embeddings for RAG

### 4. DeepSeek V3 GPT Analysis
**Cost:** $0.28 per 1M input tokens, $0.42 per 1M output tokens  
**Volume:** ~1M tokens per 500 foundations  
**Weekly Cost:** $0.45 (for 500 changed foundations)  
**Purpose:** Extract structured grant information

---

## Week-by-Week Breakdown

### Week 1: Initial Scrape (All 5,000 Foundations)

| Component | Volume | Unit Cost | Total |
|-----------|--------|-----------|-------|
| HTTP HEAD checks | 5,000 | FREE | $0 |
| Crawling | 5,000 sites | FREE | $0 |
| Embeddings | 25M tokens | $0.02/1M | $50.00 |
| GPT Analysis | 10M tokens | ~$0.35/1M avg | $4.55 |
| **Week 1 Total** | | | **$54.55** |

### Week 2+: Re-Scrape (10% Change Rate = 500 Foundations)

| Component | Volume | Unit Cost | Total |
|-----------|--------|-----------|-------|
| HTTP HEAD checks | 5,000 | FREE | $0 |
| Crawling | 500 sites | FREE | $0 |
| Embeddings | 2.5M tokens | $0.02/1M | $5.00 |
| GPT Analysis | 1M tokens | ~$0.35/1M avg | $0.45 |
| **Weekly Total** | | | **$5.45** |

---

## Monthly & Annual Projections

### Monthly Cost (After Initial Scrape)

- Week 2: $5.45
- Week 3: $5.45
- Week 4: $5.45
- Week 5: $5.45
- **Monthly Total: $23.60**

### Annual Cost

- Week 1 (initial): $54.55
- Weeks 2-52 (51 weeks): $5.45 × 51 = $277.95
- **Annual Total: $332.50**

---

## Cost Optimization Strategies

### 1. HTTP HEAD Change Detection (90% savings)

**Without optimization:**
- Scrape all 5,000 foundations every week
- Cost: $54.55/week = $236/month

**With optimization:**
- Check all 5,000 with HTTP HEAD (free)
- Only scrape ~500 changed (10%)
- Cost: $5.45/week = $23.60/month

**Savings:** $212.40/month (90%)

### 2. DeepSeek V3 vs OpenAI GPT-4 (95% savings)

**OpenAI GPT-4 Turbo:**
- Input: $10/1M tokens
- Output: $30/1M tokens
- Average: ~$20/1M tokens
- Cost for 500 foundations: $20

**DeepSeek V3:**
- Input: $0.28/1M tokens
- Output: $0.42/1M tokens
- Average: ~$0.35/1M tokens
- Cost for 500 foundations: $0.45

**Savings:** $19.55/week = $84.72/month (95%)

### 3. Local Document Analysis (No Web Search)

**With Tavily/web search:**
- Cost: $0.01 per search
- 5,000 foundations × $0.01 = $50/week

**Without web search (local only):**
- Cost: $0
- Use only scraped content

**Savings:** $50/week = $216.67/month

---

## Comparison: With vs Without Optimizations

| Scenario | Weekly | Monthly | Annual |
|----------|--------|---------|--------|
| **No optimizations** | $72.75 | $315.00 | $3,780 |
| **All optimizations** | $5.45 | $23.60 | $332 |
| **Savings** | $67.30 | $291.40 | $3,448 |
| **Reduction** | 92% | 92% | 91% |

---

## Change Rate Sensitivity Analysis

### If 5% of foundations change weekly:

| Component | Cost |
|-----------|------|
| Embeddings (250 foundations) | $2.50 |
| GPT Analysis (250 foundations) | $0.23 |
| **Weekly Total** | **$2.73** |
| **Monthly Total** | **$11.82** |

### If 20% of foundations change weekly:

| Component | Cost |
|-----------|------|
| Embeddings (1,000 foundations) | $10.00 |
| GPT Analysis (1,000 foundations) | $0.90 |
| **Weekly Total** | **$10.90** |
| **Monthly Total** | **$47.20** |

### If 50% of foundations change weekly:

| Component | Cost |
|-----------|------|
| Embeddings (2,500 foundations) | $25.00 |
| GPT Analysis (2,500 foundations) | $2.25 |
| **Weekly Total** | **$27.25** |
| **Monthly Total** | **$118.08** |

**Baseline assumption:** 10% change rate is conservative based on typical foundation website update frequency.

---

## Azure VM Costs (Not Included Above)

### Recommended Configuration

**Standard_D4s_v3:**
- 4 vCPUs, 16GB RAM
- Cost: ~$140/month (pay-as-you-go)
- Cost: ~$100/month (1-year reserved)
- Best for: Production with 20 workers

**Standard_D2s_v3:**
- 2 vCPUs, 8GB RAM
- Cost: ~$70/month (pay-as-you-go)
- Cost: ~$50/month (1-year reserved)
- Best for: Testing or 10 workers

### Total Monthly Cost (Including VM)

| Component | Cost |
|-----------|------|
| Pipeline (API costs) | $23.60 |
| Azure VM (D4s_v3) | $100.00 |
| Azure PostgreSQL (Basic) | $25.00 |
| **Total** | **$148.60/month** |

---

## Cost Monitoring

### Track Costs in Real-Time

```python
# Built into pipeline
print(f"Embeddings cost: ${embeddings_cost:.2f}")
print(f"GPT analysis cost: ${gpt_cost:.2f}")
print(f"Total cost: ${total_cost:.2f}")
```

### Azure Cost Management

1. Go to Azure Portal → Cost Management
2. Set up budget alerts
3. Monitor daily spending
4. Review cost by resource

### API Usage Tracking

**OpenAI:**
- Dashboard: https://platform.openai.com/usage
- Set monthly limits
- Email alerts

**DeepSeek:**
- Dashboard: https://platform.deepseek.com/usage
- Monitor token consumption
- Set budget limits

---

## Recommendations

### For Cost Optimization

1. **Start with 10% change rate assumption** - Adjust based on actual data
2. **Monitor first month closely** - Track actual change rates
3. **Use reserved VM instances** - 30% savings for 1-year commitment
4. **Set budget alerts** - Get notified if costs exceed expectations
5. **Review weekly reports** - Identify cost anomalies early

### For Performance vs Cost Trade-offs

**Option A: Faster (Higher Cost)**
- 40 workers: 1000-1200/hour
- Complete 5000 in 4-5 hours
- Higher VM cost (D8s_v3: $280/month)

**Option B: Balanced (Recommended)**
- 20 workers: 500-700/hour
- Complete 5000 in 7-10 hours
- Moderate VM cost (D4s_v3: $140/month)

**Option C: Budget (Lower Cost)**
- 10 workers: 250-350/hour
- Complete 5000 in 14-20 hours
- Lower VM cost (D2s_v3: $70/month)

---

## ROI Analysis

### Value Delivered

**Data collected:**
- 5,000 foundations analyzed
- 11 structured fields per foundation
- Updated weekly
- Searchable, queryable database

**Manual alternative:**
- 5,000 foundations × 30 min each = 2,500 hours
- At $50/hour = $125,000 in labor
- Plus ongoing updates

**Pipeline cost:**
- Initial: $54.55
- Annual: $332.50
- **ROI: 37,500% vs manual process**

---

## Conclusion

The Azure production pipeline delivers:

✅ **$23.60/month ongoing cost** (after initial scrape)  
✅ **91% cost reduction** vs unoptimized approach  
✅ **500-700 foundations/hour** throughput  
✅ **Automated weekly updates** with change detection  
✅ **Scalable to 10,000+ foundations** with minimal cost increase  

**Total Cost of Ownership (Year 1):**
- Pipeline API costs: $332
- Azure VM (D4s_v3): $1,200
- Azure PostgreSQL: $300
- **Total: $1,832/year**

**vs Manual Process: $125,000+**

**Savings: 98.5%**
