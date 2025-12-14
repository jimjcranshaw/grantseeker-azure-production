# Archive Documentation
**Created:** 2025-12-14 15:29:33

## Current Status
- **Main Classifier:** `continuous_classifier.py` (running as background process)
- **Database:** UKCAT integration fully implemented with 241 classification patterns
- **Classification Status:** 443/5298 funders classified (8.4%)

## Archived Scripts

### Background Classification Scripts
- `background_classifier.py` - Original simple background classifier
  - Replaced by: `continuous_classifier.py` with better logging and batch processing

### Scripts Available for Archiving (Future)
The following scripts may be candidates for archiving as they're part of development/test phases:
- Migration scripts (one-time operations)
- Test/validation scripts (development only)
- Old export/import utilities (replaced by newer versions)

### Active Scripts (Keep)
- `continuous_classifier.py` - Main production classifier
- `assign_ukcat_codes_to_funders.py` - Batch processor for development
- `ukcat_enhanced_matching.py` - Enhanced matching algorithm
- Database migration scripts (for reference)

## Notes
- Continuous classifier is running but showing 0% match rate
- Pattern matching logic may need debugging
- Process running as PID 848133
- Logs in: `classification.log`

---
**Archive Directory:** `archive/old_scripts_20251214_152933/`