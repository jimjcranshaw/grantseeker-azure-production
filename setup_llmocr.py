#!/usr/bin/env python3
"""
LLMOCR Setup Helper Script

This script helps you:
1. Test your LLMOCR API key
2. Process a sample document
3. Verify the integration works
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def test_llmocr_api():
    """Test LLMOCR API connection."""
    api_key = os.getenv('LLMOCR_API_KEY')
    
    if not api_key:
        print("❌ LLMOCR_API_KEY not found in .env file")
        print("\n📝 To get your API key:")
        print("1. Sign up at https://llmocr.com/")
        print("2. Go to Dashboard → API Keys")
        print("3. Copy your API key")
        print("4. Add to .env: LLMOCR_API_KEY=your_key_here")
        return False
    
    print(f"✅ Found API key: {api_key[:10]}...")
    
    # Test with a simple request (you'll need to provide a test image/PDF)
    print("\n📋 To test OCR processing, provide a test file:")
    print("   python setup_llmocr.py test /path/to/test.pdf")
    
    return True

def process_document(file_path: str):
    """Process a document using LLMOCR API."""
    api_key = os.getenv('LLMOCR_API_KEY')
    
    if not api_key:
        print("❌ LLMOCR_API_KEY not found in .env file")
        return None
    
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return None
    
    # Determine endpoint based on file type
    if file_path.suffix.lower() == '.pdf':
        endpoint = 'https://llmocr.com/api/pdf-to-markdown'
    else:
        endpoint = 'https://llmocr.com/api/image-to-markdown'
    
    print(f"📄 Processing: {file_path.name}")
    print(f"🔗 Endpoint: {endpoint}")
    
    # Read file
    with open(file_path, 'rb') as f:
        file_content = f.read()
    
    # Convert to base64
    import base64
    file_base64 = base64.b64encode(file_content).decode('utf-8')
    
    # Prepare request
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'image_base64': file_base64,
        'mime_type': 'application/pdf' if file_path.suffix.lower() == '.pdf' else 'image/png'
    }
    
    try:
        print("⏳ Sending request to LLMOCR...")
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success!")
            print(f"\n📝 Extracted text (first 500 chars):")
            print(result.get('text', result.get('markdown', ''))[:500])
            return result
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        if len(sys.argv) > 2:
            process_document(sys.argv[2])
        else:
            print("Usage: python setup_llmocr.py test /path/to/file.pdf")
    else:
        test_llmocr_api()
