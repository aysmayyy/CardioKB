# CardioKB Known Issues

Last updated: 2026-05-26

## Summary

| Issue | Status | Impact | Priority |
|-------|--------|--------|----------|
| Edge source property missing | Open | 0% source traceability | High |
| High orphan node rates | Open | 703,184 disconnected nodes | Medium |
| Drug cross-source merge 0% | Open | 4,010 duplicate Drug nodes | Medium |
| Jensen TISSUES 0% yield | Deferred | No gene-tissue edges from Jensen | Low |
| ClinVar variant-disease 0.12% yield | Expected | ~3,700 of 3M edges loaded | Documented |
| Download file size thresholds | Config | Some sources flagged incorrectly | Low |
| BaseAgent ista limitation | Known | Edge properties not saved to RDF | Workaround |

---

## 1. Edge Source Property Missing — 0% Coverage

**Status:** Open  
**Discovered:** 2026-05-26 (eval pipeline)  
**Impact:** Cannot trace which database a relationship came from

### Description

All 7,966,293 relationships in the graph are missing the `source` property. This property should identify the originating database (e.g., `source: "DrugBank"`, `source: "STRING"`).

### Data from Live Memgraph

```
Total edges: 7,966,293
Edges with source property: 0
Source coverage: 0.0%
```

### Root Cause

The `memgraph_loader.py` loads relationships using MERGE/CREATE but the `source_label` from ontology configs is not being set as a relationship property during loading.

### Resolution Options

1. **Fix memgraph_loader.py** — Add `source` property in the Cypher MERGE/CREATE statements
2. **Post-load update** — Run `MATCH ()-[r:TYPE]->() SET r.source = 'SourceName'` for each type
3. **Re-run pipeline** — After fixing loader, re-run full pipeline

### Files Affected

- `src/memgraph_loader.py` — Needs to set `r.source` from config's `source_label`
- `src/ontology_configs.py` — Has `source_label` defined for each relationship config

---

## 2. High Orphan Node Rates

**Status:** Open  
**Discovered:** 2026-05-26 (eval pipeline)  
**Impact:** 703,184 nodes (27.4%) have no connections

### Description

Many node types have extremely high orphan rates — nodes that exist but have no relationships connecting them to the rest of the graph.

### Data from Live Memgraph

| Node Type | Total | Orphans | Orphan Rate |
|-----------|-------|---------|-------------|
| Symptom | 415 | 415 | **100%** |
| DrugLabel | 29 | 29 | **100%** |
| Disease | 3,442 | 3,228 | **93.8%** |
| BodyPart | 1,400 | 1,217 | **86.9%** |
| Gene | 318,795 | 276,781 | **86.8%** |
| Drug | 43,596 | 24,834 | **57.0%** |
| CellularComponent | 4,076 | 2,240 | **55.0%** |
| BiologicalProcess | 24,428 | 13,279 | **54.4%** |
| MolecularFunction | 10,056 | 5,274 | **52.4%** |
| Phenotype | 19,389 | 10,160 | **52.4%** |
| ClinicalTrial | 21,578 | 11,178 | **51.8%** |
| Variant | 2,100,938 | 354,222 | **16.9%** |
| SideEffect | 4,251 | 274 | **6.5%** |
| Pathway | 2,870 | 51 | **1.8%** |
| GeneFamily | 4,257 | 2 | **0.05%** |
| TranscriptionFactor | 1,203 | 0 | **0%** |
| PharmacologicClass | 2,359 | 0 | **0%** |

**Total orphan nodes: 703,184 of 2,563,082 (27.4%)**

### Root Causes

1. **Symptom (100%)** — No relationship mappings defined for Symptom nodes (MEDLINE cooccurrence removed)
2. **DrugLabel (100%)** — ClinPGx drug labels have no outgoing edges defined
3. **Disease (93.8%)** — Only 214 diseases have variant associations; most are ontology terms without data
4. **Gene (86.8%)** — Many genes are from NCBI Gene full dump but have no relationships in CVD context
5. **BodyPart (86.9%)** — Only 183 body parts have Bgee expression data

### Resolution Options

1. **Add missing relationship mappings** — Define edges for Symptom, DrugLabel
2. **Filter node imports** — Only import nodes that will have relationships
3. **Accept as limitation** — Document that ontology completeness > graph density
4. **Post-load cleanup** — Delete orphan nodes with `MATCH (n) WHERE NOT (n)--() DELETE n`

### Files Affected

- `src/ontology_configs.py` — Relationship configs for orphan types
- `config/ontology_mappings.yaml` — Same configs in YAML format

---

## 3. Drug Cross-Source Merge — 0% Merge Rate

**Status:** Open  
**Discovered:** 2026-05-26  
**Impact:** 4,010 duplicate Drug nodes (DrugCentral + DrugBank)

### Description

DrugCentral and DrugBank both contribute Drug nodes. When a DrugCentral drug has a `drugbank_id`, it should merge with the corresponding DrugBank node. Currently, they are created as separate nodes.

### Data Analysis

| Source | Drugs | With drugbank_id |
|--------|-------|------------------|
| DrugCentral | 4,995 | 4,010 |
| DrugBank | 16,628 | 16,628 (all) |
| CTD | 9,465 | 0 |
| **Total in graph** | **43,596** | — |
| **Expected after merge** | **~39,586** | — |
| **Potential duplicates** | **4,010** | — |

### Example Duplicate

| Node ID | Drug Name | xrefDrugBank |
|---------|-----------|--------------|
| `DrugCentral:4` | levobupivacaine | DB01002 |
| `DrugBank:DB01002` | Levobupivacaine | DB01002 |

These represent the same drug but exist as separate nodes.

### Root Cause

**Config mismatch between YAML and Python configs:**

- `ontology_mappings.yaml` (used by TSV exporter):
  ```yaml
  id_column: struct_id
  id_prefix: DrugCentral
  ```

- `ontology_configs.py` (used by Memgraph loader):
  ```python
  'iri_column_name': 'drugbank_id',
  'iri_fallback_column': 'struct_id',
  'iri_fallback_prefix': 'DC:',
  ```

The TSV exporter doesn't support IRI fallback logic, so it always uses `DrugCentral:{struct_id}`.

### Resolution Options

1. **Add iri_fallback to YAML config format** — Extend ontology_mappings.yaml to support fallback IDs
2. **Add iri_fallback to TSV exporter** — Modify `src/export/tsv_exporter.py` to handle fallback logic
3. **Post-process merge** — Add a deduplication step that merges nodes by xref
4. **Change DrugCentral ID strategy** — Use drugbank_id as primary when available (requires parser change)

### Files Affected

- `config/ontology_mappings.yaml` — DrugCentral drugs config
- `src/export/tsv_exporter.py` — Needs iri_fallback support
- `data/output/nodes_Drug.csv` — Contains duplicates

---

## 4. Jensen TISSUES — 0% Edge Yield

**Status:** Deferred (skipped in config)  
**Discovered:** 2026-05-26  
**Impact:** No `geneExpressedInBodyPart` edges from Jensen TISSUES source

### Description

Jensen TISSUES data uses BTO (BRENDA Tissue Ontology) identifiers for tissues, but CardioKB's BodyPart nodes use Uberon identifiers. These are completely different ontologies with zero ID overlap.

### Data Analysis

| Source | ID Format | Example | Count |
|--------|-----------|---------|-------|
| Jensen TISSUES | BTO | `BTO:0000042` | 398,361 rows |
| BodyPart nodes | Uberon | `UBERON:0000002` | 1,400 nodes |

**Overlap:** 0 IDs match between BTO and Uberon namespaces.

### Root Cause

BTO and Uberon are independent anatomy ontologies. BTO is focused on tissues/cell types for enzyme research; Uberon is a cross-species anatomy ontology. Without a BTO→Uberon mapping file, these cannot be reconciled.

### Current Workaround

Set `skip: true` in `config/ontology_mappings.yaml` for `jensen_tissues.tissue_gene_associations`.

### Resolution Options

1. **Create BTO→Uberon mapping file** — Build or obtain a cross-reference mapping between BTO and Uberon IDs (most accurate)
2. **Fuzzy name matching** — Match by tissue name instead of ID (lossy, may have false matches)
3. **Replace Uberon with BTO** — Use BTO for all anatomy nodes (loses Uberon cross-references)
4. **Accept limitation** — Document that Jensen TISSUES is incompatible with current schema

### Files Affected

- `config/ontology_mappings.yaml` — `jensen_tissues.tissue_gene_associations` set to skip
- `data/processed/jensen_tissues/tissue_gene_associations.tsv` — Source data (not loaded)

---

## 5. ClinVar Variant-Disease — 0.12% Edge Yield

**Status:** Expected behavior (documented)  
**Discovered:** 2026-05-26  
**Impact:** Only 3,728 of 2,990,118 variant-disease associations loaded

### Description

ClinVar variant-disease associations use UMLS CUI identifiers to reference diseases. These must match Disease nodes via the `xrefUmlsCUI` property. However, only a small fraction of UMLS CUIs have corresponding entries in Disease Ontology.

### Data Analysis

| Metric | Count |
|--------|-------|
| ClinVar source rows | 2,990,118 |
| Unique UMLS CUIs in ClinVar | 8,620 |
| Disease nodes with xrefUmlsCUI | 1,691 |
| **Overlapping CUIs** | **212** |
| Resulting edges | 3,728 |

**Yield:** 0.12% (3,728 / 2,990,118)

### Root Cause

Disease Ontology (DOID) only has UMLS cross-references for ~1,691 of its 3,442 diseases, and most ClinVar diseases reference conditions not in Disease Ontology's coverage.

### Resolution Applied

Added per-mapping threshold override in config:
```yaml
clinvar.variant_disease_associations:
  min_yield_threshold: 0.001  # Expected low yield due to CUI overlap limitation
```

### Files Affected

- `config/ontology_mappings.yaml` — Added `min_yield_threshold: 0.001`
- `src/parsers/clinvar_parser.py` — Extracts UMLS CUI from MedGen IDs

---

## 6. Download File Size Thresholds

**Status:** Configuration issue  
**Discovered:** 2026-05-26 (eval pipeline)  
**Impact:** Some sources incorrectly flagged as failures in eval_download.py

### Description

The `eval_download.py` script has hardcoded minimum file size thresholds that are too aggressive for some sources, causing false positive failures.

### Affected Sources

| Source | Expected Size | Actual Size | Status |
|--------|--------------|-------------|--------|
| bgee | 1,000 MB | 174 MB | FALSE FAIL |
| string | 100 MB | varies | May fail |
| clinvar | 500 MB | varies | May fail |
| ncbigene | 50 MB | varies | Usually OK |

### Root Cause

The thresholds in `MIN_FILE_SIZES` dict were estimated conservatively but some sources have smaller files after filtering or compression.

### Resolution

Adjust thresholds in `eval/eval_download.py`:
```python
MIN_FILE_SIZES = {
    "default": 1000,  # 1KB minimum
    "bgee": 100_000_000,  # Reduced from 1GB to 100MB
    # ... etc
}
```

Or use `--skip download` when running the eval pipeline.

### Files Affected

- `eval/eval_download.py` — `MIN_FILE_SIZES` dictionary

---

## 7. BaseAgent ista Limitation — Edge Properties Not Saved

**Status:** Known limitation (workaround in place)  
**Discovered:** 2026-05-26  
**Impact:** Cannot use BaseAgent's standard populate→export pipeline for edge properties

### Description

The `ista` Python package (OntologyPopulator) used by BaseAgent processes individuals and relationships but does not serialize them to the output RDF file. Only the ontology schema (classes, properties) is saved.

### Evidence

After running `python src/main.py --step populate`:
- Log shows "Processed 2,990,118 relationships"
- Output RDF contains only 1,364 triples (schema only)
- `--step export` produces 0 nodes, 0 edges

### Root Cause

The ista package populates an in-memory RDF graph but `save_ontology()` only serializes schema elements, not data individuals/relationships.

### Current Workaround

CardioKB uses a direct TSV→Memgraph loading approach via `src/memgraph_loader.py`, bypassing the RDF intermediate format entirely. This preserves all edge properties.

### Files Affected

- `src/memgraph_loader.py` — Direct loader (workaround)
- `src/ontology_configs.py` — Python configs used by direct loader
- `src/main.py` — Has both BaseAgent pipeline and direct loading paths

---

## Resolved Issues

### ID Format Mismatch Between Node and Edge CSVs

**Status:** Resolved  
**Discovered:** 2026-05-19  
**Resolved:** 2026-05-20

**Original Issue:** Edge CSVs used inconsistent ID formats that didn't match node IDs.

**Resolution:** Rewrote `TSVMemgraphExporter` with comprehensive lookup tables that resolve various identifier types (geneId, geneSymbol, xrefDrugBank, etc.) back to canonical node IDs. Edge yield is now 10-100% for most mappings.

---

## Eval Pipeline Results (2026-05-26)

### Live Memgraph Statistics

```
Total nodes: 2,563,082
Total edges: 7,966,293
Node labels: 17
Relationship types: 24
Source labels: 0
LCC fraction: 72.56%
```

### Stage Results

| Stage | Status | Metrics | Tier 1 Failures |
|-------|--------|---------|-----------------|
| download | FAIL | 123 | 8 (file size thresholds) |
| parser | PASS | 245 | 0 |
| load | PASS | 59 | 0 |
| graph | PASS | 85 | 0 |

### High-Degree Nodes (Top 5)

| Label | ID | Degree |
|-------|-----|--------|
| Gene | NCBIGene:7273 | 33,912 |
| BodyPart | UBERON:0000178 | 30,029 |
| BodyPart | UBERON:0001323 | 29,595 |
| BodyPart | UBERON:0001388 | 29,514 |
| BodyPart | UBERON:0001161 | 28,945 |
