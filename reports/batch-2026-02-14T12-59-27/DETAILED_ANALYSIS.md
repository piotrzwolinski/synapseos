# Test Results Analysis - Batch 2026-02-14T12-59-27

## Executive Summary

**Total Tests**: 70
**Pass Rate (≥4.0)**: 27/70 (38.6%)
**Warning (3.0-3.9)**: 38/70 (54.3%)
**Critical (<3.0)**: 5/70 (7.1%)

**Note**: 19 tests had API key errors during judge execution (Gemini judge failed), but the system responses were still evaluated by OpenAI and Anthropic judges.

## Root Cause Distribution

| Category | Count | Description |
|----------|-------|-------------|
| **GOOD** | 27 | Score ≥ 4.0, no significant issues |
| **API_ERROR** | 19 | Judge execution failed (API key issue), but system response may be valid |
| **REASONING** | 12 | Bad engineering logic, wrong product selection, hallucinations |
| **GRAPH_DATA** | 5 | Wrong specs from graph, missing catalog data |
| **TRUNCATION** | 3 | Response cut off mid-sentence |
| **OVER_BLOCKING** | 2 | System blocks valid configurations |
| **UNDER_BLOCKING** | 1 | System allows unsafe configuration |
| **CLARIFICATION_LOOP** | 1 | System asks for already-provided info |

## Critical Failures (Score < 3.0)

### 1. hc_shaft_service_access (Score: 2.05)
**Root Cause**: REASONING (Hallucination)

**Problem**: System invented a "service clearance" constraint that doesn't exist in the catalog.
- User requested GDB-1200x1500 for 17,000 m³/h
- System claimed it needs "2400mm of side clearance" (double the width) for service access
- **Actual issue missed**: The airflow (17,000 m³/h) may exceed capacity limits
- Suggested PFF Planfilterram (a filter mat frame) as alternative to GDB housing - completely invalid

**Judge quotes**:
- Gemini: "Missed critical airflow capacity limit (17,000 vs 10,000 m³/h). Hallucinated 'double width' service clearance rule"
- OpenAI: "Invents a service-clearance requirement not supported by the catalog"
- Anthropic: "Fabricates a 'service clearance' constraint that does not exist"

**Severity**: Critical - Complete hallucination of technical constraints

---

### 2. hc_formaldehyde_lab (Score: 2.62)
**Root Cause**: REASONING (Product Knowledge Hallucination)

**Problem**: System fundamentally misidentified the GDC product family.
- User requested GDC-600x600 RF for anatomy lab formaldehyde exhaust
- System claimed: "GDC family uses mechanical filtration, which cannot remove gas-phase contaminants"
- **Reality**: PDF p.14 explicitly states GDC is for "patronfilter med kol eller kemikaliemedia" (carbon or chemical media cartridges)
- System blocked the CORRECT product for the application

**Judge quotes**:
- Gemini: "Critical hallucination regarding product function: claims GDC is for mechanical filtration when the PDF defines it as a carbon/chemical filter housing"
- OpenAI: "Incorrectly states GDC uses only mechanical filtration and blocks it, contradicting the catalog"
- Anthropic: "Fundamentally misidentifies the GDC product family as mechanical filtration when it is explicitly a carbon/chemical patron filter housing"

**Severity**: Critical - System has inverted knowledge about core product family function

---

### 3. chatgpt_gdb_length_750_for_long_bags (Score: 2.90)
**Root Cause**: REASONING (Over-blocking)

**Problem**: System incorrectly blocked a valid standard configuration
- Evidence: "Incorrectly blocked a valid standard configuration"

---

### 4. chatgpt_gdb_300x600_1800_undersized (Score: 3.37)
**Root Cause**: REASONING (Wrong sizing approach)

**Problem**: System recommended non-standard multi-unit solution instead of single standard SKU
- Evidence: "Recommended two separate 300x600 units instead of the standard single GDB 600x600 SKU"
- Should have suggested upsizing to a single standard size

---

### 5. chatgpt_env_marine_gdb_fz (Score: 3.38)
**Root Cause**: REASONING (Material/environment confusion)

**Problem**: Suggested wrong mitigation for corrosion
- Evidence: "Implies a pre-filter might solve the housing corrosion issue, whereas the material itself needs to change"
- Should recommend material upgrade (FZ → RF/ZM), not pre-filtration

---

## Significant Graph Data Issues

### 1. hc_gdcflex_rf_available (Score: 3.50)
**Evidence**: System blocked single-wall uninsulated housing for hospital application - this is correct engineering but suggests the catalog constraint may be missing in graph

### 2. hc_hospital_leakage_class (Score: 3.53)
**Evidence**: Similar to above - system blocks GDB for hospital leakage class requirements

### 3. chatgpt_prod_hospital_gdb_fz_pivot (Score: 3.58)
**Evidence**: "Introduces unsupported catalog assertions (ATEX rating and hospital approval logic) and uses an overly absolute blocking tone"

### 4. hc_wastewater_h2s_fz (Score: 3.72)
**Evidence**: "Misstates or fabricates catalog constraints (GDB corrosion class and allowed environments; bolted/leakage assertions)"

### 5. hc_marine_gdmi_sf_pivot (Score: 3.85)
**Evidence**: "Incorrectly states GDMI has a C3 rating (PDF p.11 lists ZM as C4)"

---

## Truncation Issues

### 1. chatgpt_prod_rooftop_gdb_fz_condensation (Score: 3.65)
**Evidence**: "Response is truncated mid-sentence, and mentions 'carbon adsorption efficiency' when GDB is a bag/compact filter housing (not carbon)"

### 2. chatgpt_env_outdoor_gdb_fz (Score: 3.77)
**Evidence**: "The system correctly identifies a critical application error" but response truncated

### 3. hc_gdmi_sf_trap (Score: 3.97)
**Evidence**: Response about SF material constraint truncated

---

## Clarification Loop

### 1. hc_cruise_ship_gdc_oversized (Score: 3.70)
**Evidence**: "The system correctly identified a critical sizing mismatch (2600 m³/h exceeds the 2000 m³/h limit for GDC 600x600) but then has clarification issues"

---

## Top Performing Tests (Score ≥ 4.5)

1. **chatgpt_env_hospital_gdmi_rf** (4.72) - Excellent
2. **chatgpt_gdcflex_900x600_2500_ok** (4.70) - Excellent
3. **chatgpt_gdc_600x600_2800_undersized** (4.68) - Excellent
4. **hc_short_bag_geometry_error** (4.63) - Correctly blocked physical incompatibility
5. **chatgpt_gdmi_600x600_3400_ok** (4.63) - Excellent
6. **chatgpt_gdc_600x600_2000_ok** (4.62) - Excellent
7. **chatgpt_gdb_600x600_2500_ok** (4.60) - Excellent
8. **chatgpt_gdmi_rf_not_available** (4.50) - Correctly blocked unavailable material

---

## Key Findings

### 1. Product Knowledge Hallucinations (Most Critical)
The most severe failures involve the system having fundamentally wrong knowledge about product families:
- **GDC misidentified as mechanical filtration** when it's for carbon/chemical media
- **Invented service clearance rules** that don't exist in catalog
- **Wrong product alternatives** (suggesting filter frames as housing replacements)

### 2. Graph Data Contamination
Several tests show incorrect specifications:
- Wrong corrosion class ratings (C3 vs C4)
- Missing or incorrect material availability constraints
- Incorrect ATEX/approval logic

### 3. API Judge Failures
19 tests have Gemini API key errors during judging. These tests still have OpenAI and Anthropic scores, but the average is calculated from fewer judges.

### 4. Good Performance on Standard Cases
The system performs well (≥4.0) on:
- Standard sizing scenarios
- Clear capacity matches
- Blocking physically impossible configurations
- Material availability constraints

### 5. Weak Performance on Edge Cases
The system struggles with:
- Complex multi-constraint scenarios
- Application-specific requirements (hospital, marine, formaldehyde)
- Service/installation constraints
- Recovery from undersized scenarios

---

## Recommendations

### Immediate (P0)
1. **Fix GDC product knowledge**: System must know GDC is for carbon/chemical media, not mechanical filtration
2. **Remove hallucinated constraints**: "Service clearance = 2x width" rule doesn't exist
3. **Fix product alternative logic**: Never suggest PFF (filter frame) as alternative to GDB (housing)

### High Priority (P1)
4. **Validate corrosion class data**: Audit C3/C4/C5 ratings in graph vs catalog
5. **Fix sizing recovery**: For undersized scenarios, suggest single larger unit before multi-unit arrays
6. **Material vs pre-filter logic**: Corrosion issues require material upgrade, not pre-filtration

### Medium Priority (P2)
7. **Truncation handling**: Implement response completion detection
8. **Application constraints**: Validate hospital/marine/lab specific requirements in graph
9. **Fix Gemini API key**: Restore 3-judge consensus for all tests

---

## Tests Requiring Manual Review

These tests have API errors but may have valid system responses:
- chatgpt_insulated_c5_gdmi_zm (2.37)
- chatgpt_gdb_1200x900_10000_ok (2.45)
- hc_aluminium_dust_atex22 (3.17)
- chatgpt_env_atex21_gdcflex (3.20)
- [15 more with API_ERROR between 3.27-3.98]
