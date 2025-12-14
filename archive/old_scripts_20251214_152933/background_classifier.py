#!/usr/bin/env python3
"""
Simple Background UKCAT Classifier
=================================

This runs continuously to classify all remaining funders.
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

# Load environment
load_dotenv()

# Set DATABASE_URL from individual components if not set
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}?"
        f"sslmode={os.getenv('DB_SSLMODE', 'require')}"
    )

print("🚀 Starting background UKCAT classification...")
print(f"📅 Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🔗 Database: {os.getenv('DB_HOST')}")
print("=" * 60)

# Import and run the classifier
from assign_ukcat_codes_to_funders import main as run_classification

if __name__ == "__main__":
    try:
        run_classification()
    except KeyboardInterrupt:
        print("\n🛑 Classification interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print(f"📅 Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")