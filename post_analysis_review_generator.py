#!/usr/bin/env python3
"""
Post-Analysis Review Interface Generator
=======================================

Creates review interface for AFTER crawling and AI analysis.
Shows extracted opportunities + AI classification for user verification.

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

def create_post_analysis_review_template(output_file: Path, analyzed_trusts: List[Dict]) -> None:
    """Create review template showing AI analysis results for user verification."""
    
    print(f"📋 Creating post-analysis review template: {output_file}")
    
    fieldnames = [
        'regno',
        'charity_name',
        'registration_date',
        'current_status',
        'website_url',
        'ai_classification',
        'ai_confidence',
        'opportunities_found',
        'extracted_opportunities_summary',
        'user_classification',
        'user_confidence',
        'user_notes',
        'user_decision',  # Agree/Disagree/Partially Agree
        'reviewer_name',
        'review_date',
        'charity_commission_url',
        'evidence_url'
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for trust_data in analyzed_trusts:
            # Generate Charity Commission URL
            cc_url = f"https://register-of-charities.charitycommission.gov.uk/charity-search/?charityNumber={trust_data['regno']}"
            
            # Extract opportunities summary
            opportunities = trust_data.get('opportunities', [])
            opp_summary = f"{len(opportunities)} opportunities found"
            if opportunities:
                opp_titles = [opp.get('title', 'Untitled')[:50] + '...' if len(opp.get('title', '')) > 50 else opp.get('title', 'Untitled') for opp in opportunities[:3]]
                opp_summary += f": {', '.join(opp_titles)}"
                if len(opportunities) > 3:
                    opp_summary += f" (+{len(opportunities)-3} more)"
            
            writer.writerow({
                'regno': trust_data['regno'],
                'charity_name': trust_data['name'],
                'registration_date': trust_data.get('reg_date', ''),
                'current_status': trust_data.get('reg_status', ''),
                'website_url': trust_data.get('website', ''),
                'ai_classification': trust_data.get('ai_classification', 'Unknown'),
                'ai_confidence': trust_data.get('ai_confidence', 'Medium'),
                'opportunities_found': len(opportunities),
                'extracted_opportunities_summary': opp_summary,
                'user_classification': '',  # To be filled by reviewer
                'user_confidence': 'Medium',  # Default
                'user_notes': '',  # To be filled by reviewer
                'user_decision': '',  # Agree/Disagree/Partially Agree
                'reviewer_name': '',  # To be filled by reviewer
                'review_date': '',  # To be filled by reviewer
                'charity_commission_url': cc_url,
                'evidence_url': trust_data.get('website', '')  # Where the evidence can be found
            })
    
    print(f"✅ Post-analysis review template created with {len(analyzed_trusts)} entries")

def create_post_analysis_instructions(output_file: Path) -> None:
    """Create detailed review instructions for post-analysis review."""
    
    instructions = f"""# Post-Analysis Charity Review Instructions

## Overview
Review the AI's analysis results for each charity. The AI has already crawled the website and extracted opportunities. Your job is to verify the AI's classification and findings.

## What You'll See

For each charity, you'll have:

1. **AI Classification**: What the AI thinks the charity is
2. **AI Confidence**: How confident the AI is (High/Medium/Low)
3. **Opportunities Found**: How many funding opportunities the AI extracted
4. **Evidence**: Links to review the AI's findings

## Your Review Process

### Step 1: Check the AI's Work
1. **Visit the website** listed in `evidence_url`
2. **Review the opportunities** the AI extracted
3. **Assess the classification** the AI assigned

### Step 2: Make Your Decision
Choose one of three options in `user_decision`:

#### ✅ **Agree**
- The AI classification is correct
- The opportunities look relevant
- No changes needed

#### ❌ **Disagree** 
- The AI classification is wrong
- Provide your reasoning in `user_notes`
- Specify the correct classification in `user_classification`

#### ⚠️ **Partially Agree**
- The AI got the general idea right but details are off
- Some opportunities are relevant, others aren't
- Explain what needs correction in `user_notes`

### Step 3: Provide Your Classification
Choose from the 7 options in `user_classification`:

{chr(10).join([f"{i+1}. **{option}**" for i, option in enumerate(CLASSIFICATION_OPTIONS)])}

### Step 4: Document Your Reasoning
Fill in:
- **`user_notes`**: Your reasoning and observations
- **`user_confidence`**: How confident you are in your review
- **`reviewer_name`**: Your name
- **`review_date`**: Today's date

## Classification Guidelines

### Grantmaking vs Operational
- **Grantmaking**: "We provide funding to other organizations"
- **Operational**: "We provide direct services to beneficiaries"

### Religious Organizations
- Churches, mosques, temples, religious education
- Even if they do some grantmaking, classify as religious if that's their primary purpose

### When AI Makes Mistakes
Common AI errors to watch for:
- Misclassifying fundraising charities as grantmaking
- Missing that religious organizations are primarily religious
- Confusing educational institutions with grantmaking foundations
- Overlooking that some "charities" are actually businesses

## Quality Checks
Before submitting, verify:
- ✅ All charities have been reviewed
- ✅ `user_decision` field is filled (Agree/Disagree/Partially Agree)
- ✅ `user_classification` is specified if you disagreed
- ✅ `user_notes` provide reasoning for your decision
- ✅ Your name and date are added

## Example Completed Entry

| charity_name | ai_classification | user_decision | user_classification | user_notes |
|-------------|------------------|---------------|-------------------|------------|
| ABC Community Trust | Grantmaking Trust | Agree | Grantmaking Trust | AI correctly identified their grantmaking activities. Website shows clear funding programs. |

---
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    print(f"📖 Post-analysis review instructions created: {output_file}")

def validate_post_analysis_review(review_file: Path) -> Dict:
    """Validate a completed post-analysis review file."""
    
    print(f"🔍 Validating post-analysis review file: {review_file}")
    
    issues = []
    stats = {
        'total_entries': 0,
        'agreed_entries': 0,
        'disagreed_entries': 0,
        'partially_agreed_entries': 0,
        'with_user_notes': 0,
        'confidence_distribution': {'High': 0, 'Medium': 0, 'Low': 0}
    }
    
    try:
        with open(review_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Check required columns
            required_columns = ['regno', 'user_decision', 'reviewer_name', 'review_date']
            missing_columns = [col for col in required_columns if col not in fieldnames]
            
            if missing_columns:
                issues.append(f"Missing required columns: {missing_columns}")
                return {'valid': False, 'issues': issues, 'stats': stats}
            
            for row in reader:
                stats['total_entries'] += 1
                
                # Check user decision
                decision = row.get('user_decision', '')
                if decision == 'Agree':
                    stats['agreed_entries'] += 1
                elif decision == 'Disagree':
                    stats['disagreed_entries'] += 1
                    # Check that they provided user classification
                    if not row.get('user_classification'):
                        issues.append(f"Row {stats['total_entries']}: Disagreement requires user_classification")
                elif decision == 'Partially Agree':
                    stats['partially_agreed_entries'] += 1
                else:
                    issues.append(f"Row {stats['total_entries']}: Invalid user_decision '{decision}'")
                
                # Check user notes
                if row.get('user_notes'):
                    stats['with_user_notes'] += 1
                
                # Check confidence
                confidence = row.get('user_confidence', 'Medium')
                if confidence in stats['confidence_distribution']:
                    stats['confidence_distribution'][confidence] += 1
                
                # Check reviewer info
                if not row.get('reviewer_name'):
                    issues.append(f"Row {stats['total_entries']}: Missing reviewer name")
                
                if not row.get('review_date'):
                    issues.append(f"Row {stats['total_entries']}: Missing review date")
        
        # Calculate completion rate
        if stats['total_entries'] > 0:
            completion_rate = (stats['total_entries'] / stats['total_entries']) * 100  # All should be completed
            if stats['agreed_entries'] + stats['disagreed_entries'] + stats['partially_agreed_entries'] < stats['total_entries']:
                incomplete = stats['total_entries'] - (stats['agreed_entries'] + stats['disagreed_entries'] + stats['partially_agreed_entries'])
                issues.append(f"Incomplete review: {incomplete} entries without user_decision")
        
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
    parser = argparse.ArgumentParser(description="Post-Analysis Review Interface Generator")
    parser.add_argument('--create-template', type=Path, help='Create post-analysis review template from analyzed data JSON')
    parser.add_argument('--create-instructions', type=Path, help='Create post-analysis review instructions file')
    parser.add_argument('--validate', type=Path, help='Validate completed post-analysis review file')
    parser.add_argument('--output-dir', type=Path, default=Path('./review_output'), help='Output directory')
    
    args = parser.parse_args()
    
    # Create output directory
    args.output_dir.mkdir(exist_ok=True)
    
    if args.create_template:
        # Load analyzed trusts data
        with open(args.create_template, 'r') as f:
            trusts_data = json.load(f)
        
        # Create template
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        template_file = args.output_dir / f"post_analysis_review_{timestamp}.csv"
        create_post_analysis_review_template(template_file, trusts_data)
        
        # Create instructions
        instructions_file = args.output_dir / f"post_analysis_instructions_{timestamp}.md"
        create_post_analysis_instructions(instructions_file)
        
        print(f"📁 Files created in: {args.output_dir}")
        print(f"  📋 Template: {template_file}")
        print(f"  📖 Instructions: {instructions_file}")
    
    elif args.validate:
        result = validate_post_analysis_review(args.validate)
        
        print(f"\n📊 Validation Results:")
        print(f"  Total entries: {result['stats']['total_entries']}")
        print(f"  Agreed: {result['stats']['agreed_entries']}")
        print(f"  Disagreed: {result['stats']['disagreed_entries']}")
        print(f"  Partially agreed: {result['stats']['partially_agreed_entries']}")
        print(f"  With notes: {result['stats']['with_user_notes']}")
        
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
        create_post_analysis_instructions(args.create_instructions)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()