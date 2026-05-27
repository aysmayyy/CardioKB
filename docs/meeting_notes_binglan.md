# CardioKB Meeting Notes — Binglan

**Date:** 2026-05-28  
**Prepared:** 2026-05-27  
**Topic:** CardioKB pipeline status, edge properties issue, and BaseAgent workflow clarification

---

## Current State of CardioKB

### Graph Statistics (Live Memgraph)
- **2,563,082 nodes** across 17 node types
- **7,966,293 relationships** across 24 relationship types
- **24 data sources** integrated (vs. 18 in BaseAgent template)
- **72.6% LCC fraction** (largest connected component)

### Data Sources Implemented
- **18 adapted from BaseAgent template:** NCBI Gene, DoRothEA, DrugBank, Disease Ontology, Gene Ontology, Uberon, MeSH, DrugCentral, BindingDB, CTD, Bgee, STRING, Reactome, MEDLINE, SIDER, LINCS L1000, PubTator, Jensen TISSUES
- **6 written from scratch:** ClinicalTrials.gov, ClinPGx, OpenTargets, HPO, HGNC Families, ClinVar

---

## What I've Fixed

### 1. ista RDF Serialization Limitation (Workaround)
**Problem:** The `ista` package's `OntologyPopulator` processes relationships in memory but `save_ontology()` only serializes schema elements, not data individuals/relationships. Running `--step populate` followed by `--step export` produces 0 nodes and 0 edges.

**Solution:** Implemented a **direct TSV→Memgraph loading approach** that bypasses RDF entirely:
- Created `src/ontology_configs.py` — 86 Python configs mapping source data to graph schema
- Created `src/memgraph_loader.py` — Cypher-based batch loader that reads TSVs directly
- Added `--step load` and `--skip-download` flags to `main.py`

**Working pipeline:**
```bash
python src/main.py                    # Full: extract → TSV → Memgraph
python src/main.py --skip-download    # Use existing TSVs → Memgraph
python src/main.py --step load        # Just reload into Memgraph
```

### 2. ID Format Mismatch Between Node and Edge CSVs
**Problem:** Edge CSVs used inconsistent ID formats that didn't match node IDs (e.g., gene symbols vs. NCBI IDs).

**Solution:** Rewrote `TSVMemgraphExporter` with comprehensive lookup tables that resolve various identifier types (geneId, geneSymbol, xrefDrugBank, etc.) back to canonical node IDs. Edge yield is now 10-100% for most mappings.

### 3. ClinVar Low Yield (Documented)
**Problem:** Only 0.12% of ClinVar variant-disease associations load (3,728 of 2.9M).

**Resolution:** This is expected — UMLS CUI overlap between ClinVar and Disease Ontology is only 212 CUIs. Added `min_yield_threshold: 0.001` in config to suppress false failure alerts.

---

## TSV Edge Property Audit

I checked 6 relationship TSV files to see what properties are available beyond start/end node IDs:

| Source | TSV File | Columns | Edge Properties Available |
|--------|----------|---------|---------------------------|
| **DrugBank** | `drug_gene_edges.tsv` | drugbank_id, gene_symbol, uniprot_id, interaction_type, source_database | `interaction_type` (target/enzyme/carrier/transporter) |
| **STRING** | `gene_interactions.tsv` | gene_id_1, gene_id_2, combined_score, source_database | `combined_score` (confidence 0-1000) |
| **BindingDB** | `drug_binds_gene.tsv` | drugbank_id, target_name, source_database | None (only IDs) |
| **CTD** | `chemical_increases_expression.tsv` | chemical_id, gene_id, interaction_text, organism, pubmed_ids, source_database | `interaction_text`, `organism`, `pubmed_ids` |
| **ClinVar** | `variant_disease_associations.tsv` | variant_id, disease_id, umls_cui, clinical_significance, source_database | `clinical_significance` (Pathogenic/Benign/etc.) |
| **DoRothEA** | `tf_gene_interactions.tsv` | tf_symbol, target_gene, tf_uniprot, target_uniprot, confidence, curation_effort, mode_of_regulation, mor_score, is_directed, relationship, source_database | `confidence` (A-E), `mor_score` (-1/0/1), `mode_of_regulation`, `curation_effort` |
| **Bgee** | `gene_expression.tsv` | uberon_id, ensembl_gene_id, expression_call, call_quality, fdr, expression_score, expression_rank, source, unbiased, sourceDatabase | `expression_score`, `expression_rank`, `fdr`, `call_quality` |

**Key finding:** The TSVs **do contain edge properties** — the parsers are extracting them correctly. The issue is that `memgraph_loader.py` isn't mapping these columns to relationship properties during graph loading.

**Properties we're losing:**
- STRING `combined_score` — interaction confidence
- DoRothEA `mor_score`, `confidence` — transcription factor regulation strength
- Bgee `expression_score`, `expression_rank` — gene expression levels
- CTD `pubmed_ids` — literature evidence
- ClinVar `clinical_significance` — variant pathogenicity
- DrugBank `interaction_type` — drug-gene relationship type

**All TSVs have `source_database` column** — this should map to `r.source` on relationships.

---

## What's Still Open

### 1. Edge Properties Not Loading — 0% Coverage (HIGH PRIORITY)
**Problem:** All 7,966,293 relationships are missing properties that exist in the source TSVs:
- `source` property (0% coverage) — cannot trace which database a relationship came from
- `combined_score`, `mor_score`, `expression_score`, etc. — valuable metadata not loaded

**Root cause:** `memgraph_loader.py` creates relationships with only start/end node IDs. It doesn't:
1. Set `r.source` from the `source_database` column (present in all TSVs)
2. Map additional property columns to relationship properties

**Impact:** Losing scientific metadata that's already parsed and available in TSVs.

**Files affected:**
- `src/memgraph_loader.py` — needs to set relationship properties during MERGE/CREATE
- `src/ontology_configs.py` — needs `edge_properties` mapping for each relationship type

### 2. High Orphan Node Rates — 27.4% (703,184 nodes)
| Node Type | Orphan Rate | Reason |
|-----------|-------------|--------|
| Symptom | 100% | No relationship mappings defined |
| DrugLabel | 100% | ClinPGx labels have no outgoing edges |
| Disease | 93.8% | Only 214 have variant associations |
| Gene | 86.8% | Full NCBI dump but CVD-filtered relationships |

### 3. Drug Cross-Source Merge — 0% Merge Rate
**Problem:** 4,010 DrugCentral drugs have `drugbank_id` but exist as separate nodes from DrugBank entries.

**Root cause:** TSV exporter doesn't support IRI fallback logic that Python configs have.

### 4. Jensen TISSUES — 0% Edge Yield (Deferred)
**Problem:** BTO tissue IDs (Jensen) vs. Uberon IDs (our BodyPart nodes) — zero overlap.

**Status:** Skipped in config. Would need BTO→Uberon mapping file to resolve.

---

## Questions for Binglan

### On the ista/RDF Limitation

1. **Is my understanding correct** that `ista`'s `save_ontology()` doesn't serialize data individuals and relationships to RDF, only schema? If so, how does alzkb-updater handle this?

2. **Your workflow suggestion** was `python src/main.py --step populate` then `--step export`. In alzkb-updater, does this actually produce populated graph data with edge properties? If so, what's different about your setup?

3. **Is there a different ista configuration or method** that does serialize individuals/relationships, or is the direct loader approach (bypassing RDF) the intended workaround?

### On Edge Properties

4. **In alzkb-updater, where do edge properties (like `morScore`, `confidence`, `expressionScore`) get preserved?** Is it in the RDF intermediate, or do you also use a direct loading approach?

5. **For the `source` property on relationships** — is this something you handle in the populate step, the export step, or during graph loading?

### On Architecture

6. **Why maintain both YAML (`ontology_mappings.yaml`) and Python (`ontology_configs.py`) configs?** In CardioKB I've diverged — Python configs drive the Memgraph loader while YAML drives the (non-functional) RDF path. Should I consolidate?

7. **Is alzkb-updater the canonical reference** for how to use BaseAgent to build a production KG, or is BaseAgent's template/ directory the primary source of truth?

### On Specific Issues

8. **Drug node deduplication** — DrugCentral drugs with `drugbank_id` should merge with DrugBank nodes. Does alzkb-updater handle this, and if so, how?

9. **Orphan nodes** — Do you filter node imports to only include nodes that will have relationships, or accept high orphan rates as an ontology completeness tradeoff?

---

## Summary for Discussion

| Area | Status | Blocking? |
|------|--------|-----------|
| Pipeline working | Yes (direct loader) | No |
| Nodes loading | Yes (2.5M) | No |
| Edges loading | Yes (7.9M) | No |
| Edge properties (scores, confidence) | **No (0%)** | **Yes** |
| Edge `source` property | **No (0%)** | **Yes** |
| Node deduplication | No | Medium |
| Orphan cleanup | No | Low |

**Main blocker:** Understanding if my direct loader approach is correct, or if there's a way to make the standard BaseAgent populate→export path work with edge properties.
