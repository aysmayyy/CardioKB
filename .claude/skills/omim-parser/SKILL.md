---
name: omim-parser
description: Parser for OMIM (Online Mendelian Inheritance in Man) to extract genetic disease data including gene-disease relationships, inheritance patterns, and phenotype mappings from bulk files and optional API enrichment. Use when querying genetic disorders, Mendelian diseases, gene-phenotype associations, or integrating OMIM data into knowledge graphs. Triggers on OMIM, Mendelian inheritance, genetic disease, gene-phenotype mapping, or inherited disorder tasks.
---

# OMIM Genetic Disease Parser

## Overview

OMIM (Online Mendelian Inheritance in Man) is the authoritative compendium of human genes and genetic phenotypes. This parser extracts gene-disease relationships, inheritance patterns, and phenotype mappings from OMIM bulk data files, with optional API enrichment for clinical synopses and variant details.

**Key characteristics:**
- Primary data: bulk TSV files (genemap2.txt, morbidmap.txt)
- Optional API enrichment via api.omim.org (requires API key)
- CVD filtering using project ontology terms
- No rate limit on bulk file parsing; API limit ~4 requests/second

## Quick Start

### Basic Usage (Bulk Files)

```python
from src.parsers import OMIMParser

# Initialize parser
# Reads OMIM_API_KEY from .env if available
parser = OMIMParser()

# Download (with API key) or locate existing files
parser.download_data()

# Parse into DataFrames
data = parser.parse_data()

genemap_df = data['gene_phenotype_map']
diseases_df = data['gene_disease_relationships']
cvd_genes_df = data['omim_cvd_genes']

print(f"Total gene entries: {len(genemap_df)}")
print(f"Gene-disease relationships: {len(diseases_df)}")
print(f"CVD-related genes: {len(cvd_genes_df)}")
```

### With API Enrichment

```python
# Requires OMIM_API_KEY in .env
parser = OMIMParser(use_api_enrichment=True)
parser.download_data()
data = parser.parse_data()

# Enriched DataFrame has additional columns
diseases_df = data['gene_disease_relationships']
print(diseases_df[diseases_df['is_cvd']][
    ['phenotype', 'gene_symbols', 'clinical_synopsis']
].head())
```

### Manual File Placement

If you don't have an API key, place files manually:

```
src/parsers/data/omim/genemap2.txt
src/parsers/data/omim/morbidmap.txt
```

Then run:

```python
parser = OMIMParser()
parser.download_data()  # Will detect existing files
data = parser.parse_data()
```

## Data Files

### genemap2.txt

Tab-separated file with `#`-prefixed comment headers. Contains the OMIM gene map with phenotype associations.

**Key columns:**
- Chromosome, Genomic Position Start/End
- MIM Number (unique OMIM identifier)
- Gene/Locus Symbols, Gene Name, Approved Gene Symbol
- Entrez Gene ID, Ensembl Gene ID
- Phenotypes (semicolon-separated phenotype entries)

### morbidmap.txt

Tab-separated file mapping phenotypes to genes. Each row is one phenotype-gene association.

**Columns:**
- Phenotype (includes name, MIM number, mapping key, inheritance)
- Gene Symbols
- MIM Number (gene)
- Cyto Location

**Phenotype field format:**
```
Long QT syndrome 1, 192500 (3), Autosomal dominant
{Susceptibility to cardiac arrest}, 115080 (3)
Brugada syndrome 1, 601144 (3), Autosomal dominant
```

**Mapping keys:**
| Key | Meaning |
|-----|---------|
| (1) | Gene with known sequence and phenotype |
| (2) | Gene with known sequence |
| (3) | Phenotype mapped to chromosomal location |
| (4) | Deletion/duplication syndrome |

## Output Schema

### gene_phenotype_map DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `mim_number` | String | OMIM MIM number |
| `gene_symbol` | String | Approved gene symbol |
| `gene_name` | String | Full gene name |
| `chromosome` | String | Chromosome |
| `cyto_location` | String | Cytogenetic location |
| `entrez_gene_id` | String | NCBI Entrez gene ID |
| `ensembl_gene_id` | String | Ensembl gene ID |
| `phenotypes_raw` | String | Raw phenotype string from OMIM |
| `source_database` | String | Always "OMIM" |

### gene_disease_relationships DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `phenotype` | String | Disease/phenotype name (cleaned) |
| `phenotype_mim` | String | Phenotype MIM number |
| `gene_symbols` | String | Associated gene symbol(s) |
| `gene_mim` | String | Gene MIM number |
| `cyto_location` | String | Cytogenetic location |
| `mapping_key` | String | Phenotype mapping confidence (1-4) |
| `inheritance` | String | Inheritance pattern (e.g., Autosomal dominant) |
| `is_cvd` | Boolean | Whether phenotype is CVD-related |
| `source_database` | String | Always "OMIM" |

Additional columns when API enrichment is enabled:

| Column | Type | Description |
|--------|------|-------------|
| `clinical_synopsis` | String | Clinical synopsis from OMIM API |
| `allelic_variant_count` | Integer | Number of allelic variants |
| `references_count` | Integer | Number of references |

### omim_cvd_genes DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `gene_symbol` | String | Gene symbol |
| `gene_mim` | String | Gene MIM number |
| `cvd_phenotypes` | String | Semicolon-joined CVD phenotype names |
| `cvd_phenotype_count` | Integer | Number of CVD phenotypes |
| `inheritance_patterns` | String | Unique inheritance patterns |
| `source_database` | String | Always "OMIM" |

## Data Mapping for Knowledge Graphs

### Node Types

| Source Field | Target Node Type | Properties |
|--------------|-----------------|------------|
| `gene_symbol` | Gene | `geneSymbol`, `entrezGeneId`, `ensemblGeneId` |
| `phenotype` | Disease | `diseaseName`, `mimNumber`, `inheritance` |
| `mim_number` | OMIMEntry | `mimNumber`, `cytoLocation` |

### Relationship Mappings

```python
# Gene-Disease causal relationship
gene_disease = {
    'subject': 'gene_symbols',
    'relationship': 'CAUSES_OR_CONTRIBUTES_TO',
    'object': 'phenotype',
    'properties': {'mapping_key', 'inheritance'}
}

# Gene-MIM entry
gene_omim = {
    'subject': 'gene_symbol',
    'relationship': 'HAS_OMIM_ENTRY',
    'object': 'mim_number'
}
```

## CVD-Relevant Genetic Conditions

Key cardiovascular conditions in OMIM:

### Arrhythmias
- Long QT syndrome (LQT1-LQT15): SCN5A, KCNQ1, KCNH2, KCNE1, KCNE2
- Brugada syndrome: SCN5A, CACNA1C, GPD1L
- Catecholaminergic polymorphic VT: RYR2, CASQ2

### Cardiomyopathies
- Hypertrophic cardiomyopathy: MYH7, MYBPC3, TNNT2, TNNI3, TPM1
- Dilated cardiomyopathy: TTN, LMNA, MYH7, SCN5A, TNNT2
- Arrhythmogenic RV cardiomyopathy: PKP2, DSP, DSG2, DSC2

### Lipid Disorders
- Familial hypercholesterolemia: LDLR, APOB, PCSK9, LDLRAP1

### Connective Tissue / Vascular
- Marfan syndrome: FBN1
- Ehlers-Danlos (vascular type): COL3A1
- Aortic aneurysm: TGFBR1, TGFBR2, FBN1, ACTA2

### Congenital Heart Disease
- Holt-Oram syndrome: TBX5
- Noonan syndrome: PTPN11, SOS1, RAF1

## Filtering Examples

### CVD-Related Diseases Only

```python
# Already flagged in the DataFrame
cvd_diseases = diseases_df[diseases_df['is_cvd']]
print(f"CVD gene-disease relationships: {len(cvd_diseases)}")
```

### By Inheritance Pattern

```python
# Autosomal dominant conditions
ad_conditions = diseases_df[
    diseases_df['inheritance'].str.contains('Autosomal dominant', na=False)
]

# Autosomal recessive conditions
ar_conditions = diseases_df[
    diseases_df['inheritance'].str.contains('Autosomal recessive', na=False)
]
```

### By Mapping Confidence

```python
# High-confidence phenotype mappings (key 3 = confirmed locus)
confirmed = diseases_df[diseases_df['mapping_key'] == '3']
```

### Top CVD Genes

```python
# Genes with most CVD phenotypes
cvd_genes_df = data['omim_cvd_genes']
top_genes = cvd_genes_df.sort_values('cvd_phenotype_count', ascending=False)
print(top_genes[['gene_symbol', 'cvd_phenotype_count', 'inheritance_patterns']].head(20))
```

## API Key Setup

To enable automatic file downloads and API enrichment:

1. Request an API key at https://omim.org/api
2. Add to your `.env` file:
   ```
   OMIM_API_KEY=your_api_key_here
   ```

Without an API key, you can still use the parser by manually placing the bulk files in `src/parsers/data/omim/`.

## Caching

API enrichment responses are cached as JSON in `src/parsers/data/omim/cache/`. Cache files are named by MIM number (e.g., `entry_192500.json`).

```python
# API enrichment with caching (default when API key is available)
parser = OMIMParser(use_api_enrichment=True)

# Skip API enrichment even if key is available
parser = OMIMParser(use_api_enrichment=False)
```

## Resources

### External Links
- [OMIM Homepage](https://omim.org/)
- [OMIM API Documentation](https://omim.org/help/api)
- [OMIM Downloads](https://omim.org/downloads)
- [OMIM Gene Map Statistics](https://omim.org/statistics/geneMap)

### References
- Online Mendelian Inheritance in Man, OMIM. McKusick-Nathans Institute of Genetic Medicine, Johns Hopkins University, Baltimore, MD.
- Amberger JS, et al. (2019). OMIM.org: leveraging knowledge across phenotype-gene relationships. Nucleic Acids Research.
