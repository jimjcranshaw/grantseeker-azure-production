# DeepSeek OCR Setup Guide

## Overview

DeepSeek-OCR is an **open-source model** (not an API service). You have two options:

1. **Self-host** the model locally (free, requires GPU)
2. **Use a hosted service** (paid, no GPU needed)

## Option 1: Self-Host with vLLM (Recommended for Cost Savings)

### Prerequisites
- NVIDIA GPU (A100 recommended, but other GPUs work)
- CUDA 11.8+
- Python 3.10+

### Setup Steps

1. **Install vLLM and dependencies**:
```bash
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118
pip install vllm
pip install flash-attn==2.7.3 --no-build-isolation
```

2. **Start vLLM server** (OpenAI-compatible API):
```bash
python -m vllm.entrypoints.openai.api_server \
    --model deepseek-ai/DeepSeek-OCR \
    --port 8000 \
    --api-key EMPTY
```

3. **Configure environment variables**:
```bash
# In .env file:
DEEPSEEK_OCR_BASE_URL=http://localhost:8000/v1
DEEPSEEK_OCR_API_KEY=EMPTY  # Can be any dummy string for local server
```

### Benefits
- ✅ **Free** (no API costs)
- ✅ **Fast** (local processing)
- ✅ **Private** (data stays on your server)

### Drawbacks
- ❌ Requires GPU infrastructure
- ❌ More setup complexity

## Option 2: Use Hosted Service

### Available Providers

1. **SiliconFlow** (mentioned in SDK docs)
   - Sign up at their platform
   - Get API key
   - Set `DEEPSEEK_OCR_BASE_URL` to their endpoint

2. **Clarifai** (hosts DeepSeek-OCR)
   - Sign up at https://clarifai.com
   - Get Personal Access Token
   - Set `DEEPSEEK_OCR_BASE_URL` to Clarifai endpoint

3. **Other providers** that host DeepSeek-OCR

### Configuration

```bash
# In .env file:
DEEPSEEK_OCR_BASE_URL=https://api.provider.com/v1  # Provider's endpoint
DEEPSEEK_OCR_API_KEY=your_provider_api_key        # Provider's API key
```

### Benefits
- ✅ No GPU needed
- ✅ Easy setup
- ✅ Managed infrastructure

### Drawbacks
- ❌ API costs (~$0.005-$0.029 per document)
- ❌ Data sent to third party

## Current Implementation

The pipeline code supports both options:

- If `DEEPSEEK_OCR_BASE_URL` is set → uses that endpoint
- If not set → defaults to `http://localhost:8000/v1` (self-hosted)
- API key can be `EMPTY` for self-hosted, or provider's key for hosted

## Recommendation

For processing 12,000 documents:
- **Self-hosted**: ~$31-62 per run (Azure GPU VM costs) + setup complexity
- **Hosted service**: ~$60-240 one-time cost + ~$5-20/month for updates

**For Azure VMs without existing GPU access, hosted service is recommended:**
- ✅ Cheaper (no VM costs)
- ✅ Simpler (no GPU setup)
- ✅ Faster to get started
- ✅ No infrastructure management

**Self-hosting only makes sense if:**
- You already have a GPU VM running 24/7
- You're processing millions of documents regularly
- You have strict data privacy requirements
