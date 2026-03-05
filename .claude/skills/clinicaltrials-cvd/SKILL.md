---
name: clinicaltrials-cvd
description: Parser for ClinicalTrials.gov API v2 to extract cardiovascular disease clinical trials data including trial IDs, interventions, conditions, phases, and status. Supports broad CVD condition queries, RNA therapeutics intervention queries, and custom queries. Use when querying clinical trials, researching CVD therapeutics, analyzing trial phases, or integrating clinical trial data into knowledge graphs. Triggers on ClinicalTrials.gov, clinical trial parsing, cardiovascular trials, or drug trial database tasks.
---

# ClinicalTrials.gov Cardiovascular Disease Parser

## Overview

ClinicalTrials.gov is a database of privately and publicly funded clinical studies conducted around the world. This parser uses the ClinicalTrials.gov API v2 to extract clinical trial data, with a default focus on cardiovascular disease conditions. It supports three query modes: broad CVD condition search, RNA therapeutics intervention search, and custom queries.

**Key characteristics:**
- REST API with JSON responses
- No authentication required
- Rate limited to ~50 requests/minute per IP
- API endpoint: https://clinicaltrials.gov/api/v2/studies

## Quick Start

### Default: Broad CVD Query

```python
from src.parsers import ClinicalTrialsParser

# Default mode queries all CVD conditions
parser = ClinicalTrialsParser(max_results=1000)

# Download data from API
parser.download_data()

# Parse into DataFrame
data = parser.parse_data()
trials_df = data['clinical_trials']

print(f"Retrieved {len(trials_df)} CVD trials")
print(trials_df.head())
```

### RNA Therapeutics Mode

```python
# Legacy RNA therapeutics query
parser = ClinicalTrialsParser(query_mode="rna", max_results=500)
parser.download_data()
data = parser.parse_data()
trials_df = data['clinical_trials']

# Post-filter for cardiovascular trials
cvd_rna = parser.filter_cardiovascular_trials(trials_df)
print(f"Found {len(cvd_rna)} cardiovascular RNA trials")
```

### Custom Query Mode

```python
# Custom intervention or condition query
parser = ClinicalTrialsParser(
    query_mode="custom",
    query_term="SGLT2 inhibitor",
    query_field="query.intr",
    max_results=200
)
parser.download_data()
data = parser.parse_data()
```

## Query Modes

### `"cvd"` (default)

Queries ClinicalTrials.gov by **condition** using 10 grouped CVD category searches. Each category is an OR-joined query covering terms from `ontology/cvd_disease_hierarchy.txt`. Results are deduplicated by NCT ID across categories.

**CVD categories queried:**
1. Cardiovascular disease, heart disease, cardiac disease
2. Arrhythmia, atrial fibrillation, ventricular tachycardia, long QT syndrome, Brugada syndrome
3. Coronary artery disease, myocardial infarction, angina, atherosclerosis
4. Heart failure, congestive heart failure, HFrEF, HFpEF
5. Cardiomyopathy (hypertrophic, dilated, restrictive, ARVC)
6. Hypertension, pulmonary hypertension, resistant hypertension
7. Stroke, cerebrovascular disease, ischemic/hemorrhagic stroke, TIA
8. Peripheral arterial disease, vascular disease, aortic aneurysm, thromboembolism
9. Hypercholesterolemia, dyslipidemia, familial hypercholesterolemia
10. Valvular heart disease, aortic stenosis, mitral regurgitation

### `"rna"`

Queries by **intervention** using the term "RNA therapeutics". Use `filter_cardiovascular_trials()` to post-filter for CVD-relevant results.

### `"custom"`

Queries using a user-provided `query_term` and `query_field`. The field defaults to `"query.cond"` (condition search) but can be set to `"query.intr"` (intervention) or any other supported API parameter.

## Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_dir` | str or None | None | Directory for cached data |
| `query_mode` | str | `"cvd"` | Query strategy: `"cvd"`, `"rna"`, or `"custom"` |
| `query_term` | str or None | None | Search term (required for `"custom"` mode) |
| `query_field` | str | `"query.cond"` | API query field for `"custom"` mode |
| `max_results` | int | 1000 | Maximum results per query/category |

## Output Schema

### clinical_trials DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `trial_id` | String | ClinicalTrials.gov NCT identifier (e.g., NCT12345678) |
| `title` | String | Study title (brief or official) |
| `intervention_name` | String | Drug/intervention name(s), semicolon-separated |
| `condition` | String | Disease/condition(s), semicolon-separated |
| `phase` | String | Study phase (PHASE1, PHASE2, PHASE3, PHASE4, or combinations) |
| `status` | String | Recruitment status (e.g., RECRUITING, COMPLETED, TERMINATED) |
| `source_database` | String | Always "ClinicalTrials.gov" |

### Example Output

```
   trial_id                              title       intervention_name                condition      phase         status
0  NCT05123456  SGLT2 Inhibitor in Heart Failure    Dapagliflozin      Heart Failure, Chronic    PHASE3    COMPLETED
1  NCT05234567  Anticoagulation in Atrial Fib      Apixaban            Atrial Fibrillation      PHASE4    RECRUITING
```

## Data Mapping for Knowledge Graphs

### Node Types

| Source Field | Target Node Type | Properties |
|--------------|-----------------|------------|
| `trial_id` | ClinicalTrial | `trialId`, `title`, `phase`, `status` |
| `intervention_name` | Drug/Intervention | `drugName`, `interventionType` |
| `condition` | Disease | `diseaseName` |

### Relationship Mappings

```python
# Trial-Intervention relationships
trial_intervention = {
    'subject': 'trial_id',
    'relationship': 'TESTS_INTERVENTION',
    'object': 'intervention_name'
}

# Trial-Disease relationships
trial_disease = {
    'subject': 'trial_id',
    'relationship': 'STUDIES_CONDITION',
    'object': 'condition'
}
```

## Filtering Examples

### Post-Filter for CVD (RNA/Custom Modes)

```python
# Only needed for "rna" or "custom" modes; "cvd" mode queries CVD directly
cvd_trials = parser.filter_cardiovascular_trials(trials_df)
```

### By Phase

```python
# Completed Phase 3 trials
phase3_completed = trials_df[
    (trials_df['phase'].str.contains('PHASE3')) &
    (trials_df['status'] == 'COMPLETED')
]
```

### By Status

```python
# Active recruiting trials
recruiting = trials_df[trials_df['status'] == 'RECRUITING']
```

### By Specific Condition

```python
# Heart failure trials
hf_trials = trials_df[
    trials_df['condition'].str.contains('heart failure', case=False, na=False)
]
```

## Common Custom Queries

### By Intervention Type

```python
# SGLT2 inhibitors
ClinicalTrialsParser(query_mode="custom", query_term="SGLT2 inhibitor", query_field="query.intr")

# PCSK9 inhibitors
ClinicalTrialsParser(query_mode="custom", query_term="PCSK9", query_field="query.intr")

# RNA therapeutics (same as "rna" mode)
ClinicalTrialsParser(query_mode="custom", query_term="RNA therapeutics", query_field="query.intr")
```

### By Specific Condition

```python
# Familial hypercholesterolemia specifically
ClinicalTrialsParser(query_mode="custom", query_term="familial hypercholesterolemia")

# Post-MI trials
ClinicalTrialsParser(query_mode="custom", query_term="myocardial infarction")
```

## API Rate Limits

- **Rate limit**: ~50 requests per minute per IP
- **Best practices**:
  - Pagination handled automatically (100 results per page)
  - 1.5-second delay between pages (implemented)
  - 2-second delay between CVD category batches (implemented)
  - Results deduplicated by NCT ID in CVD mode

## Resources

### External Links
- [ClinicalTrials.gov API Documentation](https://clinicaltrials.gov/data-api/api)
- [API Version 2.0 Announcement](https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html)
- [ClinicalTrials.gov Homepage](https://clinicaltrials.gov/)

### References
- NLM Technical Bulletin. (2024). ClinicalTrials.gov API Version 2.0 Now Available.
