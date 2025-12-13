import psycopg2
import os
import csv
from dotenv import load_dotenv

# Explicitly load the .env file from the correct directory
dotenv_path = os.path.join(os.path.expanduser('~'), 'grantseeker-azure-production', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME'),
    port=os.getenv('DB_PORT'),
    sslmode='require'
)

cursor = conn.cursor()

print("=" * 80)
print("📤 EXPORTING FUNDING OPPORTUNITIES TO CSV")
print("=" * 80)

# Fetch all opportunities
print("Querying database...")
cursor.execute("""
    SELECT 
        f.name as foundation_name,
        f.website,
        fo.opportunity_title,
        fo.funding_focus,
        fo.eligibility_inclusion,
        fo.eligibility_exclusion,
        fo.funding_amounts,
        fo.deadlines,
        fo.application_process,
        fo.important_urls,
        fo.created_at
    FROM funding_opportunities fo
    JOIN funders f ON fo.funder_id = f.id
    ORDER BY f.name, fo.opportunity_title
""")

rows = cursor.fetchall()
total_rows = len(rows)
print(f"Found {total_rows:,} records to export.")

# Define output filename
output_file = 'funding_opportunities_export.csv'

# Write to CSV
print(f"Writing to {output_file}...")
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    
    # Write header
    writer.writerow([
        'Foundation Name',
        'Website',
        'Opportunity Title',
        'Funding Focus',
        'Eligibility (Inclusion)',
        'Eligibility (Exclusion)',
        'Funding Amounts',
        'Deadlines',
        'Application Process',
        'Important URLs',
        'Date Captured'
    ])
    
    # Write data
    writer.writerows(rows)

# Check file size
file_size_mb = os.path.getsize(output_file) / (1024 * 1024)

print("-" * 80)
print(f"✅ Export Complete!")
print(f"📁 File: {output_file}")
print(f"📊 Size: {file_size_mb:.2f} MB")
print("-" * 80)

cursor.close()
conn.close()