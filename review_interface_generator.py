#!/usr/bin/env python3
"""
Manual Review Interface Generator
================================

Creates review files with the 7 classification options and handles the review workflow.

Author: Grant Seeker Pipeline
Date: December 2025
"""

import csv
import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# 7 Classification Options
CLASSIFICATION_OPTIONS = [
    "Grantmaking Trust",
    "Grantmaking Foundation", 
    "Operational Charity (provides services)",
    "Fundraising Charity",
    "Religious Organization",
    "Educational Institution",
    "Other (specify)"
]

def create_review_template(output_file: Path, trusts: List[Dict]) -> None:
    """Create a comprehensive review template CSV file."""
    
    print(f"📋 Creating review template: {output_file}")
    
    fieldnames = [
        'regno',
        'charity_name',
        'registration_date',
        'current_status',
        'website_url',
        'initial_classification',
        'manual_classification',
        'classification_notes',
        'reviewer_name',
        'review_date',
        'charity_commission_url',
        'research_notes',
        'decision_confidence'  # High/Medium/Low
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for trust in trusts:
            # Generate Charity Commission URL
            cc_url = f"https://register-of-charities.charitycommission.gov.uk/charity-search/?charityNumber={trust['regno']}"
            
            writer.writerow({
                'regno': trust['regno'],
                'charity_name': trust['name'],
                'registration_date': trust['reg_date'],
                'current_status': trust['reg_status'],
                'website_url': '',  # To be filled by reviewer
                'initial_classification': trust.get('initial_classification', 'Needs Review'),
                'manual_classification': '',  # To be filled by reviewer - DROPDOWN
                'classification_notes': '',  # To be filled by reviewer
                'reviewer_name': '',  # To be filled by reviewer
                'review_date': '',  # To be filled by reviewer
                'charity_commission_url': cc_url,
                'research_notes': '',  # To be filled by reviewer
                'decision_confidence': 'Medium'  # Default, can be changed
            })
    
    print(f"✅ Review template created with {len(trusts)} entries")

def create_review_instructions(output_file: Path) -> None:
    """Create detailed review instructions."""
    
    instructions = f"""# Monthly Charity Review Instructions

## Overview
Review each charity entry and classify according to the 7 options below.

## Classification Options

{chr(10).join([f"{i+1}. **{option}**" for i, option in enumerate(CLASSIFICATION_OPTIONS)])}

## Review Process

### Step 1: Open the CSV File
- Open the review template CSV file in Excel, Google Sheets, or similar
- Each row represents one charity to review

### Step 2: Research Each Charity
For each charity, you should:

1. **Visit the Charity Commission Page**
   - Click the link in the `charity_commission_url` column
   - Review official registration details

2. **Check Their Website (if provided)**
   - Look at the `website_url` column
   - If empty, search for their website online
   - Review their activities and funding approach

3. **Review Initial Classification**
   - Check the `initial_classification` column for AI's guess
   - This is just a starting point - use your judgment

### Step 3: Make Your Classification
Choose from the 7 options in the `manual_classification` column:

#### Grantmaking Trusts & Foundations
- **Grantmaking Trust**: Traditional charitable trusts that make grants
- **Grantmaking Foundation**: Charitable foundations that provide funding

#### Operational Charities
- **Operational Charity (provides services)**: Charities that directly provide services rather than just funding others

#### Other Types
- **Fundraising Charity**: Organizations primarily focused on fundraising
- **Religious Organization**: Churches, mosques, temples, religious charities
- **Educational Institution**: Schools, universities, educational charities
- **Other (specify)**: Use this for anything else and specify in notes

### Step 4: Document Your Decision
Fill in these fields:

- **`website_url`**: Add the charity's website if not provided
- **`classification_notes`**: Brief reasoning for your classification
- **`research_notes`**: Any important findings from your research
- **`decision_confidence`**: High/Medium/Low confidence in your decision
- **`reviewer_name`**: Your name
- **`review_date`**: Today's date

### Step 5: Quality Checks
Before submitting, verify:

- ✅ All charities have been reviewed
- ✅ All `manual_classification` fields are filled
- ✅ Website URLs added where found
- ✅ Notes provided for complex cases
- ✅ Your name and date added

## Example Completed Entry

| regno | charity_name | manual_classification | classification_notes | website_url |
|-------|-------------|---------------------|---------------------|-------------|
| 1234567 | ABC Community Trust | Grantmaking Trust | Makes grants to local charities and community groups | https://abctrust.org |

## Tips for Classification

### Grantmaking vs Operational
- **Grantmaking**: "We provide funding to other organizations"
- **Operational**: "We provide direct services to beneficiaries"

### Religious Organizations
- Churches, mosques, temples, religious education
- Even if they do some grantmaking, classify as religious if that's their primary purpose

### Educational Institutions
- Schools, colleges, universities
- Educational charities and scholarship providers

### When in Doubt
- Use "Other (specify)" and explain in notes
- It's better to be specific than force a fit

## Submission
Once complete, save the file and place it in the `/data/reviewed/` folder.
The system will automatically detect and process it.

---
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    print(f"📖 Review instructions created: {output_file}")

def validate_review_file(review_file: Path) -> Dict:
    """Validate a completed review file."""
    
    print(f"🔍 Validating review file: {review_file}")
    
    issues = []
    stats = {
        'total_entries': 0,
        'classified_entries': 0,
        'with_websites': 0,
        'with_notes': 0,
        'confidence_distribution': {'High': 0, 'Medium': 0, 'Low': 0}
    }
    
    try:
        with open(review_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Check required columns
            required_columns = ['regno', 'manual_classification', 'reviewer_name', 'review_date']
            missing_columns = [col for col in required_columns if col not in fieldnames]
            
            if missing_columns:
                issues.append(f"Missing required columns: {missing_columns}")
                return {'valid': False, 'issues': issues, 'stats': stats}
            
            for row in reader:
                stats['total_entries'] += 1
                
                # Check classification
                if row.get('manual_classification'):
                    stats['classified_entries'] += 1
                    
                    # Validate classification option
                    if row['manual_classification'] not in CLASSIFICATION_OPTIONS:
                        issues.append(f"Row {stats['total_entries']}: Invalid classification '{row['manual_classification']}'")
                    
                    # Check for "Other" specification
                    if row['manual_classification'] == 'Other (specify)' and not row.get('classification_notes'):
                        issues.append(f"Row {stats['total_entries']}: 'Other' classification requires notes")
                
                # Check website
                if row.get('website_url'):
                    stats['with_websites'] += 1
                
                # Check notes
                if row.get('classification_notes') or row.get('research_notes'):
                    stats['with_notes'] += 1
                
                # Check confidence
                confidence = row.get('decision_confidence', 'Medium')
                if confidence in stats['confidence_distribution']:
                    stats['confidence_distribution'][confidence] += 1
                
                # Check reviewer info
                if not row.get('reviewer_name'):
                    issues.append(f"Row {stats['total_entries']}: Missing reviewer name")
                
                if not row.get('review_date'):
                    issues.append(f"Row {stats['total_entries']}: Missing review date")
        
        # Calculate completion rate
        if stats['total_entries'] > 0:
            completion_rate = (stats['classified_entries'] / stats['total_entries']) * 100
            if completion_rate < 100:
                issues.append(f"Incomplete review: {completion_rate:.1f}% entries classified")
        
        valid = len(issues) == 0
        
        print(f"✅ Validation complete: {'Valid' if valid else 'Issues found'}")
        if not valid:
            for issue in issues:
                print(f"  ❌ {issue}")
        
        return {
            'valid': valid,
            'issues': issues,
            'stats': stats
        }
        
    except Exception as e:
        issues.append(f"File read error: {e}")
        return {'valid': False, 'issues': issues, 'stats': stats}

def main():
    parser = argparse.ArgumentParser(description="Manual Review Interface Generator")
    parser.add_argument('--create-template', type=Path, help='Create review template from JSON file')
    parser.add_argument('--create-instructions', type=Path, help='Create review instructions file')
    parser.add_argument('--validate', type=Path, help='Validate completed review file')
    parser.add_argument('--output-dir', type=Path, default=Path('./review_output'), help='Output directory')
    
    args = parser.parse_args()
    
    # Create output directory
    args.output_dir.mkdir(exist_ok=True)
    
    if args.create_template:
        # Load trusts data
        with open(args.create_template, 'r') as f:
            trusts = json.load(f)
        
        # Create template
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        template_file = args.output_dir / f"review_template_{timestamp}.csv"
        create_review_template(template_file, trusts)
        
        # Create instructions
        instructions_file = args.output_dir / f"review_instructions_{timestamp}.md"
        create_review_instructions(instructions_file)
        
        print(f"📁 Files created in: {args.output_dir}")
        print(f"  📋 Template: {template_file}")
        print(f"  📖 Instructions: {instructions_file}")
    
    elif args.validate:
        result = validate_review_file(args.validate)
        
        print(f"\n📊 Validation Results:")
        print(f"  Total entries: {result['stats']['total_entries']}")
        print(f"  Classified: {result['stats']['classified_entries']}")
        print(f"  With websites: {result['stats']['with_websites']}")
        print(f"  With notes: {result['stats']['with_notes']}")
        
        print(f"\n📈 Confidence Distribution:")
        for level, count in result['stats']['confidence_distribution'].items():
            print(f"  {level}: {count}")
        
        if result['valid']:
            print("✅ File is ready for submission!")
        else:
            print("❌ Please fix the issues before submission:")
            for issue in result['issues']:
                print(f"  - {issue}")
    
    elif args.create_instructions:
        create_review_instructions(args.create_instructions)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()