#!/usr/bin/env python3
"""
Enhanced UKCAT Export System
=============================

This creates comprehensive exports with UKCAT classifications, providing structured
classification data for analysis, reporting, and external integration.

Usage:
    python enhanced_ukcat_exports.py --export-all
    python enhanced_ukcat_exports.py --export-classified
    python enhanced_ukcat_exports.py --export-matching

Author: Grant Seeker UKCAT Integration
Date: December 2025
"""

import os
import csv
import json
import argparse
from typing import List, Dict
from dotenv import load_dotenv
import psycopg2
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UKCATExporter:
    """Enhanced export system for UKCAT classified funders."""
    
    def __init__(self, db_connection):
        self.conn = db_connection
        self.cursor = db_connection.cursor()
        
    def get_classification_details(self) -> Dict[str, Dict]:
        """Get all UKCAT code descriptions and metadata."""
        self.cursor.execute("""
            SELECT code, tag, category, subcategory, level, notes
            FROM ukcat_codes 
            ORDER BY code
        """)
        
        results = self.cursor.fetchall()
        return {
            code: {
                'tag': tag,
                'category': category,
                'subcategory': subcategory,
                'level': level,
                'notes': notes
            }
            for code, tag, category, subcategory, level, notes in results
        }
    
    def get_funders_with_ukcat_classifications(self, include_opportunities: bool = False) -> List[Dict]:
        """Get all funders with their UKCAT classifications."""
        
        if include_opportunities:
            query = """
                SELECT 
                    f.id,
                    f.name,
                    f.website,
                    f.charity_number,
                    f.ukcat_codes,
                    f.classification_type,
                    f.assessment_notes,
                    COUNT(o.id) as opportunity_count,
                    string_agg(DISTINCT o.opportunity_title, '; ') as opportunity_titles
                FROM funders f
                LEFT JOIN funding_opportunities o ON f.id = o.funder_id
                WHERE f.ukcat_codes IS NOT NULL AND jsonb_array_length(f.ukcat_codes) > 0
                GROUP BY f.id, f.name, f.website, f.charity_number, f.ukcat_codes, 
                         f.classification_type, f.assessment_notes
                ORDER BY f.name
            """
        else:
            query = """
                SELECT 
                    f.id,
                    f.name,
                    f.website,
                    f.charity_number,
                    f.ukcat_codes,
                    f.classification_type,
                    f.assessment_notes
                FROM funders f
                WHERE f.ukcat_codes IS NOT NULL AND jsonb_array_length(f.ukcat_codes) > 0
                ORDER BY f.name
            """
        
        self.cursor.execute(query)
        results = self.cursor.fetchall()
        
        funders = []
        for row in results:
            if include_opportunities:
                funder_id, name, website, charity_num, codes, classification_type, notes, opp_count, opp_titles = row
                funders.append({
                    'id': funder_id,
                    'name': name,
                    'website': website,
                    'charity_number': charity_num,
                    'ukcat_codes': codes,
                    'classification_type': classification_type,
                    'assessment_notes': notes,
                    'opportunity_count': opp_count,
                    'opportunity_titles': opp_titles
                })
            else:
                funder_id, name, website, charity_num, codes, classification_type, notes = row
                funders.append({
                    'id': funder_id,
                    'name': name,
                    'website': website,
                    'charity_number': charity_num,
                    'ukcat_codes': codes,
                    'classification_type': classification_type,
                    'assessment_notes': notes
                })
        
        return funders
    
    def export_funders_csv(self, filename: str, include_opportunities: bool = False):
        """Export funders with UKCAT classifications to CSV."""
        
        funders = self.get_funders_with_ukcat_classifications(include_opportunities)
        classification_details = self.get_classification_details()
        
        logger.info(f"Exporting {len(funders)} classified funders to {filename}")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            if include_opportunities:
                fieldnames = [
                    'id', 'name', 'website', 'charity_number', 'ukcat_codes', 
                    'ukcat_descriptions', 'classification_type', 'assessment_notes',
                    'opportunity_count', 'opportunity_titles'
                ]
            else:
                fieldnames = [
                    'id', 'name', 'website', 'charity_number', 'ukcat_codes', 
                    'ukcat_descriptions', 'classification_type', 'assessment_notes'
                ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for funder in funders:
                # Get human-readable descriptions for UKCAT codes
                code_descriptions = []
                for code in funder['ukcat_codes']:
                    if code in classification_details:
                        details = classification_details[code]
                        description = f"{details['tag']} ({details['category']})"
                        if details['subcategory']:
                            description += f" - {details['subcategory']}"
                        code_descriptions.append(description)
                
                row = {
                    'id': funder['id'],
                    'name': funder['name'],
                    'website': funder['website'] or '',
                    'charity_number': funder['charity_number'] or '',
                    'ukcat_codes': ', '.join(funder['ukcat_codes']),
                    'ukcat_descriptions': '; '.join(code_descriptions),
                    'classification_type': funder['classification_type'] or '',
                    'assessment_notes': funder['assessment_notes'] or ''
                }
                
                if include_opportunities:
                    row['opportunity_count'] = funder.get('opportunity_count', 0)
                    row['opportunity_titles'] = funder.get('opportunity_titles', '') or ''
                
                writer.writerow(row)
        
        logger.info(f"✅ CSV export completed: {filename}")
    
    def export_ukcat_summary_csv(self, filename: str):
        """Export summary of UKCAT classifications by category."""
        
        query = """
            SELECT 
                f.id,
                f.ukcat_codes,
                f.name,
                f.website,
                f.charity_number
            FROM funders f
            WHERE f.ukcat_codes IS NOT NULL AND jsonb_array_length(f.ukcat_codes) > 0
            ORDER BY f.name
        """
        
        self.cursor.execute(query)
        results = self.cursor.fetchall()
        
        classification_details = self.get_classification_details()
        
        # Flatten to one row per UKCAT code assignment
        assignments = []
        for funder_id, codes, name, website, charity_num in results:
            for code in codes:
                if code in classification_details:
                    details = classification_details[code]
                    assignments.append({
                        'funder_id': funder_id,
                        'funder_name': name,
                        'website': website or '',
                        'charity_number': charity_num or '',
                        'ukcat_code': code,
                        'tag': details['tag'],
                        'category': details['category'],
                        'subcategory': details['subcategory'] or '',
                        'level': details['level'],
                        'notes': details['notes'] or ''
                    })
        
        logger.info(f"Exporting {len(assignments)} code assignments to {filename}")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'funder_id', 'funder_name', 'website', 'charity_number',
                'ukcat_code', 'tag', 'category', 'subcategory', 
                'level', 'notes'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for assignment in assignments:
                writer.writerow(assignment)
        
        logger.info(f"✅ UKCAT summary export completed: {filename}")
    
    def export_classification_statistics(self, filename: str):
        """Export statistics about UKCAT classification coverage."""
        
        # Overall statistics
        self.cursor.execute("SELECT COUNT(*) FROM funders")
        total_funders = self.cursor.fetchone()[0]
        
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0
        """)
        classified_funders = self.cursor.fetchone()[0]
        
        self.cursor.execute("""
            SELECT COUNT(*) FROM funders 
            WHERE ukcat_codes IS NULL OR jsonb_array_length(ukcat_codes) = 0
        """)
        unclassified_funders = self.cursor.fetchone()[0]
        
        # Category statistics
        self.cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM ukcat_codes 
            GROUP BY category 
            ORDER BY count DESC
        """)
        category_stats = self.cursor.fetchall()
        
        # Most common classifications
        self.cursor.execute("""
            SELECT ukcat_codes, COUNT(*) as count
            FROM funders 
            WHERE ukcat_codes IS NOT NULL AND jsonb_array_length(ukcat_codes) > 0
            GROUP BY ukcat_codes
            ORDER BY count DESC
            LIMIT 20
        """)
        top_classifications = self.cursor.fetchall()
        
        logger.info(f"Exporting classification statistics to {filename}")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Overall stats
            writer.writerow(['OVERALL STATISTICS'])
            writer.writerow(['Metric', 'Count', 'Percentage'])
            writer.writerow(['Total Funders', total_funders, '100.0%'])
            writer.writerow(['Classified Funders', classified_funders, f'{classified_funders/total_funders*100:.1f}%'])
            writer.writerow(['Unclassified Funders', unclassified_funders, f'{unclassified_funders/total_funders*100:.1f}%'])
            writer.writerow([''])
            
            # Category stats
            writer.writerow(['UKCAT CATEGORY STATISTICS'])
            writer.writerow(['Category', 'Number of Codes'])
            for category, count in category_stats:
                writer.writerow([category, count])
            writer.writerow([''])
            
            # Top classifications
            writer.writerow(['MOST COMMON CLASSIFICATIONS'])
            writer.writerow(['UKCAT Codes', 'Number of Funders'])
            for codes, count in top_classifications:
                code_str = ', '.join(codes) if isinstance(codes, list) else str(codes)
                writer.writerow([code_str, count])
        
        logger.info(f"✅ Statistics export completed: {filename}")

def main():
    """Main function for enhanced UKCAT exports."""
    
    parser = argparse.ArgumentParser(description='Enhanced UKCAT export system')
    parser.add_argument('--export-all', action='store_true', help='Export all classified funders with details')
    parser.add_argument('--export-classified', action='store_true', help='Export classified funders (basic)')
    parser.add_argument('--export-matching', action='store_true', help='Export funders ready for matching')
    parser.add_argument('--export-summary', action='store_true', help='Export UKCAT code assignments summary')
    parser.add_argument('--export-stats', action='store_true', help='Export classification statistics')
    parser.add_argument('--output-dir', default='ukcat_exports', help='Output directory for exports')
    parser.add_argument('--include-opportunities', action='store_true', help='Include opportunity data in export')
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment")
        return
    
    conn = psycopg2.connect(db_url)
    
    try:
        exporter = UKCATExporter(conn)
        
        if args.export_all or args.export_classified:
            filename = os.path.join(args.output_dir, 'classified_funders.csv')
            exporter.export_funders_csv(filename, args.include_opportunities)
        
        if args.export_matching:
            filename = os.path.join(args.output_dir, 'funders_for_matching.csv')
            exporter.export_funders_csv(filename, False)
        
        if args.export_summary:
            filename = os.path.join(args.output_dir, 'ukcat_code_assignments.csv')
            exporter.export_ukcat_summary_csv(filename)
        
        if args.export_stats:
            filename = os.path.join(args.output_dir, 'classification_statistics.csv')
            exporter.export_classification_statistics(filename)
        
        if not any([args.export_all, args.export_classified, args.export_matching, args.export_summary, args.export_stats]):
            print("❌ Please specify at least one export option")
            print("Available options:")
            print("  --export-all         Export all classified funders with full details")
            print("  --export-classified  Export basic classified funders")
            print("  --export-matching    Export funders ready for UKCAT matching")
            print("  --export-summary     Export UKCAT code assignments summary")
            print("  --export-stats       Export classification statistics")
        
    except Exception as e:
        logger.error(f"❌ Export failed: {e}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()