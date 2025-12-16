# Azure Document Intelligence Setup Guide

## 🎯 BEST OPTION: Uses Your Azure Subscription!

**Pricing:** $1.50 per 1,000 pages = **$0.0015 per page** (same as Google Cloud)

**Cost for 18,000 documents (3 per foundation):** ~$27.00
- 2 annual accounts per foundation (last 2)
- 1 articles of association per foundation

**BONUS:** Free tier includes **500 pages/month** (great for testing and small updates!)

## Why Azure Document Intelligence?

✅ **Uses your existing Azure subscription/credits**  
✅ **Same price as Google Cloud** ($18 for 12k docs)  
✅ **Free tier: 500 pages/month** included  
✅ **No external service setup** - already on Azure!  
✅ **Integrated billing** with your Azure account  

## Step-by-Step Setup

### Step 1: Create Azure Document Intelligence Resource (5 minutes)

1. **Go to Azure Portal**: https://portal.azure.com/
2. **Search for "Document Intelligence"** or "Form Recognizer"
3. **Click "Create"**
4. **Fill in details:**
   - **Subscription**: Your existing Azure subscription
   - **Resource Group**: Create new or use existing
   - **Region**: Choose closest to you (e.g., `West Europe`, `East US`)
   - **Name**: `grantseeker-document-intelligence` (or your choice)
   - **Pricing Tier**: **Free (F0)** for testing, or **Standard (S0)** for production
5. **Click "Review + Create"** then **"Create"**

### Step 2: Get Endpoint and API Key (2 minutes)

1. **Go to your resource** in Azure Portal
2. **Click "Keys and Endpoint"** in left menu
3. **Copy:**
   - **Endpoint** (looks like: `https://your-resource.cognitiveservices.azure.com/`)
   - **Key 1** (or Key 2 - both work)

### Step 3: Configure Environment Variables

Add to your `.env` file:

```bash
# Azure Document Intelligence Configuration
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-api-key-here
```

### Step 4: Install Python Library

```bash
pip install azure-ai-documentintelligence
```

### Step 5: Test Setup

```bash
python3 -c "
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import os

endpoint = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT')
key = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_KEY')

if endpoint and key:
    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    print('✅ Azure Document Intelligence client created successfully!')
    print(f'Endpoint: {endpoint}')
else:
    print('❌ Environment variables not set')
"
```

## Cost Breakdown

### One-Time Processing (18,000 documents)
- **Documents:** 3 per foundation (2 annual accounts + articles of association)
- **Total:** 6,000 foundations × 3 docs = 18,000 documents
- **Cost:** $27.00
- **Uses:** Your Azure subscription/credits

### Monthly Updates
- **Free tier:** 500 pages/month included (FREE!)
- **Additional pages:** $1.50 per 1,000 pages
- **Typical monthly cost:** $0.08 - $0.30/month (for 50-200 new docs)

### Free Tier Benefits
- **500 pages/month** included at no cost
- Perfect for testing and small updates
- Shared across all Document Intelligence resources in your subscription

## Pricing Tiers

- **Free (F0):** 500 pages/month included, then pay-as-you-go
- **Standard (S0):** Pay-as-you-go: $1.50 per 1,000 pages

For your use case (12k docs one-time, then small monthly updates), **Free (F0) tier is perfect!**

## Advantages Over Other Options

| Feature | Azure | Google Cloud | LLMOCR |
|---------|-------|--------------|--------|
| **Cost (12k docs)** | $18 | $18 | $53.88 |
| **Uses Azure credits** | ✅ Yes | ❌ No | ❌ No |
| **Free tier** | ✅ 500 pages/month | ❌ No | ❌ No |
| **Setup complexity** | ⭐ Easy | ⭐⭐ Medium | ⭐ Easy |
| **Billing integration** | ✅ Azure portal | ❌ Separate | ❌ Separate |

## Troubleshooting

### Error: "Resource not found"
- Verify `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` matches your resource endpoint
- Check resource exists in Azure Portal

### Error: "Invalid API key"
- Verify `AZURE_DOCUMENT_INTELLIGENCE_KEY` matches Key 1 or Key 2 from portal
- Keys are case-sensitive

### Error: "Quota exceeded"
- Free tier: 500 pages/month limit reached
- Upgrade to Standard (S0) tier or wait for next month

### Error: "Module not found"
- Install: `pip install azure-ai-documentintelligence`

## Next Steps

Once configured:
1. Test with a sample document
2. Run the full pipeline
3. Monitor usage in Azure Portal → Your Resource → Metrics

The pipeline will automatically use Azure Document Intelligence if configured!

## Cost Monitoring

Monitor your usage:
1. Go to Azure Portal → Your Document Intelligence Resource
2. Click **"Metrics"** → **"Document Count"**
3. Track pages processed vs free tier limit
