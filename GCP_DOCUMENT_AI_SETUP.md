# Google Cloud Document AI Setup Guide

## Cost: $18 for 12,000 documents (vs $53.88 with LLMOCR)

**Pricing:** $1.50 per 1,000 pages = **$0.0015 per page**

## Step-by-Step Setup

### Step 1: Sign Up for Google Cloud (5 minutes)

1. Go to https://cloud.google.com/
2. Click "Get Started for Free"
3. Sign up with your Google account
4. **Free Trial:** $300 credit for 90 days (more than enough for your needs!)

### Step 2: Install Google Cloud SDK (5 minutes)

```bash
# Download and install Google Cloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Verify installation
gcloud --version
```

### Step 3: Create Project and Enable APIs (5 minutes)

```bash
# Login to Google Cloud
gcloud auth login

# Create a new project (or use existing)
gcloud projects create grantseeker-ocr --name="Grant Seeker OCR"

# Set as active project
gcloud config set project grantseeker-ocr

# Enable Document AI API
gcloud services enable documentai.googleapis.com

# Note your project ID (you'll need it)
PROJECT_ID=$(gcloud config get-value project)
echo "Project ID: $PROJECT_ID"
```

### Step 4: Create Document AI Processor (5 minutes)

1. **Go to Document AI Console:**
   - Visit: https://console.cloud.google.com/document-ai
   - Select your project: `grantseeker-ocr`

2. **Create Processor:**
   - Click "Create Processor"
   - Processor Type: **"OCR Processor"** (or "Form Parser" for structured docs)
   - Region: Choose **"us"** or **"eu"** (closest to you)
   - Name: `grantseeker-ocr-processor`
   - Click "Create"

3. **Copy Processor Details:**
   - After creation, note:
     - **Processor ID** (looks like: `a1b2c3d4e5f6g7h8`)
     - **Location** (us or eu)

### Step 5: Create Service Account (5 minutes)

```bash
# Set variables (replace with your values)
PROJECT_ID="grantseeker-ocr"  # Your project ID from Step 3
LOCATION="us"  # Your processor location (us or eu)

# Create service account
gcloud iam service-accounts create ocr-service \
    --display-name="OCR Service Account" \
    --project=$PROJECT_ID

# Grant Document AI permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:ocr-service@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/documentai.apiUser"

# Create and download key file
gcloud iam service-accounts keys create ~/gcp-key.json \
    --iam-account=ocr-service@${PROJECT_ID}.iam.gserviceaccount.com \
    --project=$PROJECT_ID

echo "✅ Service account key saved to: ~/gcp-key.json"
```

### Step 6: Configure Environment Variables

Add these to your `.env` file:

```bash
# Google Cloud Document AI Configuration
GOOGLE_APPLICATION_CREDENTIALS=/home/azureuser/gcp-key.json
GCP_PROJECT_ID=grantseeker-ocr
GCP_PROCESSOR_LOCATION=us
GCP_PROCESSOR_ID=your-processor-id-here
```

**Replace:**
- `grantseeker-ocr` with your actual project ID
- `us` with your processor location (us or eu)
- `your-processor-id-here` with your actual processor ID from Step 4

### Step 7: Install Python Library

```bash
pip install google-cloud-documentai
```

### Step 8: Test Setup

```bash
# Test that credentials work
python3 -c "
from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions
import os

project_id = os.getenv('GCP_PROJECT_ID')
location = os.getenv('GCP_PROCESSOR_LOCATION', 'us')
processor_id = os.getenv('GCP_PROCESSOR_ID')

print(f'Project: {project_id}')
print(f'Location: {location}')
print(f'Processor: {processor_id}')

opts = ClientOptions(api_endpoint=f'{location}-documentai.googleapis.com')
client = documentai.DocumentProcessorServiceClient(client_options=opts)
print('✅ Google Cloud Document AI client created successfully!')
"
```

## Cost Breakdown

- **12,000 documents** × $0.0015 = **$18.00**
- **Monthly updates** (50-200 docs): **$0.08 - $0.30/month**

**Total savings vs LLMOCR:** $35.88 one-time + ~$0.60/month

## Troubleshooting

### Error: "Permission denied"
- Make sure service account has `roles/documentai.apiUser` role
- Verify `GOOGLE_APPLICATION_CREDENTIALS` points to correct key file

### Error: "Processor not found"
- Check `GCP_PROCESSOR_ID` matches the processor ID from console
- Verify `GCP_PROCESSOR_LOCATION` matches processor location (us/eu)

### Error: "Project not found"
- Verify `GCP_PROJECT_ID` matches your project ID
- Run: `gcloud config get-value project`

## Next Steps

Once configured:
1. Test with a sample document
2. Run the full pipeline
3. Monitor costs in Google Cloud Console

The pipeline will automatically use Google Cloud Document AI if configured!
