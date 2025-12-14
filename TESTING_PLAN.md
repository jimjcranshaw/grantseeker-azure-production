# Testing Plan for Charity Commission Integration & UKCAT Classification

## Overview
This testing plan covers all changes made for charity commission funder integration and UKCAT classification systems.

## Test Areas

### 1. Database Insertion (insert_unique_funders.py)
**Purpose:** Verify funders are correctly inserted into database

**Test Cases:**
- ✅ Insert funders with name, charity_number, website
- ✅ Handle duplicate charity numbers (should skip)
- ✅ Handle missing/empty website fields
- ✅ Verify all other fields are NULL/default
- ✅ Check database constraints are maintained

### 2. UKCAT Classification (finish_ukcat_classification.py)
**Purpose:** Verify UKCAT codes are correctly assigned

**Test Cases:**
- ✅ Match charity numbers with UKCAT database
- ✅ Assign UKCAT codes from UKCAT database to funders
- ✅ Handle funders without UKCAT data (mark as processed)
- ✅ Verify codes are stored as JSON array
- ✅ Check no infinite loops on unclassified funders

### 3. Monthly Processor Integration (monthly_charity_processor.py)
**Purpose:** Verify automatic classification works for new monthly additions

**Test Cases:**
- ✅ UKCAT mappings load correctly on initialization
- ✅ New funders get classified during INSERT
- ✅ Updated funders get classified during UPDATE
- ✅ Funders without UKCAT data handled gracefully
- ✅ Classification happens automatically without manual intervention

### 4. Quarterly Recategorization (quarterly_ukcat_recategorization.py)
**Purpose:** Verify quarterly recategorization system works

**Test Cases:**
- ✅ Processes all funders in batches
- ✅ Matches charity numbers with UKCAT database
- ✅ Updates changed classifications
- ✅ Tracks before/after statistics
- ✅ Progress tracking and resume capability
- ✅ Dry-run mode works correctly
- ✅ Generates reports correctly

### 5. Integration Tests
**Purpose:** Verify end-to-end workflows

**Test Cases:**
- ✅ Complete workflow: Insert → Classify → Verify
- ✅ Monthly workflow: Process → Classify → Verify
- ✅ Quarterly workflow: Recategorize → Compare → Report

### 6. Data Quality Tests
**Purpose:** Verify data integrity

**Test Cases:**
- ✅ No duplicate funders created
- ✅ Charity numbers are valid
- ✅ UKCAT codes are valid codes
- ✅ Database constraints maintained
- ✅ No orphaned records

## Test Execution Plan

1. **Unit Tests** - Test individual functions
2. **Integration Tests** - Test workflows
3. **Data Validation** - Verify database state
4. **Performance Tests** - Check processing times
5. **Error Handling** - Test edge cases
