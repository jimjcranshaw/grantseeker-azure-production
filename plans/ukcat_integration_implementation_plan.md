# UKCAT Classification Integration Implementation Plan

## 🎯 **Objective**
Integrate UKCAT classification codes into GrantSeeker database to enable precise AI-powered matching between charities and funders based on shared classification categories.

## 📋 **Business Requirements**
- **Store UKCAT codes** for all 11,000 funders in database
- **Add charity number column** to database tables  
- **Create enhanced export** combining funders + opportunities with charity numbers
- **Build matching system** to find funders with overlapping UKCAT classifications
- **Avoid storing 300k+ charities** - use on-demand UKCAT lookup

## 🏗️ **Technical Architecture**

### **Data Flow**
```
Charity User (with charity number) 
    ↓ UKCAT Lookup
UKCAT Classification Codes 
    ↓ Matching Algorithm  
Funder Database (with UKCAT codes)
    ↓ Ranking
Precision-matched Funder Recommendations
```

### **Database Schema Updates**
```sql
-- Add charity_number to funders table
ALTER TABLE funders ADD COLUMN charity_number VARCHAR(20);

-- Add UKCAT codes to funders table (JSON array for multiple codes)
ALTER TABLE funders ADD COLUMN ukcat_codes JSONB;

-- Add UKCAT codes to opportunities table (for context)
ALTER TABLE opportunities ADD COLUMN ukcat_codes JSONB;

-- Create UKCAT codes reference table
CREATE TABLE ukcat_codes (
    code VARCHAR(10) PRIMARY KEY,
    tag VARCHAR(200),
    category VARCHAR(100),
    subcategory VARCHAR(100),
    level INTEGER,
    description TEXT,
    regex_pattern TEXT
);
```

## 📝 **Implementation Steps**

### **Phase 1: Database Schema & Data Preparation**
1. **Create database migration** for charity_number and ukcat_codes columns
2. **Import UKCAT classification data** into reference table
3. **Update existing export scripts** to include charity numbers
4. **Test schema changes** on development environment

### **Phase 2: UKCAT Data Integration**
1. **Process UKCAT classification data** for existing 11,000 funders
2. **Create matching script** to assign UKCAT codes based on funder names/descriptions
3. **Update funder records** with assigned UKCAT codes
4. **Validate classification accuracy** with sample testing

### **Phase 3: Enhanced Export System**
1. **Create comprehensive export** joining funders + opportunities + charity numbers + UKCAT codes
2. **Exclude chunked text** (as requested)
3. **Add filtering options** for specific UKCAT categories
4. **Test export performance** with full dataset

### **Phase 4: Matching Algorithm**
1. **Build UKCAT lookup service** for charity numbers
2. **Create matching algorithm** based on code overlap
3. **Implement ranking system** (exact matches > partial matches)
4. **Add caching layer** for performance optimization

### **Phase 5: Integration & Testing**
1. **Integrate with existing pipeline** 
2. **Test end-to-end workflow** with sample data
3. **Performance testing** with full dataset
4. **Documentation and deployment**

## 🔧 **Key Technical Components**

### **UKCAT Classification Structure**
- **Categories**: Animals, Armed forces, Arts, Associations, etc. (255 total codes)
- **Hierarchical**: Parent codes (e.g., "AR" for Arts) with specific subcodes (e.g., "AR101" for Culture)
- **Multiple tags per charity**: Average 3-5 codes per organization
- **Regex patterns**: Used for automatic classification

### **Data Storage Strategy**
```python
# Example funder record
{
    "id": 123,
    "name": "Big Lottery Fund",
    "website": "https://www.biglotteryfund.org.uk",
    "charity_number": "1064286", 
    "ukcat_codes": ["CA200", "CA202", "CV102", "SW105"],
    "classification_type": "GRANTMAKING_CHARITY"
}
```

### **Matching Algorithm**
```python
def find_matching_funders(charity_number):
    # 1. Get charity's UKCAT codes from UKCAT API
    charity_codes = ukcat_service.get_classification(charity_number)
    
    # 2. Find funders with overlapping codes
    matching_funders = db.query(
        "SELECT * FROM funders WHERE ukcat_codes && %s",
        charity_codes
    )
    
    # 3. Rank by overlap quality
    return rank_by_overlap(matching_funders, charity_codes)
```

## 📊 **Expected Benefits**

### **AI Algorithm Improvements**
- **Precision matching**: Charities see only relevant funders
- **Reduced noise**: Eliminate broad/unrelated matches
- **Enhanced recommendations**: Based on actual organizational similarities
- **Better user experience**: More targeted results

### **Database Optimization**
- **Minimal storage**: Only 11k funder records with codes
- **Efficient queries**: JSONB indexing for fast lookups
- **Scalable architecture**: Works with any number of user charities
- **Current data**: Always uses latest UKCAT classifications

## 🎯 **Success Metrics**
- **Classification coverage**: 90%+ of funders have relevant UKCAT codes
- **Query performance**: <200ms for matching algorithm
- **Data quality**: <5% classification errors in validation testing
- **User satisfaction**: Improved funder recommendation accuracy

## ⚡ **Quick Wins**
1. **Add charity number column** immediately (enables current exports)
2. **Import UKCAT reference data** (foundation for all other work)
3. **Enhanced export script** (provides immediate value)
4. **Sample classification testing** (validates approach)

## 🔄 **Next Actions**
1. Review and approve implementation plan
2. Begin Phase 1 database schema changes
3. Set up UKCAT data processing pipeline
4. Create development environment for testing

---

**Priority**: High
**Estimated Timeline**: 2-3 weeks for full implementation
**Resource Requirements**: 1 developer, database access, UKCAT data access