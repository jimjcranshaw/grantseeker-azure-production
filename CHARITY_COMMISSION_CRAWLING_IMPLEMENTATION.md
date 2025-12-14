# Charity Commission Page Crawling Implementation

## Overview
Implemented support for crawling Charity Commission profile pages for funders without websites, extracting opportunities using the same structured DeepSeek analysis as the main pipeline.

## Implementation Details

### 1. Charity Commission URL Building
- **Function**: `build_charity_commission_url(charity_number: str)`
- **URL Format**: `https://register-of-charities.charitycommission.gov.uk/charity-details/?regId={charity_number}&subId=0`
- Automatically constructs Charity Commission profile page URLs from charity numbers

### 2. Pipeline Modifications

#### Modified `process_foundation()` Function
- **New Parameters**: 
  - `funder_id: Optional[int]` - Pre-existing funder ID
  - `charity_number: Optional[str]` - Charity number for Charity Commission pages
- **Logic**:
  - If no website URL provided, checks for charity number
  - Builds Charity Commission URL if charity number exists
  - Uses Charity Commission page for crawling instead of website
  - Same processing pipeline: crawl → extract → analyze → store opportunities

#### New Function: `load_funders_without_websites(limit: Optional[int])`
- Loads funders from database with:
  - No website (NULL or empty)
  - Has charity number (not NULL/empty)
- Returns list of `(funder_id, name, charity_number)` tuples
- Used by main pipeline to automatically process funders via Charity Commission pages

#### New Function: `get_funder_charity_number(funder_id: int)`
- Retrieves charity number from database for a given funder ID
- Used when charity number not provided directly

### 3. Enhanced Document Extraction

#### Improved Document Detection
The crawler now detects documents from Charity Commission pages by checking for:
- Standard file extensions (`.pdf`, `.doc`, `.docx`)
- Charity Commission-specific patterns:
  - `annual-accounts` in URL
  - `articles-of-association` in URL
  - `governing-document` in URL
  - `download` + PDF/DOC indicators

#### Document Processing
- Documents are automatically processed with Docling (already integrated)
- Extracted content is included in the analysis pipeline
- Same opportunity extraction applies to document content

### 4. Main Pipeline Integration

#### Automatic Processing
The main pipeline (`main()`) now:
1. Loads foundations with websites (existing behavior)
2. **NEW**: Also loads funders without websites (with charity numbers)
3. Processes both groups in parallel
4. Uses same concurrency controls and change detection

#### Output Format
- **Same as existing pipeline**: Structured opportunities with:
  - Opportunity title and description
  - Eligibility criteria (inclusion/exclusion)
  - Application requirements and process
  - Funding focus and amounts
  - Deadlines and evaluation criteria
  - Contact information
  - Important URLs (including Charity Commission page)
  - Application forms and guidance

### 5. Testing

#### Test Script: `test_charity_commission_crawling.py`
- Tests Charity Commission page crawling on sample funders
- Verifies opportunity extraction
- Reports statistics and results

**Usage**:
```bash
python3 test_charity_commission_crawling.py --count 5
```

## Features

✅ **Same Output Format**: Opportunities extracted via structured DeepSeek analysis  
✅ **Document Extraction**: Annual accounts, articles of association, governing documents  
✅ **Docling Integration**: Documents processed and included in analysis  
✅ **Change Detection**: HTTP HEAD change detection works for Charity Commission pages  
✅ **Parallel Processing**: Same concurrency controls as main pipeline  
✅ **Automatic Discovery**: Pipeline automatically finds and processes funders without websites  

## Database Schema Requirements

The implementation uses existing schema:
- `funders` table with:
  - `id` (primary key)
  - `name` (unique)
  - `website` (nullable)
  - `charity_number` (nullable)
  - `etag`, `last_modified`, `content_hash` (for change detection)

## Usage

### Running Full Pipeline
The main pipeline automatically processes funders without websites:
```bash
python3 azure_production_pipeline.py
```

### Testing Only Charity Commission Pages
```bash
python3 test_charity_commission_crawling.py --count 10
```

## Next Steps

1. ✅ **Implementation Complete**: All core functionality implemented
2. ⏳ **Testing**: Run comprehensive tests on sample funders
3. ⏳ **Monitoring**: Set up monitoring for Charity Commission page changes
4. ⏳ **Automation**: Integrate into scheduled pipeline runs

## Notes

- Charity Commission pages are crawled with the same depth and page limits as regular websites
- Document extraction is prioritized (up to 5 documents per funder)
- Change detection works the same way - checks for updates to Charity Commission pages
- All opportunities are stored in the same `funding_opportunities` table with the same structure
