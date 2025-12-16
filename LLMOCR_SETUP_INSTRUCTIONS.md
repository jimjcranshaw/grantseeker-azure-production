# LLMOCR Setup Instructions

## Quick Setup (5 minutes)

### Step 1: Sign Up
1. Go to https://llmocr.com/
2. Click "Sign Up" or "Get Started"
3. Create an account (email + password)

### Step 2: Get API Key
1. Log in to your account
2. Go to **Dashboard** → **API Keys**
3. Click **"Create API Key"** or copy existing key
4. Copy the key (it looks like: `sk-xxxxxxxxxxxxx`)

### Step 3: Add to .env File
```bash
# Add this line to your .env file
LLMOCR_API_KEY=sk-your-actual-api-key-here
```

### Step 4: Test Connection
```bash
# Test with a sample PDF
python setup_llmocr.py test /path/to/test.pdf
```

## Pricing

- **$4.49 per 1,000 credits** = **$0.00449 per document**
- **12,000 documents** = **$53.88** (well under your $60 budget!)

## API Endpoints

LLMOCR provides:
- **PDF to Markdown**: `https://llmocr.com/api/pdf-to-markdown`
- **Image to Markdown**: `https://llmocr.com/api/image-to-markdown`

The pipeline automatically uses the correct endpoint based on file type.

## Rate Limits

Check LLMOCR documentation for current rate limits. The pipeline includes:
- Rate limiting (0.6s delay between requests)
- Retry logic (2 retries on failure)
- Timeout protection (60 seconds per document)

## Support

- Documentation: https://llmocr.com/en/api-docs
- Support: Contact through their website

## Next Steps

Once you have the API key:
1. Add to `.env` file
2. Test with `setup_llmocr.py`
3. Run the full pipeline!

The pipeline will automatically use LLMOCR if `LLMOCR_API_KEY` is set.
