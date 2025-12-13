# Monthly Charity Review Instructions

## Overview
Review each charity entry and classify according to the 7 options below.

## Classification Options

1. **Grantmaking Trust**
2. **Grantmaking Foundation**
3. **Operational Charity (provides services)**
4. **Fundraising Charity**
5. **Religious Organization**
6. **Educational Institution**
7. **Other (specify)**

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
Generated: 2025-12-13 21:13:21
