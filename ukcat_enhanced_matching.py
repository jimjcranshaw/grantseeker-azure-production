#!/usr/bin/env python3
"""
Enhanced UKCAT Matching Algorithm
=================================

This implements the enhanced matching algorithm that uses UKCAT classification overlap
to find better funder recommendations based on structured classification rather than
content similarity.

Usage:
    python ukcat_enhanced_matching.py --charity-number "123456" --top-n 10

Author: Grant Seeker UKCAT Integration
Date: December 2025
"""

import os
import psycopg2
import json
import argparse
from typing import List, Dict, Set, Tuple
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UKCATEnhancedMatcher:
    """Enhanced matching using UKCAT classification overlap."""
    
    def __init__(self, db_connection):
        self.conn = db_connection
        self.cursor = db_connection.cursor()
        
    def get_user_ukcat_codes(self, charity_number: str) -> List[str]:
        """Get UKCAT codes for a user charity (mock implementation)."""
        
        # In production, this would query UKCAT database for the charity
        # For now, we'll use mock data or get from user input
        try:
            # Try to find existing charity data
            self.cursor.execute("""
                SELECT ukcat_codes 
                FROM funders 
                WHERE charity_number = %s
                LIMIT 1
            """, (charity_number,))
            
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0] if isinstance(result[0], list) else json.loads(result[0])
            
            logger.warning(f"No UKCAT codes found for charity number {charity_number}")
            return []
            
        except Exception as e:
            logger.error(f"Error fetching UKCAT codes for charity {charity_number}: {e}")
            return []
    
    def find_matching_funders(self, user_codes: List[str], top_n: int = 10) -> List[Dict]:
        """Find funders matching user's UKCAT codes using overlap scoring."""
        
        if not user_codes:
            logger.warning("No user UKCAT codes provided")
            return []
        
        try:
            # Query funders with matching UKCAT codes using JSONB overlap
            # First, get all funders with UKCAT codes
            self.cursor.execute("""
                SELECT 
                    f.id,
                    f.name,
                    f.website,
                    f.charity_number,
                    f.ukcat_codes,
                    jsonb_array_length(f.ukcat_codes) as total_codes
                FROM funders f
                WHERE f.ukcat_codes IS NOT NULL 
                AND jsonb_array_length(f.ukcat_codes) > 0
            """)
            
            all_funders = self.cursor.fetchall()
            
            # Filter and score manually
            matching_funders = []
            for row in all_funders:
                funder_id, name, website, charity_num, codes, total_codes = row
                
                # Calculate overlap manually
                user_codes_set = set(user_codes)
                funder_codes_set = set(codes) if isinstance(codes, list) else set()
                overlap_count = len(user_codes_set & funder_codes_set)
                
                # Only include funders with at least one overlapping code
                if overlap_count > 0:
                    # Calculate match score (overlap + precision factor)
                    precision_factor = overlap_count / max(total_codes, 1)
                    match_score = overlap_count + (precision_factor * 0.5)
                    
                    funder_data = {
                        'id': funder_id,
                        'name': name,
                        'website': website,
                        'charity_number': charity_num,
                        'ukcat_codes': codes,
                        'overlap_count': overlap_count,
                        'total_codes': total_codes,
                        'match_score': round(match_score, 2),
                        'match_percentage': round((overlap_count / len(user_codes)) * 100, 1) if user_codes else 0
                    }
                    
                    matching_funders.append(funder_data)
            
            # Sort by match score and limit results
            matching_funders.sort(key=lambda x: (x['overlap_count'], -x['total_codes']), reverse=True)
            matching_funders = matching_funders[:top_n]
            
            results = self.cursor.fetchall()
            
            logger.info(f"Found {len(matching_funders)} matching funders")
            return matching_funders
            
        except Exception as e:
            logger.error(f"Error finding matching funders: {e}")
            return []
    
    def get_classification_details(self, codes: List[str]) -> Dict[str, str]:
        """Get human-readable descriptions for UKCAT codes."""
        
        if not codes:
            return {}
        
        try:
            placeholders = ','.join(['%s'] * len(codes))
            self.cursor.execute(f"""
                SELECT code, tag, category
                FROM ukcat_codes 
                WHERE code IN ({placeholders})
            """, codes)
            
            results = self.cursor.fetchall()
            return {code: f"{tag} ({category})" for code, tag, category in results}
            
        except Exception as e:
            logger.error(f"Error fetching classification details: {e}")
            return {}
    
    def display_matches(self, matches: List[Dict], user_codes: List[str]):
        """Display matching results in a formatted way."""
        
        if not matches:
            print("❌ No matching funders found")
            return
        
        # Get classification descriptions
        all_codes = set(user_codes)
        for match in matches:
            all_codes.update(match['ukcat_codes'])
        
        code_descriptions = self.get_classification_details(list(all_codes))
        
        print("\n🎯 ENHANCED UKCAT MATCHING RESULTS")
        print("=" * 50)
        print(f"User UKCAT codes: {', '.join(user_codes)}")
        if user_codes:
            user_descriptions = [code_descriptions.get(code, code) for code in user_codes]
            print(f"User focus: {', '.join(user_descriptions)}")
        print()
        
        print(f"📊 Found {len(matches)} matching funders:\n")
        
        for i, match in enumerate(matches, 1):
            print(f"{i}. {match['name']}")
            print(f"   📈 Match Score: {match['match_score']}")
            print(f"   🎯 Code Overlap: {match['overlap_count']}/{len(user_codes)} codes ({match['match_percentage']}%)")
            print(f"   🏷️  Codes: {', '.join(match['ukcat_codes'])}")
            
            # Show overlapping codes specifically
            overlapping_codes = set(match['ukcat_codes']) & set(user_codes)
            if overlapping_codes:
                overlap_descriptions = [code_descriptions.get(code, code) for code in overlapping_codes]
                print(f"   ✅ Overlap: {', '.join(overlap_descriptions)}")
            
            # Show website status
            website_status = "✅ Has website" if match['website'] else "❌ No website"
            print(f"   🌐 {website_status}")
            
            if match['website']:
                print(f"   🔗 Website: {match['website']}")
            
            print()

def main():
    """Main function for enhanced UKCAT matching."""
    
    parser = argparse.ArgumentParser(description='Enhanced UKCAT matching for funders')
    parser.add_argument('--charity-number', type=str, help='Charity number to find matches for')
    parser.add_argument('--user-codes', type=str, help='Comma-separated UKCAT codes (e.g., "ED,BE102")')
    parser.add_argument('--top-n', type=int, default=10, help='Number of top matches to return')
    parser.add_argument('--demo', action='store_true', help='Run with demo data')
    
    args = parser.parse_args()
    
    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return
    
    conn = psycopg2.connect(db_url)
    
    try:
        matcher = UKCATEnhancedMatcher(conn)
        
        # Get user codes
        user_codes = []
        
        if args.demo:
            # Demo with known codes
            user_codes = ['ED', 'BE102']  # Education + Children
            print("🎭 Running demo with Education + Children codes")
            
        elif args.user_codes:
            user_codes = [code.strip().upper() for code in args.user_codes.split(',')]
            
        elif args.charity_number:
            user_codes = matcher.get_user_ukcat_codes(args.charity_number)
            if user_codes:
                print(f"📥 Loaded {len(user_codes)} UKCAT codes for charity {args.charity_number}")
            else:
                print(f"⚠️ No UKCAT codes found for charity {args.charity_number}")
                print("💡 Try using --user-codes instead")
                return
        else:
            print("❌ Please provide --user-codes, --charity-number, or --demo")
            return
        
        if not user_codes:
            print("❌ No user codes available for matching")
            return
        
        # Find matches
        print(f"🔍 Searching for funders matching: {', '.join(user_codes)}")
        matches = matcher.find_matching_funders(user_codes, args.top_n)
        
        # Display results
        matcher.display_matches(matches, user_codes)
        
        if matches:
            print("✅ Enhanced UKCAT matching completed successfully!")
            print("🎯 These matches are based on structured classification overlap,")
            print("   providing more accurate and reliable recommendations.")
        else:
            print("❌ No matches found - try different UKCAT codes")
        
    except Exception as e:
        logger.error(f"❌ Enhanced matching failed: {e}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()