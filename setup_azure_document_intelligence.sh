#!/bin/bash
# Automated Azure Document Intelligence Setup Script
# This script creates the resource and configures .env automatically

set -e

echo "🚀 Azure Document Intelligence Automated Setup"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}❌ Azure CLI not found. Installing...${NC}"
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    echo -e "${GREEN}✅ Azure CLI installed${NC}"
else
    echo -e "${GREEN}✅ Azure CLI found${NC}"
fi

# Check if logged in
echo ""
echo "Checking Azure login status..."
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}⚠️  Not logged in to Azure. Please login...${NC}"
    az login
else
    echo -e "${GREEN}✅ Already logged in to Azure${NC}"
    az account show --output table
fi

# Get current subscription
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
echo ""
echo "Current subscription: $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"

# Get or create resource group
echo ""
read -p "Enter resource group name (default: grantseeker-rg): " RESOURCE_GROUP
RESOURCE_GROUP=${RESOURCE_GROUP:-grantseeker-rg}

if az group show --name $RESOURCE_GROUP &> /dev/null; then
    echo -e "${GREEN}✅ Resource group '$RESOURCE_GROUP' exists${NC}"
else
    echo "Creating resource group '$RESOURCE_GROUP'..."
    read -p "Enter region (default: westeurope): " REGION
    REGION=${REGION:-westeurope}
    az group create --name $RESOURCE_GROUP --location $REGION
    echo -e "${GREEN}✅ Resource group created${NC}"
fi

# Get region from resource group
REGION=$(az group show --name $RESOURCE_GROUP --query location -o tsv)

# Create Document Intelligence resource
echo ""
# Azure resource names can only contain letters and numbers (no hyphens)
RESOURCE_NAME="grantseekerdocintel$(date +%s | tail -c 5)"
echo "Creating Document Intelligence resource: $RESOURCE_NAME"

# Check if resource name is available
while az cognitiveservices account show --name $RESOURCE_NAME --resource-group $RESOURCE_GROUP &> /dev/null; do
    RESOURCE_NAME="grantseekerdocintel$(date +%s | tail -c 5)"
done

# Create the resource
az cognitiveservices account create \
    --name $RESOURCE_NAME \
    --resource-group $RESOURCE_GROUP \
    --kind FormRecognizer \
    --sku F0 \
    --location $REGION \
    --yes

echo -e "${GREEN}✅ Document Intelligence resource created${NC}"

# Wait a moment for resource to be ready
echo "Waiting for resource to be ready..."
sleep 10

# Get endpoint and keys
echo ""
echo "Retrieving endpoint and API key..."

ENDPOINT=$(az cognitiveservices account show \
    --name $RESOURCE_NAME \
    --resource-group $RESOURCE_GROUP \
    --query properties.endpoint -o tsv)

KEY1=$(az cognitiveservices account keys list \
    --name $RESOURCE_NAME \
    --resource-group $RESOURCE_GROUP \
    --query key1 -o tsv)

if [ -z "$ENDPOINT" ] || [ -z "$KEY1" ]; then
    echo -e "${RED}❌ Failed to retrieve endpoint or key${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Retrieved credentials${NC}"
echo ""
echo "Resource Details:"
echo "  Name: $RESOURCE_NAME"
echo "  Endpoint: $ENDPOINT"
echo "  Key: ${KEY1:0:10}...${KEY1: -4}"
echo "  Tier: F0 (Free - 500 pages/month included)"

# Update .env file
ENV_FILE="/home/azureuser/grantseeker-azure-production-1/.env"
echo ""
echo "Updating .env file..."

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file..."
    touch "$ENV_FILE"
fi

# Remove old Azure Document Intelligence entries if they exist
sed -i '/^AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=/d' "$ENV_FILE"
sed -i '/^AZURE_DOCUMENT_INTELLIGENCE_KEY=/d' "$ENV_FILE"

# Add new entries
echo "" >> "$ENV_FILE"
echo "# Azure Document Intelligence Configuration (auto-configured by setup script)" >> "$ENV_FILE"
echo "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=$ENDPOINT" >> "$ENV_FILE"
echo "AZURE_DOCUMENT_INTELLIGENCE_KEY=$KEY1" >> "$ENV_FILE"

echo -e "${GREEN}✅ .env file updated${NC}"

# Test the configuration
echo ""
echo "Testing configuration..."
python3 << EOF
import os
from dotenv import load_dotenv

load_dotenv('$ENV_FILE')

endpoint = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT')
key = os.getenv('AZURE_DOCUMENT_INTELLIGENCE_KEY')

if endpoint and key:
    print("✅ Configuration loaded successfully!")
    print(f"   Endpoint: {endpoint}")
    print(f"   Key: {key[:10]}...{key[-4:]}")
    
    # Try to create client
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        print("✅ Azure Document Intelligence client created successfully!")
    except ImportError:
        print("⚠️  azure-ai-documentintelligence not installed. Run: pip install azure-ai-documentintelligence")
    except Exception as e:
        print(f"⚠️  Error creating client: {e}")
else:
    print("❌ Configuration not found in .env file")
EOF

echo ""
echo "=============================================="
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo "=============================================="
echo ""
echo "Your Azure Document Intelligence is configured:"
echo "  • Resource: $RESOURCE_NAME"
echo "  • Resource Group: $RESOURCE_GROUP"
echo "  • Tier: F0 (Free - 500 pages/month included)"
echo "  • Cost: \$1.50 per 1,000 pages after free tier"
echo ""
echo "Expected costs for your pipeline:"
echo "  • 18,000 documents (3 per foundation): ~\$27.00"
echo "  • Monthly updates (50-200 docs): \$0.08 - \$0.30/month"
echo ""
echo "The pipeline will automatically use Azure Document Intelligence!"
echo ""
