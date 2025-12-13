import json
from openai import AsyncOpenAI
import os
import logging
import time

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def analyze_with_direct_llm(pages: list, foundation_name: str, use_deepseek: bool = True) -> dict:
    """
    Analyzes content to identify one or more funding opportunities.
    Returns a dict containing a 'opportunities' list.
    """
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

CONTENT:
{combined_content}

Return ONLY valid JSON with this exact structure:
{{
    "is_grantmaking_charity": true/false,  // TRUE if they fund OTHER charities/groups. FALSE if they only fund their own work/subcontractors.
    "funder_type_reason": "Brief explanation of why you classified them this way (UK English)",
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
            "application_form_type": "Must be one of: 'ONLINE APPLICATION FORM OPEN', 'ONLINE APPLICATION FORM WHICH REQUIRED LOGIN', 'PDF', 'WORD', or 'QUESTIONS LISTED ON WEBSITE'",
            "application_questions_list": "List of questions (retaining numbering if present, or create numbering)",
            "guidance_url": "URL location of guidance for applicants",
            "guidance_text": "Guidance for applicants (e.g., how to best answer each question). EXACT WORDING preferred."
        }}
    ]
}}"""

    if use_deepseek:
        logger.info(f"  ⏳ Initializing DeepSeek client...")
        start_time = time.time()
        # Increased timeout to 180s to handle full content analysis
        client = AsyncOpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url="https://api.deepseek.com", timeout=180)
        model = "deepseek-chat"
        elapsed_time = time.time() - start_time
        logger.info(f"  ⏱️ DeepSeek client initialized in {elapsed_time:.2f} seconds")
    else:
        client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        model = "gpt-4o-mini"
    
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Extract grant info as structured JSON. Identify distinct opportunities."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=8000 # Increased to 8000 to prevent truncation of exact wording
        )
        
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"): content = content[7:]
        if content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        content = content.strip()
        
        result = json.loads(content)
        
        # Ensure consistent structure
        if "opportunities" not in result:
            # Fallback if LLM returned a single object instead of list
            if "is_grantmaking_charity" in result:
                 # It returned the classification but maybe messed up the list
                 result["opportunities"] = []
            else:
                 # It probably just returned an opportunity object directly
                 result = {
                     "is_grantmaking_charity": True, # Assume yes if it found an opportunity
                     "funder_type_reason": "inferred from direct opportunity result",
                     "opportunities": [result]
                 }
            
        return result
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse failed: {e}")
        return {
            'is_grantmaking_charity': None,
            'funder_type_reason': f"Error parsing analysis: {e}",
            'opportunities': [{
                'opportunity_title': 'Error parsing analysis',
                'description': content if 'content' in locals() else 'Error',
                'eligibility_inclusion': '', 'eligibility_exclusion': '',
                'application_requirements': '', 'application_process': '',
                'application_questions': '', 'objectives_goals': '', 'funding_focus': '',
                'funding_amounts': '', 'deadlines': '', 'evaluation_criteria': '',
                'contact_info': '',
                'application_form_url': '',
                'application_form_type': '',
                'application_questions_list': '',
                'guidance_url': '',
                'guidance_text': ''
            }]
        }
    except Exception as e:
        print(f"❌ API failed: {e}")
        raise
