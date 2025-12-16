# Hosted OCR Service Setup Guide

## Recommended: Use a Hosted Service

Since you're on Azure VM without GPU, **hosted OCR service is the best option**:
- ✅ Cheaper than GPU VM ($60-240 vs $31-62 per run + setup)
- ✅ No infrastructure management
- ✅ Faster to get started

## Option 1: SiliconFlow (Recommended)

### Setup Steps

1. **Sign up**: https://www.siliconflow.com/
2. **Get API Key**:
   - Log in → Dashboard → API Keys
   - Click "Create API Key"
   - Copy the key

3. **Configure `.env`**:
```bash
DEEPSEEK_OCR_BASE_URL=https://api.siliconflow.com/v1  # Check their docs for exact endpoint
DEEPSEEK_OCR_API_KEY=your_siliconflow_api_key
```

4. **Check pricing**: Visit https://www.siliconflow.com/pricing for current rates

### Documentation
- Quick Start: https://docs.siliconflow.com/en/userguide/quickstart

---

## Option 2: Clarifai

### Setup Steps

1. **Sign up**: https://clarifai.com/
2. **Get Personal Access Token (PAT)**:
   - Log in → Settings → Secrets
   - Click "Create Personal Access Token"
   - Copy the token

3. **Configure `.env`**:
```bash
DEEPSEEK_OCR_BASE_URL=https://api.clarifai.com/v2  # Check their docs for exact endpoint
DEEPSEEK_OCR_API_KEY=your_clarifai_pat
```

4. **Check pricing**: Visit https://clarifai.com/pricing for current rates

### Documentation
- PAT Setup: https://docs.clarifai.com/control/authentication/pat/
- DeepSeek-OCR: https://www.clarifai.com/blog/deepseek-ocr

---

## Option 3: Other Providers

Any provider that hosts DeepSeek-OCR and provides an OpenAI-compatible API endpoint will work. Just set:
- `DEEPSEEK_OCR_BASE_URL` to their endpoint
- `DEEPSEEK_OCR_API_KEY` to their API key

---

## Testing Your Setup

Once configured, test with:

```python
from deepseek_ocr import DeepSeekOCR
import os

client = DeepSeekOCR(
    api_key=os.getenv('DEEPSEEK_OCR_API_KEY'),
    base_url=os.getenv('DEEPSEEK_OCR_BASE_URL')
)

# Test with a sample PDF
result = client.parse("test_document.pdf")
print(result)
```

---

## Cost Estimates

For 12,000 documents (2 per foundation × 6,000 foundations):

- **One-time processing**: ~$60-240 (varies by provider)
- **Monthly updates** (few changes): ~$5-20/month

**Much cheaper than Azure GPU VM** ($31-62 per run + setup complexity)

---

## Next Steps

1. Choose a provider (SiliconFlow recommended)
2. Sign up and get API key
3. Add to `.env` file
4. Test with sample document
5. Run full pipeline!
