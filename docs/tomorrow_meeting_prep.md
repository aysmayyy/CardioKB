# CardioKB Meeting Prep — Binglan

**Meeting Date:** 2026-05-28  
**Prepared:** 2026-05-27  
**Status:** Ready for review

---

## What Binglan Has Ready

Based on her confirmation and the recent BaseAgent commits, Binglan has pushed fixes for:

### 1. Edge Properties Fix
**Commit:** `feat(memgraph_exporter): add support for edge properties`

**How it works:**
- `populator.py` now calls `_collect_edge_props()` during `populate_relationships()`
- Edge properties are stored in memory (`self._pending_edge_props`)
- `save_ontology()` writes sidecar CSV files: `edge_props_{rel_type}.csv`
- `memgraph_exporter.py` checks for these sidecars and includes properties in export

**What this solves:**
- `r.source` property (0% → should be 100%)
- `combinedScore` (STRING), `morScore`/`confidence` (DoRothEA), `expressionScore` (Bgee)
- `clinical_significance` (ClinVar), `pubmed_ids` (CTD), `interactionType` (DrugBank)

### 2. Drug Merge Logic Fix
**Commit:** `fix(ontology-mappings): fix merge logic errors`

**What this likely solves:**
- DrugCentral drugs with `drugbank_id` should now merge with DrugBank nodes
- Expected reduction: ~4,010 duplicate Drug nodes eliminated

### 3. Other Recent Fixes
- `fix(ontology): update project configuration with all existing but not used classes and properties`
- `feat(disgenet): consolidate the extraction of diseases`
- `feat(disease-ontology): add support for disease ontology mappings with additional cross-references`

---

## Current CardioKB State (Bring to Meeting)

### Graph Statistics
| Metric | Current Value |
|--------|---------------|
| Total nodes | 2,563,082 |
| Total edges | 7,966,293 |
| Node types | 17 |
| Relationship types | 24 |
| LCC fraction | 72.6% |
| Orphan nodes | 703,184 (27.4%) |

### Edge Property Coverage (BEFORE fix)
| Property | Coverage | Affected Sources |
|----------|----------|------------------|
| `r.source` | 0% | ALL (7.9M edges) |
| `combinedScore` | 0% | STRING (121K edges) |
| `morScore`, `confidence` | 0% | DoRothEA (13K edges) |
| `expressionScore` | 0% | Bgee (786K edges) |
| `clinical_significance` | 0% | ClinVar (2.3M edges) |
| `interactionType` | 0% | DrugBank (12K edges) |

### Data Sources Implemented (24 total)
**From BaseAgent template (18):** NCBI Gene, DoRothEA, DrugBank, Disease Ontology, Gene Ontology, Uberon, MeSH, DrugCentral, BindingDB, CTD, Bgee, STRING, Reactome, MEDLINE, SIDER, LINCS L1000, PubTator, Jensen TISSUES

**Written from scratch (6):** ClinicalTrials.gov, ClinPGx, OpenTargets, HPO, HGNC Families, ClinVar

### Architecture Divergence
| Aspect | BaseAgent Template | My CardioKB |
|--------|-------------------|-------------|
| Config format | YAML only (`ontology_mappings.yaml`) | YAML + Python (`ontology_configs.py`) |
| Loading approach | ista → RDF → export → Memgraph | Direct TSV → Memgraph via `memgraph_loader.py` |
| Parsers | 18 | 24 (6 custom) |
| Edge property handling | Sidecar CSV workaround | Not implemented (why edges have no props) |

---

## Binglan's Latest Feedback (2026-05-27)

**Key confirmation:** Binglan has confirmed that **ista should be used properly and not worked around** — it handles ID mismatches natively. The direct loader approach (TSV → Memgraph via `memgraph_loader.py`) is the root cause of edge property issues. Rather than patching the direct loader, the path forward is to align with the standard ista/RDF pipeline that BaseAgent uses.

**Implication:** Architecture questions (#7, #8) are partially answered — the direct loader was a workaround that introduced problems ista was designed to solve. Meeting should focus on how to migrate back to the ista pipeline while preserving the 6 custom parsers.

---

## Questions to Ask Binglan

### On Adapting the Edge Properties Fix

1. **Can I adapt just the edge property sidecar approach** without switching back to the full ista/RDF pipeline? My direct loader already has the infrastructure (`data_property_map` in configs, SET clause generation) — I just need to understand where properties are getting lost.

2. **In the sidecar CSV approach, does `_collect_edge_props()` re-read the entire TSV file?** If so, is there a more efficient approach for large files (ClinVar has 2.9M rows)?

3. **Should I port the sidecar logic to my `memgraph_loader.py`**, or is there a simpler fix since my loader already generates Cypher SET clauses for properties?

### On the Drug Merge Fix

4. **What specific change fixed drug merging?** Is it:
   - A change in ID column priority (drugbank_id before struct_id)?
   - A MERGE vs CREATE change?
   - A cross-reference matching change?

5. **Does the fix require re-parsing DrugCentral data**, or can I apply it to existing TSVs?

6. **How does alzkb-updater handle the DrugCentral/DrugBank merge?** Can I see the specific config?

### On Architecture

7. **Is my direct loader approach (TSV → Memgraph, bypassing RDF) acceptable**, or should I switch back to the standard BaseAgent pipeline? The direct approach was my workaround for ista not serializing data to RDF.

8. **Should I consolidate to YAML-only configs** (like BaseAgent template) or keep my Python `ontology_configs.py`? The Python configs are more flexible but create maintenance burden.

9. **For my 6 custom parsers** (ClinicalTrials, ClinPGx, OpenTargets, HPO, HGNC Families, ClinVar) — should I contribute these back to BaseAgent, or keep them CardioKB-specific?

### On Known Issues

10. **Orphan nodes (27.4%)** — Is this acceptable, or should I filter imports to only include nodes that will have relationships? AlzKB's orphan rate would be useful for comparison.

11. **Jensen TISSUES (0% yield)** — BTO vs Uberon ID mismatch. Does alzkb-updater have a BTO→Uberon mapping, or did you skip Jensen TISSUES too?

12. **ClinVar low yield (0.12%)** — UMLS CUI overlap limitation. Is this expected, or is there a better way to map ClinVar diseases?

### On Workflow

13. **"Adapt without rerunning full pipeline"** — Can you walk me through the specific steps? Do I:
   - Pull the BaseAgent changes
   - Copy specific files to Cardio-KB
   - Run a partial reload (just relationships)?
   - Something else?

14. **What's the expected timeline** for getting edge properties working? Is this a 1-hour fix or a multi-day effort?

---

## Decisions to Make Tomorrow

### High Priority (Blocking)

| Decision | Options | My Preference |
|----------|---------|---------------|
| **Edge properties approach** | A) Port sidecar CSV logic to my loader<br>B) Switch back to ista/RDF pipeline<br>C) Fix my existing Cypher SET clauses | Deferring to Binglan — she confirmed ista handles ID mismatches natively and should be used properly, not worked around. The direct loader approach is causing the edge property issues. |
| **Drug merge strategy** | A) Adapt Binglan's YAML fix<br>B) Post-load deduplication script<br>C) Change DrugCentral parser to use drugbank_id as primary | A — cleaner, matches BaseAgent |

### Medium Priority

| Decision | Options | My Preference |
|----------|---------|---------------|
| **Config consolidation** | A) Keep Python + YAML (current)<br>B) YAML only (BaseAgent standard)<br>C) Python only (simpler for me) | Need Binglan's input — what's maintainable long-term? |
| **Orphan node handling** | A) Accept high rates<br>B) Filter on import<br>C) Post-load cleanup | A — unless it causes downstream issues |
| **Custom parser contribution** | A) Keep in CardioKB only<br>B) PR to BaseAgent<br>C) Discuss which ones are reusable | B for reusable ones (ClinVar, HPO, OpenTargets) |

### Low Priority (Can Defer)

| Decision | Options |
|----------|---------|
| Jensen TISSUES | Skip permanently or find BTO→Uberon mapping |
| ClinVar yield | Accept 0.12% or find better disease mapping |

---

## Files to Bring / Share Screen

1. **`src/memgraph_loader.py`** — lines 414-460 showing existing SET clause logic
2. **`src/ontology_configs.py`** — example relationship config with `data_property_map`
3. **Sample TSV** — show that properties exist in source data
4. **Memgraph query results** — show edges have no properties currently
5. **`KNOWN_ISSUES.md`** — full issue documentation

---

## Pre-Meeting Checklist

- [ ] Pull latest BaseAgent changes to `~/Desktop/BaseAgent/` (don't merge into Cardio-KB yet)
- [ ] Review the specific commits Binglan mentioned
- [ ] Have Memgraph running with current graph loaded
- [ ] Prepare quick demo of edge property absence: `MATCH ()-[r]->() WHERE r.source IS NOT NULL RETURN count(r)`
- [ ] Have `meeting_notes_binglan.md` open for reference
- [ ] Have terminal ready in `/Users/nawaza/Desktop/Cardio-KB/`

---

## Success Criteria for Meeting

**Minimum:** Understand exactly what changes to make and in which files

**Ideal:** 
- Clear step-by-step plan to add edge properties
- Drug merge fix adapted or plan to adapt
- Decision on architecture (direct loader vs ista/RDF)
- Timeline for completion

**Stretch:**
- Live fix of one relationship type as proof of concept
- Contribution plan for custom parsers
