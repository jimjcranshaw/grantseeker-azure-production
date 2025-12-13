import psycopg2
import os
import json
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
print("🔍 CHECKING FUNDING OPPORTUNITIES DATA")
print("=" * 80)

# Get total count
cursor.execute("SELECT COUNT(*) FROM funding_opportunities")
count = cursor.fetchone()[0]
print(f"Total Opportunities Found: {count:,}")
print("-" * 80)

# Fetch the most recent 3 opportunities with their detailed columns
cursor.execute("""
    SELECT 
        f.name as foundation_name,
        fo.opportunity_title,
        fo.funding_focus,
        fo.eligibility_inclusion,
        fo.application_process,
        fo.created_at
    FROM funding_opportunities fo
    JOIN funders f ON fo.funder_id = f.id
    ORDER BY fo.created_at DESC
    LIMIT 3
""")

opportunities = cursor.fetchall()

for i, opp in enumerate(opportunities, 1):
    funder, title, focus, eligibility, process, created = opp
    
    print(f"\n📄 Opportunity #{i}")
    print(f"  🏛️  Foundation:  {funder}")
    print(f"  🏷️  Title:       {title}")
    print(f"  🎯 Focus:       {str(focus)[:100]}..." if focus else "  🎯 Focus:       (empty)")
    print(f"  ✅ Eligibility: {str(eligibility)[:100]}..." if eligibility else "  ✅ Eligibility: (empty)")
    print(f"  📝 Process:     {str(process)[:100]}..." if process else "  📝 Process:     (empty)")
    print(f"  🕒 Captured:    {created}")
    print("-" * 50)

cursor.close()
conn.close()