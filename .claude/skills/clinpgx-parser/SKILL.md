---
name: clinpgx-parser
description: Parser for ClinPGx (PharmGKB successor) REST API to extract pharmacogenomics data including gene-drug pairs, CPIC guidelines, clinical annotations, drug labels, and genetic variants. Use when querying pharmacogenomics data, gene-drug interactions, precision medicine dosing, or integrating pharmacogenomic data into knowledge graphs. Triggers on ClinPGx, PharmGKB, pharmacogenomics, gene-drug interaction, CPIC guideline, or drug metabolism tasks.
---

# ClinPGx Pharmacogenomics Parser

## Overview

ClinPGx (successor to PharmGKB) is a comprehensive pharmacogenomics database consolidating data from PharmGKB, CPIC, and PharmCAT. This parser queries the ClinPGx REST API to extract gene-drug interactions, clinical guidelines, annotations, drug labels, and variant data, with a default focus on cardiovascular pharmacogenes and drugs.

**Key characteristics:**
- REST API with JSON responses
- No authentication required for basic access
- Rate limited to 2 requests per second
- API endpoint: https://api.clinpgx.org/v1/
- License: Creative Commons Attribution-ShareAlike 4.0

## Quick Start

### Basic Usage

```python
from src.parsers import ClinPGxParser

# Initialize parser (defaults to CVD pharmacogenes and drugs)
parser = ClinPGxParser(use_cache=True)

# Download data from API
parser.download_data()

# Parse into DataFrames
data = parser.parse_data()

# Access individual DataFrames
gene_drug_df = data['gene_drug_pairs']
guidelines_df = data['guidelines']
annotations_df = data['clinical_annotations']
labels_df = data['drug_labels']
variants_df = data['variants']

print(f"Gene-drug pairs: {len(gene_drug_df)}")
print(f"Guidelines: {len(guidelines_df)}")
```

### Custom Gene/Drug Lists

```python
# Query specific genes and drugs
parser = ClinPGxParser(
    genes=["CYP2C19", "CYP2D6", "SLCO1B1"],
    drugs=["clopidogrel", "metoprolol", "simvastatin"]
)
parser.download_data()
data = parser.parse_data()
```

## Default CVD Focus

### Cardiovascular Pharmacogenes (17)

| Gene | Clinical Relevance |
|------|-------------------|
| CYP2C19 | Clopidogrel metabolism |
| CYP2C9 | Warfarin metabolism |
| VKORC1 | Warfarin target |
| CYP2D6 | Beta-blocker metabolism (metoprolol, carvedilol) |
| SLCO1B1 | Statin transport (simvastatin myopathy risk) |
| CYP3A4 | Statin metabolism |
| CYP3A5 | Tacrolimus (post-transplant) |
| ADRB1 | Beta-blocker response |
| ADRB2 | Beta-blocker response |
| ACE | ACE inhibitor response |
| CETP | Lipid metabolism |
| HMGCR | Statin target |
| PCSK9 | Lipid metabolism |
| NOS3 | Nitric oxide / vascular function |
| F5 | Factor V Leiden / thrombosis |
| F2 | Prothrombin / thrombosis |
| MTHFR | Homocysteine / vascular risk |

### Cardiovascular Drugs (24)

- **Anticoagulants/antiplatelets**: warfarin, clopidogrel, ticagrelor, prasugrel, aspirin, heparin, enoxaparin, rivaroxaban, apixaban
- **Statins**: simvastatin, atorvastatin, rosuvastatin
- **Beta-blockers**: metoprolol, carvedilol, propranolol
- **Antiarrhythmics**: digoxin, amiodarone, flecainide
- **Antihypertensives**: lisinopril, enalapril, losartan, valsartan
- **Vasodilators**: nitroglycerin, hydralazine

## Output Schema

### gene_drug_pairs DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `gene` | String | Gene symbol (e.g., CYP2C19) |
| `drug` | String | Drug name |
| `cpic_level` | String | CPIC guideline level (A, B, C, D) |
| `pgx_level` | String | Pharmacogenomics evidence level |
| `clinpgx_id` | String | ClinPGx identifier |
| `source_database` | String | Always "ClinPGx" |

### guidelines DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `guideline_id` | String | Guideline identifier |
| `gene` | String | Gene symbol |
| `drug` | String | Drug name |
| `source` | String | Guideline source (CPIC, DPWG) |
| `recommendation_text` | String | Clinical recommendation summary |
| `evidence_level` | String | Strength of evidence |
| `url` | String | Link to full guideline |
| `source_database` | String | Always "ClinPGx" |

### clinical_annotations DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `annotation_id` | String | Annotation identifier |
| `gene` | String | Gene symbol |
| `drug` | String | Drug name |
| `phenotype` | String | Clinical phenotype |
| `evidence_level` | String | Evidence level (1A, 1B, 2A, 2B, 3, 4) |
| `pmid` | String | PubMed ID |
| `source_database` | String | Always "ClinPGx" |

### drug_labels DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `label_id` | String | Label identifier |
| `drug` | String | Drug name |
| `gene` | String | Gene(s) mentioned |
| `regulatory_source` | String | Regulatory body (FDA, EMA, etc.) |
| `testing_level` | String | Testing recommendation level |
| `summary` | String | Label pharmacogenomics summary |
| `source_database` | String | Always "ClinPGx" |

### variants DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `variant_id` | String | Variant identifier (e.g., rs4244285) |
| `gene` | String | Gene symbol |
| `chromosome` | String | Chromosome |
| `position` | String | Genomic position |
| `clinical_significance` | String | Clinical significance |
| `allele` | String | Associated allele name |
| `source_database` | String | Always "ClinPGx" |

## Data Mapping for Knowledge Graphs

### Node Types

| Source Field | Target Node Type | Properties |
|--------------|-----------------|------------|
| `gene` | Gene | `geneSymbol` |
| `drug` | Drug | `drugName` |
| `variant_id` | Variant | `rsid`, `chromosome`, `position` |

### Relationship Mappings

```python
# Gene-Drug interaction
gene_drug = {
    'subject': 'gene',
    'relationship': 'AFFECTS_RESPONSE_TO',
    'object': 'drug',
    'properties': {'cpic_level', 'evidence_level'}
}

# Variant-Gene association
variant_gene = {
    'subject': 'variant_id',
    'relationship': 'VARIANT_IN',
    'object': 'gene'
}

# Drug-Guideline association
drug_guideline = {
    'subject': 'drug',
    'relationship': 'HAS_GUIDELINE',
    'object': 'guideline_id',
    'properties': {'recommendation_text', 'evidence_level'}
}
```

## Evidence Levels

### Clinical Annotation Levels (highest to lowest)

| Level | Description |
|-------|-------------|
| 1A | High-quality evidence, CPIC/FDA/DPWG guidelines available |
| 1B | High-quality evidence, not yet in guideline |
| 2A | Moderate evidence from well-designed studies |
| 2B | Moderate evidence with some limitations |
| 3 | Limited or conflicting evidence |
| 4 | Case reports or weak evidence |

### CPIC Guideline Levels

| Level | Description |
|-------|-------------|
| A | Strong recommendation, prescribing action recommended |
| B | Moderate recommendation, prescribing action recommended |
| C | Optional recommendation |
| D | Informative, no prescribing action needed |

## Caching

API responses are cached as JSON files in `src/parsers/data/clinpgx/cache/`. Cache behavior:

```python
# Use cache (default) - avoids repeated API calls
parser = ClinPGxParser(use_cache=True)

# Force fresh API calls
parser = ClinPGxParser(use_cache=False)
```

Cache files are named by endpoint and query parameter (e.g., `gdp_cyp2c19.json`, `dl_warfarin.json`).

## Filtering Examples

### High-Evidence Annotations

```python
# Filter for Level 1A/1B annotations
high_evidence = annotations_df[
    annotations_df['evidence_level'].isin(['1A', '1B'])
]
```

### CPIC Level A Gene-Drug Pairs

```python
# Actionable gene-drug pairs with strong recommendations
actionable = gene_drug_df[gene_drug_df['cpic_level'] == 'A']
```

### FDA-Labeled Drugs

```python
# Drugs with FDA pharmacogenomic labeling
fda_labels = labels_df[labels_df['regulatory_source'] == 'FDA']
```

## API Rate Limits

- **Rate limit**: 2 requests per second maximum
- **Best practices**:
  - 0.5-second delay between requests (implemented in parser)
  - Exponential backoff on HTTP 429 responses (implemented)
  - Cache results locally to avoid repeated queries (implemented)
  - For substantial API use, contact api@clinpgx.org

## Resources

### External Links
- [ClinPGx Website](https://www.clinpgx.org/)
- [ClinPGx API](https://api.clinpgx.org/)
- [CPIC Guidelines](https://cpicpgx.org/)
- [ClinPGx Blog](https://blog.clinpgx.org/)

### References
- PharmGKB/ClinPGx: Curated pharmacogenomics knowledge base
- CPIC: Clinical Pharmacogenetics Implementation Consortium guidelines
- As of July 2025, PharmGKB URLs redirect to ClinPGx
