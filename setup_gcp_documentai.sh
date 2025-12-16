#!/bin/bash
# Google Cloud Document AI Setup Script
# This script automates the GCP setup process

set -e

echo "🚀 Google Cloud Document AI Setup"
echo "=================================="
echo ""

# Step 1: Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Google Cloud SDK not found. Installing..."
    curl https://sdk.cloud.google.com | bash
    exec -l $SHELL
    echo "✅ Google Cloud SDK installed"
else
    echo "✅ Google Cloud SDK found"
fi

# Step 2: Login
echo ""
echo "📋 Please login to Google Cloud..."
gcloud auth login

# Step 3: Create project
echo ""
read -p "Enter project name (default: grantseeker-ocr): " PROJECT_NAME
PROJECT_NAME=${PROJECT_NAME:-grantseeker-ocr}

echo "Creating project: $PROJECT_NAME"
gcloud projects create $PROJECT_NAME --name="Grant Seeker OCR" 2>/dev/null || echo "Project may already exist"

gcloud config set project $PROJECT_NAME
PROJECT_ID=$(gcloud config get-value project)
echo "✅ Project ID: $PROJECT_ID"

# Step 4: Enable APIs
echo ""
echo "Enabling Document AI API..."
gcloud services enable documentai.googleapis.com --project=$PROJECT_ID
echo "✅ Document AI API enabled"

# Step 5: Create service account
echo ""
echo "Creating service account..."
gcloud iam service-accounts create ocr-service \
    --display-name="OCR Service Account" \
    --project=$PROJECT_ID 2>/dev/null || echo "Service account may already exist"

# Step 6: Grant permissions
echo ""
echo "Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:ocr-service@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/documentai.apiUser" \
    --quiet

# Step 7: Create key file
echo ""
echo "Creating service account key..."
KEY_FILE="$HOME/gcp-key.json"
gcloud iam service-accounts keys create $KEY_FILE \
    --iam-account=ocr-service@${PROJECT_ID}.iam.gserviceaccount.com \
    --project=$PROJECT_ID

echo "✅ Service account key saved to: $KEY_FILE"

# Step 8: Get processor info
echo ""
echo "=================================="
echo "📋 Next Steps:"
echo "=================================="
echo ""
echo "1. Go to: https://console.cloud.google.com/document-ai"
echo "2. Select project: $PROJECT_ID"
echo "3. Click 'Create Processor'"
echo "4. Choose 'OCR Processor'"
echo "5. Choose location (us or eu)"
echo "6. Copy the Processor ID"
echo ""
echo "Then add to your .env file:"
echo ""
echo "GOOGLE_APPLICATION_CREDENTIALS=$KEY_FILE"
echo "GCP_PROJECT_ID=$PROJECT_ID"
echo "GCP_PROCESSOR_LOCATION=us  # or 'eu'"
echo "GCP_PROCESSOR_ID=your-processor-id-here"
echo ""
echo "✅ Setup script complete!"
