---
name: aopdb-parser
description: Parser for AOP-DB (Adverse Outcome Pathway Database), the EPA's MySQL database containing adverse outcome pathways, key events, stressors, chemicals, genes, diseases, and biological pathways. Use when parsing AOP-DB data, querying the database, extracting pathway-gene relationships, chemical-stressor mappings, or integrating AOP data into knowledge graphs. Triggers on AOP-DB, adverse outcome pathway, toxicological pathway parsing, or EPA pathway database tasks.
---

# AOP-DB Parser

## Overview

AOP-DB (Adverse Outcome Pathway Database) is an EPA MySQL database that integrates adverse outcome pathway information with gene, chemical, disease, and pathway data to characterize toxicological outcomes relevant to human health and the environment.

**Key characteristics:**
- MySQL database (InnoDB, version 5.6.36+)
- 16+ interconnected tables linked through gene identifiers
- Primary data source: AOP-Wiki 2.0 XML (quarterly updates)
- Download: https://gaftp.epa.gov/EPADataCommons/ORD/AOP-DB/ (~7.2 GB compressed)

## Quick Start

### Connection Setup

```python
import mysql.connector

mysql_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'aopdb'
}

conn = mysql.connector.connect(**mysql_config)
```

### Common Queries

**Get all AOPs:**
```sql
SELECT * FROM aop_info;
```

**Get pathways with genes (human only):**
```sql
SELECT DISTINCT path_id, path_name, entrez, ext_source
FROM pathway_gene
WHERE tax_id = 9606;
```

**Get chemical/stressor information:**
```sql
SELECT * FROM chemical_info;
-- or
SELECT * FROM stressor_info;
```

## Database Schema

See [references/schema.md](references/schema.md) for complete table definitions.

### Core Tables

| Table | Description | Key Columns |
|-------|-------------|-------------|
| `aop_info` | AOP metadata | `AOP_id`, `AOP_name`, `AOP_description` |
| `aop_gene` | AOP-gene associations | `AOP_id`, `entrez`, `gene_symbol` |
| `aop_stressor` | AOP-chemical links | `AOP_id`, `stressor_id`, `DTXSID` |
| `stressor_info` | Stressor metadata | `stressor_id`, `stressor_name`, `CASRN`, `DTXSID` |
| `chemical_info` | Chemical details | `ChemicalID`, `DTX_id`, `chemical_name` |
| `event_info` | Key events (KE) | `event_id`, `event_name`, `ke_type` |
| `ke_gene` | KE-gene links | `event_id`, `entrez`, `gene_symbol` |
| `pathway_gene` | Pathway-gene associations | `path_id`, `path_name`, `entrez`, `tax_id`, `ext_source` |
| `disease_gene` | Disease-gene links | `disease_id`, `disease_name`, `entrez` |
| `gene_info` | Gene metadata | `entrez`, `gene_symbol`, `gene_name`, `tax_id` |
| `assay_gene` | ToxCast assay targets | `assay_id`, `entrez`, `assay_name` |

### Entity Relationships

```
AOP ──┬── aop_gene ─── Gene ─── pathway_gene ─── Pathway
      │                  │
      │                  ├─── disease_gene ─── Disease
      │                  │
      │                  └─── assay_gene ─── ToxCast Assay
      │
      └── aop_stressor ─── Stressor/Chemical
```

## Parsing Workflow

### 1. Extract AOPs

```python
query = "SELECT * FROM aop_info"
aops_df = pd.read_sql(query, connection)
aops_df['source_database'] = 'AOPDB'
```

### 2. Extract Pathways (Deduplicated)

```python
query = """
    SELECT path_name,
        GROUP_CONCAT(DISTINCT path_id) as path_id,
        CONCAT('AOPDB - ', GROUP_CONCAT(DISTINCT ext_source)) as ext_source
    FROM (
        SELECT DISTINCT path_id,
            TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(path_name,
                '<sub>', ''), '</sub>', ''), '<i>', ''), '</i>', ''),
                ' - Homo sapiens (human)', '')) as path_name,
            ext_source
        FROM pathway_gene
        WHERE tax_id = 9606
    ) data
    GROUP BY path_name;
"""
pathways_df = pd.read_sql(query, connection)
```

### 3. Extract Gene-Pathway Relationships

```python
query = """
    SELECT DISTINCT entrez, path_id,
        TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(path_name,
            '<sub>', ''), '</sub>', ''), '<i>', ''), '</i>', ''),
            ' - Homo sapiens (human)', '')) as path_name
    FROM pathway_gene
    WHERE tax_id = 9606;
"""
gene_pathway_df = pd.read_sql(query, connection)
```

### 4. Extract Chemicals/Drugs

```python
query = "SELECT * FROM chemical_info"
chemicals_df = pd.read_sql(query, connection)
```

## Data Mapping for Knowledge Graphs

### Output Schema

| AOP-DB Entity | Target Node Type | Key Properties |
|---------------|-----------------|----------------|
| `aop_info` | AOP | `aop_id`, `aop_name` |
| `pathway_gene` (pathways) | Pathway | `path_id`, `path_name`, `ext_source` |
| `pathway_gene` (relationships) | geneInPathway | `entrez` → `path_name` |
| `chemical_info` | Drug | `DTX_id` (xrefDTXSID), `ChemicalID` (xrefMeSH) |

### Property Mappings

```python
# Drugs from chemical_info
drug_mapping = {
    'DTX_id': 'xrefDTXSID',       # DSSTox ID
    'ChemicalID': 'xrefMeSH',     # MeSH identifier
    'source_database': 'sourceDatabase'
}

# Pathways from pathway_gene
pathway_mapping = {
    'path_id': 'pathwayId',
    'path_name': 'pathwayName',
    'ext_source': 'sourceDatabase'
}

# Gene-Pathway relationships
relationship_mapping = {
    'subject_column': 'entrez',          # Entrez gene ID
    'subject_match': 'xrefNcbiGene',
    'object_column': 'path_name',
    'object_match': 'pathwayName'
}
```

## Data Sources Integrated in AOP-DB

| Source | Data Type | Description |
|--------|-----------|-------------|
| AOP-Wiki | AOPs, KEs, KERs | Primary AOP definitions |
| CTD | Chemical-Gene | Comparative Toxicogenomics Database |
| ConsensusPathDB | Pathways | Integrated pathway database |
| KEGG | Pathways | Kyoto Encyclopedia of Genes and Genomes |
| Reactome | Pathways | Curated pathway database |
| DisGeNET | Disease-Gene | Disease-gene associations |
| ToxCast | Assay-Gene | High-throughput screening data |
| Homologene | Orthologs | Cross-species gene mapping |
| HumanBase | Tissue-Gene | Tissue-specific expression |
| DSSTox | Chemicals | EPA chemical identifiers |

## Key Identifiers

| ID Type | Format | Example | Used In |
|---------|--------|---------|---------|
| AOP ID | Integer | `1`, `42`, `320` | `aop_info`, `aop_gene` |
| Entrez | Integer | `7157`, `1956` | Gene tables |
| DTXSID | `DTXSID\d+` | `DTXSID7020182` | Chemical tables |
| MeSH | `D\d+` | `D000068` | `chemical_info` |
| Path ID | String | `hsa04110`, `R-HSA-123` | `pathway_gene` |
| Tax ID | Integer | `9606` (human) | Species filtering |

## Resources

### references/
- [schema.md](references/schema.md) - Complete database schema with all table columns

### External Resources
- [EPA AOP-DB Website](https://www.epa.gov/healthresearch/adverse-outcome-pathway-database-aop-db)
- [AOP-Wiki](https://aopwiki.org/)
- [Data Download (EPA FTP)](https://gaftp.epa.gov/EPADataCommons/ORD/AOP-DB/)
- [2021 Publication (Nature Scientific Data)](https://www.nature.com/articles/s41597-021-00962-3)
