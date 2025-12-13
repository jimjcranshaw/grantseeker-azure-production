# Pipeline Consistency Implementation Code Plan

**Implementation details for fixing the pipeline inconsistencies**

---

## 🔧 Code Implementation Steps

### Step 1: Database Schema Updates

#### 1.1 Add New Columns to Funders Table

```sql
-- Add classification tracking columns
ALTER TABLE funders ADD COLUMN IF NOT EXISTS classification_type VARCHAR(50);
ALTER TABLE funders ADD COLUMN IF NOT EXISTS assessment_notes TEXT;
ALTER TABLE funders ADD COLUMN IF NOT EXISTS requires_manual_review BOOLEAN DEFAULT false;

-- Add opportunity source tracking
ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS opportunity_source VARCHAR(50);
ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS is_default_assessment BOOLEAN DEFAULT false;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_funders_classification ON funders(classification_type);
CREATE INDEX IF NOT EXISTS idx_opportunities_source ON funding_opportunities(opportunity_source);
```

#### 1.2 Create Migration Script

```python
# migration_add_consistency_fields.py
import psycopg2
import os
from dotenv import load_dotenv

def migrate_database():
    """Add consistency fields to database."""
    
    # Load environment
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
    
    try:
        # Add columns
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS classification_type VARCHAR(50);
        """)
        
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS assessment_notes TEXT;
        """)
        
        cursor.execute("""
            ALTER TABLE funders ADD COLUMN IF NOT EXISTS requires_manual_review BOOLEAN DEFAULT false;
        """)
        
        cursor.execute("""
            ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS opportunity_source VARCHAR(50);
        """)
        
        cursor.execute("""
            ALTER TABLE funding_opportunities ADD COLUMN IF NOT EXISTS is_default_assessment BOOLEAN DEFAULT false;
        """)
        
        # Add indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_funders_classification 
            ON funders(classification_type);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_source 
            ON funding_opportunities(opportunity_source);
        """)
        
        conn.commit()
        print("✅ Database migration completed successfully")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
```

### Step 2: Enhanced AI Analysis Function

#### 2.1 Modify `simple_llm_analysis.py`

```python
# In simple_llm_analysis.py - replace the main function

async def analyze_with_direct_llm(pages: list, foundation_name: str, use_deepseek: bool = True) -> dict:
    """
    Analyzes content to identify funding opportunities.
    ALWAYS returns at least one assessment record for every foundation.
    """
    
    # Ensure we have content to analyze
    if not pages:
        # Return default assessment for no content
        return {
            "is_grantmaking_charity": None,
            "funder_type_reason": "No content found on website",
            "classification_type": "NO_CONTENT_FOUND",
            "opportunities": [
                {
                    "opportunity_title": "Assessment: No Content Found",
                    "description": "No meaningful content could be extracted from the website. Manual review required.",
                    "eligibility_inclusion": "Manual review required",
                    "eligibility_exclusion": "N/A",
                    "funding_amounts": "N/A",
                    "deadlines": "N/A",
                    "application_process": "Manual website review required",
                    "application_questions": "",
                    "objectives_goals": "Website content extraction failed",
                    "funding_focus": "N/A",
                    "evaluation_criteria": "N/A",
                    "contact_info": "See website directly",
                    "application_form_url": "",
                    "application_form_type": "MANUAL_REVIEW_REQUIRED",
                    "application_questions_list": "",
                    "guidance_url": "",
                    "guidance_text": "Website content could not be accessed or parsed",
                    "important_urls": ""
                }
            ]
        }
    
    combined_content = "\n\n---PAGE BREAK---\n\n".join([
        f"URL: {page['url']}\nTitle: {page['title']}\n\n{page['content'][:5000]}"
        for page in pages
    ])
    
    prompt = f"""Analyze {foundation_name}'s website and extract distinct funding opportunities.
    
    IMPORTANT RULES:
    1. **LANGUAGE**: Output MUST be in **UK English** (e.g., use 'programme' not 'program', 'organisation' not 'organization').
    2. **CLASSIFICATION**: You must determine if this entity is a "Grantmaking Charity" (funds other charities/groups) OR an "Operational/Service Charity" (does its own work/funds subcontractors).
    3. **OPPORTUNITIES**: Identify EACH distinct grant programme or 'pot' of money. If they do NOT give grants to others, return an empty opportunities list.
    4. **ELIGIBILITY**: Explicitly separate Inclusion criteria (who CAN apply) from Exclusion criteria (who CANNOT apply).
    5. **EXACT WORDING**: Wherever possible, extract the EXACT WORDING that the funder uses on their website across all questions and guidance.
    6. **GUARANTEED OUTPUT**: Even if no grant opportunities are found, provide a classification assessment.

    CONTENT:
    {combined_content}

    Return ONLY valid JSON with this exact structure:
    {{
        "is_grantmaking_charity": true/false/null,  // TRUE if they fund OTHER charities/groups. FALSE if they only fund their own work/subcontractors. NULL if unclear.
        "funder_type_reason": "Brief explanation of why you classified them this way (UK English)",
        "classification_type": "One of: GRANTMAKING_CHARITY, OPERATIONAL_CHARITY, FUNDRAISING_PLATFORM, NON_CHARITY, UNCLASSIFIED, NO_CONTENT_FOUND",
        "opportunities": [
            {{
                "opportunity_title": "Name of the specific grant programme/pot",
                "description": "Brief description of this specific opportunity",
                "eligibility_inclusion": "Who is eligible? (Inclusion criteria)",
                "eligibility_exclusion": "Who is NOT eligible? (Exclusion criteria)",
                "application_requirements": "Documents and materials needed",
                "application_process": "Step-by-step process",
                "application_questions": "Key application questions",
                "objectives_goals": "Goals of this specific programme",
                "funding_focus": "Thematic focus areas",
                "funding_amounts": "Grant sizes/amounts",
                "deadlines": "Specific deadlines",
                "evaluation_criteria": "How applications are judged",
                "contact_info": "Contact details",
                
                "application_form_url": "URL location of application form (one URL only)",
                "application_form_type": "Must be one of: 'ONLINE APPLICATION FORM OPEN', 'ONLINE APPLICATION FORM WHICH REQUIRED LOGIN', 'PDF', 'WORD', 'QUESTIONS LISTED ON WEBSITE', 'REQUIRES_MANUAL_REVIEW', 'DIRECT_SERVICES_ONLY', 'NOT_A_CHARITY', 'INVALID_ENTRY'",
                "application_questions_list": "List of questions (retaining numbering if present, or create numbering)",
                "guidance_url": "URL location of guidance for applicants",
                "guidance_text": "Guidance for applicants (e.g., how to best answer each question). EXACT WORDING preferred."
            }}
        ]
    }}"""

    # ... rest of the function with error handling and API calls ...
    # [Previous code for API calls remains the same until the end]
    
    # After getting API response, ensure we always have opportunities
    try:
        # Parse response and validate structure
        result = json.loads(content)
        
        # GUARANTEE: If no opportunities found, create default assessment
        if not result.get("opportunities"):
            # Determine classification type based on is_grantmaking_charity
            is_grantmaking = result.get("is_grantmaking_charity")
            reason = result.get("funder_type_reason", "No opportunities found")
            
            if is_grantmaking is True:
                classification_type = "GRANTMAKING_CHARITY"
                opp_title = "Grant Programmes Available"
                opp_description = "This charity provides grants to other organizations. Review website for specific programmes."
            elif is_grantmaking is False:
                classification_type = "OPERATIONAL_CHARITY"
                opp_title = "Direct Service Provider"
                opp_description = "This charity provides direct services rather than grants to other organizations."
            else:
                classification_type = "UNCLASSIFIED"
                opp_title = "Classification Unclear"
                opp_description = "Unable to determine classification. Manual review required."
            
            # Add default opportunity
            default_opportunity = {
                "opportunity_title": opp_title,
                "description": opp_description,
                "eligibility_inclusion": "See website for specific criteria" if is_grantmaking else "Direct services only",
                "eligibility_exclusion": "N/A",
                "funding_amounts": "N/A",
                "deadlines": "N/A",
                "application_process": "Review website for application process",
                "application_questions": "",
                "objectives_goals": reason,
                "funding_focus": "N/A",
                "evaluation_criteria": "N/A",
                "contact_info": "See funder website",
                "application_form_url": "",
                "application_form_type": "REQUIRES_MANUAL_REVIEW" if classification_type == "UNCLASSIFIED" else "MULTIPLE_PROGRAMMES",
                "application_questions_list": "",
                "guidance_url": "",
                "guidance_text": f"AI Analysis: {reason}",
                "important_urls": ""
            }
            
            result["opportunities"] = [default_opportunity]
        
        # Add classification type if missing
        if "classification_type" not in result:
            is_grantmaking = result.get("is_grantmaking_charity")
            if is_grantmaking is True:
                result["classification_type"] = "GRANTMAKING_CHARITY"
            elif is_grantmaking is False:
                result["classification_type"] = "OPERATIONAL_CHARITY"
            else:
                result["classification_type"] = "UNCLASSIFIED"
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse failed: {e}")
        # Return default assessment on parse error
        return {
            'is_grantmaking_charity': None,
            'funder_type_reason': f"Error parsing analysis: {e}",
            'classification_type': 'UNCLASSIFIED',
            'opportunities': [{
                'opportunity_title': 'Assessment: Parse Error',
                'description': f"Error parsing AI analysis: {e}",
                'eligibility_inclusion': 'Manual review required',
                'eligibility_exclusion': 'N/A',
                'funding_amounts': 'N/A',
                'deadlines': 'N/A',
                'application_process': 'Manual website review required',
                'application_questions': '',
                'objectives_goals': 'Analysis parsing failed',
                'funding_focus': 'N/A',
                'evaluation_criteria': 'N/A',
                'contact_info': 'See website directly',
                'application_form_url': '',
                'application_form_type': 'MANUAL_REVIEW_REQUIRED',
                'application_questions_list': '',
                'guidance_url': '',
                'guidance_text': f"Analysis error: {e}",
                'important_urls': ''
            }]
        }
    except Exception as e:
        print(f"❌ API failed: {e}")
        # Return default assessment on API error
        return {
            'is_grantmaking_charity': None,
            'funder_type_reason': f"API analysis failed: {e}",
            'classification_type': 'UNCLASSIFIED',
            'opportunities': [{
                'opportunity_title': 'Assessment: API Error',
                'description': f"AI analysis failed: {e}",
                'eligibility_inclusion': 'Manual review required',
                'eligibility_exclusion': 'N/A',
                'funding_amounts': 'N/A',
                'deadlines': 'N/A',
                'application_process': 'Manual website review required',
                'application_questions': '',
                'objectives_goals': 'Analysis failed',
                'funding_focus': 'N/A',
                'evaluation_criteria': 'N/A',
                'contact_info': 'See website directly',
                'application_form_url': '',
                'application_form_type': 'MANUAL_REVIEW_REQUIRED',
                'application_questions_list': '',
                'guidance_url': '',
                'guidance_text': f"Analysis error: {e}",
                'important_urls': ''
            }]
        }
```

### Step 3: Enhanced Storage Function

#### 3.1 Modify Database Storage Functions

```python
# Add to azure_production_pipeline.py

def store_funding_opportunities_guaranteed(funder_id: int, session_id: int, analysis: dict) -> int:
    """
    Store funding opportunities with guaranteed coverage.
    Every funder gets at least one opportunity record.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Clean up old opportunities for this funder
        cursor.execute("DELETE FROM funding_opportunities WHERE funder_id = %s", (funder_id,))
        
        # Get opportunities from analysis
        opportunities = analysis.get('opportunities', [])
        
        # If no opportunities in analysis, create default
        if not opportunities:
            classification_type = analysis.get('classification_type', 'UNCLASSIFIED')
            is_grantmaking = analysis.get('is_grantmaking_charity')
            
            default_opportunity = create_default_opportunity(analysis, classification_type)
            opportunities = [default_opportunity]
        
        # Store each opportunity
        stored_count = 0
        for opp in opportunities:
            cursor.execute("""
                INSERT INTO funding_opportunities (
                    funder_id, scrape_session_id, opportunity_title, description,
                    eligibility_inclusion, eligibility_exclusion, funding_focus,
                    funding_amounts, deadlines, application_process, application_requirements,
                    evaluation_criteria, contact_info, application_form_url, application_form_type,
                    application_questions, guidance_url, guidance_text, objectives_goals,
                    important_urls, opportunity_source, is_default_assessment
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                funder_id, session_id,
                opp.get('opportunity_title', 'Untitled'),
                opp.get('description', ''),
                opp.get('eligibility_inclusion', ''),
                opp.get('eligibility_exclusion', ''),
                opp.get('funding_focus', ''),
                opp.get('funding_amounts', ''),
                opp.get('deadlines', ''),
                opp.get('application_process', ''),
                opp.get('application_requirements', ''),
                opp.get('evaluation_criteria', ''),
                opp.get('contact_info', ''),
                opp.get('application_form_url', ''),
                opp.get('application_form_type', 'UNKNOWN'),
                opp.get('application_questions', ''),
                opp.get('guidance_url', ''),
                opp.get('guidance_text', ''),
                opp.get('objectives_goals', ''),
                opp.get('important_urls', ''),
                opp.get('opportunity_source', 'AI_ANALYSIS'),
                opp.get('is_default_assessment', False)
            ))
            stored_count += 1
        
        conn.commit()
        logger.info(f"  ✅ Stored {stored_count} opportunities for funder {funder_id}")
        return stored_count
        
    except Exception as e:
        logger.error(f"  ❌ Error storing opportunities for funder {funder_id}: {e}")
        conn.rollback()
        # Even on error, create a minimal opportunity record
        try:
            cursor.execute("""
                INSERT INTO funding_opportunities (
                    funder_id, scrape_session_id, opportunity_title, description,
                    opportunity_source, is_default_assessment
                ) VALUES (
                    %s, %s, %s, %s, %s, %s
                )
            """, (
                funder_id, session_id, 
                'Assessment: Storage Error',
                f'Error storing opportunities: {e}',
                'ERROR_FALLBACK',
                True
            ))
            conn.commit()
        except:
            pass  # Give up if we can't even store error record
        return 0
    finally:
        release_db_connection(conn)

def create_default_opportunity(analysis: dict, classification_type: str) -> dict:
    """Create default opportunity based on classification."""
    
    templates = {
        "GRANTMAKING_CHARITY": {
            "opportunity_title": "Grant Programmes Available",
            "description": "This charity provides grants to other organizations. Review website for specific programmes.",
            "application_form_type": "MULTIPLE_PROGRAMMES"
        },
        "OPERATIONAL_CHARITY": {
            "opportunity_title": "Direct Service Provider",
            "description": "This charity provides direct services rather than grants to other organizations.",
            "application_form_type": "DIRECT_SERVICES_ONLY"
        },
        "FUNDRAISING_PLATFORM": {
            "opportunity_title": "Fundraising Platform",
            "description": "This appears to be a fundraising platform rather than a grantmaking charity.",
            "application_form_type": "NOT_A_CHARITY"
        },
        "NON_CHARITY": {
            "opportunity_title": "Non-Charity Entity",
            "description": "This entity does not appear to be a registered charity.",
            "application_form_type": "INVALID_ENTRY"
        },
        "NO_CONTENT_FOUND": {
            "opportunity_title": "Assessment: No Content Found",
            "description": "No meaningful content could be extracted from the website. Manual review required.",
            "application_form_type": "MANUAL_REVIEW_REQUIRED"
        },
        "UNCLASSIFIED": {
            "opportunity_title": "Classification Unclear",
            "description": "Unable to determine classification. Manual review required.",
            "application_form_type": "MANUAL_REVIEW_REQUIRED"
        }
    }
    
    template = templates.get(classification_type, templates["UNCLASSIFIED"])
    reason = analysis.get('funder_type_reason', 'No analysis available')
    
    return {
        **template,
        "description": f"{template['description']} AI Analysis: {reason}",
        "eligibility_inclusion": "See website for specific criteria",
        "eligibility_exclusion": "N/A",
        "funding_amounts": "N/A",
        "deadlines": "N/A",
        "application_process": "Review website for application process",
        "contact_info": "See website directly",
        "application_questions": "",
        "guidance_text": f"AI Analysis: {reason}",
        "objectives_goals": reason,
        "funding_focus": "N/A",
        "evaluation_criteria": "N/A",
        "application_url": "",
        "guidance_url": "",
        "important_urls": "",
        "opportunity_source": "DEFAULT_TEMPLATE",
        "is_default_assessment": True
    }

def update_funder_classification_enhanced(funder_id: int, analysis: dict):
    """Update funder classification with enhanced tracking."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        is_grantmaking = analysis.get('is_grantmaking_charity')
        type_reason = analysis.get('funder_type_reason', '')
        classification_type = analysis.get('classification_type', 'UNCLASSIFIED')
        requires_review = classification_type in ['UNCLASSIFIED', 'NO_CONTENT_FOUND', 'FUNDRAISING_PLATFORM']
        
        cursor.execute("""
            UPDATE funders SET 
                is_grantmaking_charity = %s,
                funder_type_reason = %s,
                classification_type = %s,
                requires_manual_review = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_grantmaking, type_reason, classification_type, requires_review, funder_id))
        
        conn.commit()
        logger.info(f"  ✓ Updated classification: {classification_type}")
        
    except Exception as e:
        logger.error(f"  ❌ Error updating classification for funder {funder_id}: {e}")
        conn.rollback()
    finally:
        release_db_connection(conn)
```

### Step 4: Validation Functions

#### 4.1 Add Validation Script

```python
# validate_pipeline_consistency.py
import psycopg2
import os
from dotenv import load_dotenv

def validate_100_percent_coverage():
    """Validate that 100% of funders have opportunities."""
    
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
    
    try:
        # Check 1: No funders without opportunities
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funders f 
            WHERE f.is_active = TRUE 
            AND f.last_checked IS NOT NULL
            AND f.id NOT IN (SELECT DISTINCT funder_id FROM funding_opportunities)
        """)
        gap_count = cursor.fetchone()[0]
        
        # Check 2: All opportunities have proper classification
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funding_opportunities fo
            JOIN funders f ON fo.funder_id = f.id
            WHERE f.is_grantmaking_charity IS NULL
            AND f.is_active = TRUE
        """)
        unclassified_count = cursor.fetchone()[0]
        
        # Check 3: Assessment records are properly tagged
        cursor.execute("""
            SELECT COUNT(*) 
            FROM funding_opportunities 
            WHERE is_default_assessment = true
            AND opportunity_source IS NULL
        """)
        untagged_assessments = cursor.fetchone()[0]
        
        # Check 4: Generate breakdown by classification
        cursor.execute("""
            SELECT 
                f.classification_type,
                COUNT(DISTINCT f.id) as funder_count,
                COUNT(fo.id) as opportunity_count,
                COUNT(CASE WHEN f.requires_manual_review = true THEN 1 END) as needing_review
            FROM funders f
            LEFT JOIN funding_opportunities fo ON f.id = fo.funder_id
            WHERE f.is_active = TRUE
            GROUP BY f.classification_type
            ORDER BY funder_count DESC
        """)
        breakdown = cursor.fetchall()
        
        # Print results
        print("=" * 60)
        print("PIPELINE CONSISTENCY VALIDATION")
        print("=" * 60)
        
        print(f"❌ FUNDERS WITHOUT OPPORTUNITIES: {gap_count}")
        if gap_count == 0:
            print("✅ 100% Coverage Achieved!")
        else:
            print(f"❌ CRITICAL: {gap_count} funders missing opportunities!")
        
        print(f"📊 UNCLASSIFIED FUNDERS: {unclassified_count}")
        print(f"🏷️  UNTAGGED ASSESSMENTS: {untagged_assessments}")
        
        print("\nCLASSIFICATION BREAKDOWN:")
        print("-" * 40)
        for classification, funder_count, opp_count, needing_review in breakdown:
            print(f"{classification}: {funder_count} funders, {opp_count} opportunities, {needing_review} need review")
        
        # Summary
        total_funders = sum(row[1] for row in breakdown)
        total_opportunities = sum(row[2] for row in breakdown)
        avg_opportunities = total_opportunities / total_funders if total_funders > 0 else 0
        
        print(f"\nSUMMARY:")
        print(f"Total Funders: {total_funders}")
        print(f"Total Opportunities: {total_opportunities}")
        print(f"Average Opportunities per Funder: {avg_opportunities:.2f}")
        print(f"Coverage Rate: {((total_funders - gap_count) / total_funders * 100):.1f}%")
        
        return {
            'gap_count': gap_count,
            'unclassified_count': unclassified_count,
            'untagged_assessments': untagged_assessments,
            'breakdown': breakdown,
            'coverage_rate': ((total_funders - gap_count) / total_funders * 100) if total_funders > 0 else 0
        }
        
    finally:
        conn.close()

if __name__ == "__main__":
    result = validate_100_percent_coverage()
    
    if result['gap_count'] == 0:
        print("\n🎉 SUCCESS: Pipeline consistency validated!")
    else:
        print(f"\n❌ FAILURE: {result['gap_count']} funders still missing opportunities")
        print("Pipeline needs fixing before deployment!")
```

### Step 5: Main Pipeline Integration

#### 5.1 Update Main Processing Function

```python
# In azure_production_pipeline.py - modify the process_foundation function

async def process_foundation_enhanced(name: str, url: str, semaphore, stats):
    """Enhanced foundation processing with guaranteed coverage."""
    
    async with semaphore:
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"Processing: {name}")
            logger.info(f"{'='*70}")
            
            # Store/get foundation
            funder_id = store_foundation(name, url)
            logger.info(f"  ✓ Foundation ID: {funder_id}")
            
            # Check for changes using HTTP HEAD
            if CHANGE_DETECTION_ENABLED:
                stored_etag, stored_last_modified, stored_content_hash = get_foundation_change_headers(funder_id)
                changed, new_etag, new_last_modified, new_content_hash = check_url_changed(url, stored_etag, stored_last_modified, stored_content_hash)
                
                # Update headers
                update_change_detection_headers(funder_id, new_etag, new_last_modified, new_content_hash)
                
                if not changed:
                    logger.info(f"  ⏭️  No changes detected - skipping scrape")
                    stats['skipped'] += 1
                    return
            
            # Create scrape session
            session_id = create_scrape_session(funder_id)
            logger.info(f"  ✓ Scrape session ID: {session_id}")
            
            # Crawl foundation website
            logger.info(f"  🔍 Crawling: {url}")
            start_time = time.time()
            pages = await crawl_foundation(url, name)
            elapsed_time = time.time() - start_time
            logger.info(f"  ⏱️ Crawling completed in {elapsed_time:.2f} seconds")
            
            logger.debug(f"  Crawled pages: {len(pages)}")
            
            # ENHANCED: Even if no pages crawled, create assessment record
            if not pages:
                logger.warning(f"  ⚠️ No pages crawled - creating assessment record")
                # Create minimal analysis result
                analysis = {
                    "is_grantmaking_charity": None,
                    "funder_type_reason": "Website crawling failed - no content found",
                    "classification_type": "NO_CONTENT_FOUND",
                    "opportunities": []
                }
            else:
                # Clean up old data before storing new data
                cleanup_foundation_data(funder_id)
                
                # Store pages and generate embeddings
                logger.info(f"  💾 Storing pages and generating embeddings...")
                store_pages_and_embeddings(session_id, funder_id, pages)
                
                # Analyze content
                logger.info(f"  🤖 Analyzing with DeepSeek (direct API)...")
                analysis = await analyze_foundation_content(pages, name)
            
            # Update classification with enhanced tracking
            update_funder_classification_enhanced(funder_id, analysis)
            
            # ENHANCED: Store opportunities with guaranteed coverage
            logger.info(f"  💾 Storing opportunities with guaranteed coverage...")
            opportunity_count = store_funding_opportunities_guaranteed(funder_id, session_id, analysis)
            
            # Complete session
            complete_scrape_session(session_id)
            
            logger.info(f"  ✅ Completed {name} - {opportunity_count} opportunities stored")
            stats['completed'] += 1
            
        except Exception as e:
            logger.error(f"  ❌ Error processing {name}: {str(e)}")
            
            # ENHANCED: Even on error, create assessment record
            try:
                logger.info(f"  🔧 Creating error assessment record...")
                funder_id = store_foundation(name, url)
                session_id = create_scrape_session(funder_id)
                
                error_analysis = {
                    "is_grantmaking_charity": None,
                    "funder_type_reason": f"Processing error: {str(e)}",
                    "classification_type": "UNCLASSIFIED",
                    "opportunities": []
                }
                
                update_funder_classification_enhanced(funder_id, error_analysis)
                store_funding_opportunities_guaranteed(funder_id, session_id, error_analysis)
                complete_scrape_session(session_id)
                
                logger.info(f"  ✅ Error assessment record created")
                stats['completed'] += 1  # Count as completed since we have assessment
                
            except Exception as nested_error:
                logger.error(f"  ❌ Failed to create error assessment: {nested_error}")
                stats['failed'] += 1
```

---

## 🚀 Deployment Steps

### Step 1: Backup Current State
```bash
# Create backup of current database
pg_dump -h your-server.postgres.database.azure.com -U your-user postgres > backup_before_consistency_fix.sql

# Create backup of current code
git branch backup-before-consistency-fix
git commit -m "Backup before consistency fix"
```

### Step 2: Apply Database Migration
```bash
python migration_add_consistency_fields.py
```

### Step 3: Test on Subset
```bash
# Test on 100 foundations first
python azure_production_pipeline.py --test-foundations 100
```

### Step 4: Validate Results
```bash
python validate_pipeline_consistency.py
```

### Step 5: Deploy Full Pipeline
```bash
# Run full pipeline
python azure_production_pipeline.py
```

### Step 6: Final Validation
```bash
python validate_pipeline_consistency.py
```

---

## ✅ Success Criteria

1. **100% Coverage**: Every funder has at least one opportunity record
2. **Consistent Logic**: Same input always produces same output
3. **Error Handling**: Even failed processing generates assessment records
4. **Classification Tracking**: All funders have clear classification types
5. **Manual Review Ready**: Clear identification of funders needing review

**This implementation ensures reliable, predictable pipeline behavior with guaranteed coverage.**