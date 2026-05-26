# CardioKB Evaluation Report
Generated: 2026-05-19 12:17:20

## Summary
- **Total Nodes:** 2,411,112
- **Total Edges:** 11,625,273
- **Node Types:** 17
- **Edge Types:** 25

## Within-Source Merge Rate Analysis

Raw records parsed vs unique IDs after internal deduplication.

| Source | Raw Records | Unique IDs | Duplicates | Merge Rate |
|--------|------------:|-----------:|-----------:|-----------:|
| clinicaltrials | 21,578 | 21,578 | 0 | 100.0% |
| clinpgx | 29 | 29 | 0 | 100.0% |
| clinvar | 2,100,938 | 2,100,938 | 0 | 100.0% |
| collectri | 1,201 | 1,201 | 0 | 100.0% |
| ctd | 9,465 | 9,465 | 0 | 100.0% |
| disease_ontology | 3,442 | 3,442 | 0 | 100.0% |
| dorothea | 367 | 367 | 0 | 100.0% |
| drugbank | 16,628 | 16,628 | 0 | 100.0% |
| drugcentral | 7,354 | 7,354 | 0 | 100.0% |
| gene_ontology | 38,560 | 38,560 | 0 | 100.0% |
| hgnc | 4,257 | 4,257 | 0 | 100.0% |
| hpo | 19,389 | 19,389 | 0 | 100.0% |
| mesh | 415 | 415 | 0 | 100.0% |
| ncbigene | 193,795 | 193,795 | 0 | 100.0% |
| reactome | 2,870 | 2,870 | 0 | 100.0% |
| sider | 4,251 | 4,251 | 0 | 100.0% |
| uberon | 1,400 | 1,400 | 0 | 100.0% |

## Cross-Source Merge Rate Analysis

For node types with multiple contributing sources, shows overlap and merge success.

### Drug

**Sources:** drugcentral, ctd, drugbank

| Source | Unique IDs | ID Column | Cross-Refs |
|--------|----------:|-----------|------------|
| drugcentral | 4,995 | struct_id | xrefMeSH, drugbank_id, mesh_id |
| ctd | 9,465 | chemical_id | xrefMeSH, mesh_id |
| drugbank | 16,628 | drugbank_id | drugbank_id |

| Metric | Value |
|--------|------:|
| Sum unique per source | 31,088 |
| Union of all IDs | 31,088 |
| Final graph nodes | 16,628 |
| Potential duplicates | 4,010 |
| **Cross-merge rate** | **100.0%** |

**Detected Overlaps:**
- drugcentral ∩ drugbank via drugbank_id: 4,010 (99.73% of smaller)

### TranscriptionFactor

**Sources:** dorothea, collectri

| Source | Unique IDs | ID Column | Cross-Refs |
|--------|----------:|-----------|------------|
| dorothea | 367 | tf_symbol | - |
| collectri | 1,201 | tf_symbol | - |

| Metric | Value |
|--------|------:|
| Sum unique per source | 1,568 |
| Union of all IDs | 1,203 |
| Final graph nodes | 1,201 |
| Potential duplicates | 365 |
| **Cross-merge rate** | **100.0%** |

**Detected Overlaps:**
- dorothea ∩ collectri (primary ID): 365 (99.46% of smaller)

## ✅ No Merge Issues Detected

All sources show proper deduplication both within-source and cross-source.