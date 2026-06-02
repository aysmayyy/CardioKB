# CardioKB Meeting Prep — Binglan

**Meeting Date:** 2026-05-28  
**Prepared:** 2026-05-27  
**Updated:** 2026-05-28 (post-meeting)  
**Status:** Meeting complete — action items below

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

## Binglan's Guidance (2026-05-28 Meeting)

### Architecture
- **Fix parsers**, update prompts to include templates + custom parsers
- **Separate initialization and evaluation steps** in the pipeline
- **Use rolling window carefully** when processing
- **Integrate new parsers into CardioKB branch of BaseAgent on GitHub** — custom parsers belong in the CardioKB branch, not kept separate

### Edge Properties
- Being addressed via the **ista fix** — no need to patch the direct loader; ista handles this natively once the pipeline is corrected

### Drug Merge
- Root cause: **ista mistake + ontology mapping issue**
- Fix: **promote one database as the core** (e.g., DrugBank) and merge others into it

### Config Format
- **Switch to YAML only** — remove Python `ontology_configs.py`
- YAML is faster for agents to read/write
- Use agent to migrate `ontology_configs.py` to new BaseAgent build
- **Keep filename constants** (don't inline filenames into YAML)

### Custom Parsers
- Add to **CardioKB branch of BaseAgent on GitHub**

### Orphan Nodes
- ista handles merge natively
- **Ask Jay about fastest way to import 7–10 GB TSV into Memgraph**

### Jensen TISSUES
- **Cut it out entirely** — not worth the BTO→Uberon mapping effort

---

## Questions Asked — Binglan's Answers

### On Edge Properties (Q1–3)
> **Answer:** Being addressed via the ista fix. Don't patch the direct loader — switch back to the ista pipeline. The sidecar CSV approach in `populator.py` + `memgraph_exporter.py` handles this end-to-end.

### On Drug Merge (Q4–6)
> **Answer:** Root cause was an ista mistake combined with an ontology mapping issue. Fix by promoting one database as the core source (e.g., DrugBank as primary) and merging others into it via `merge: true` + `merge_column` in YAML config.

### On Architecture (Q7–9)
> **Answer:** Direct loader is not acceptable long-term. Fix parsers, update prompts to include both templates and custom parsers, separate initialization and evaluation steps, use rolling window carefully. Custom parsers should be added to the CardioKB branch of BaseAgent on GitHub.

### On Config Format (Q8 follow-up)
> **Answer:** Switch to YAML only. YAML is faster for agents. Use agent to migrate `ontology_configs.py` to the new BaseAgent build. Keep filename constants in Python — just move the mapping configs to YAML.

### On Orphan Nodes (Q10)
> **Answer:** ista handles merge natively, which should reduce orphans. For the import performance question, ask Jay about the fastest way to import 7–10 GB TSV into Memgraph.

### On Jensen TISSUES (Q11)
> **Answer:** Cut it out entirely.

### On ClinVar / Workflow (Q12–14)
> Not explicitly addressed — focus was on architecture-level fixes first.

---

## Decisions Made (2026-05-28)

| Decision | Outcome |
|----------|---------|
| **Edge properties approach** | **B) Switch back to ista/RDF pipeline.** ista fix handles this. |
| **Drug merge strategy** | **Promote one DB as core, merge others.** ista mistake + ontology mapping issue. |
| **Config consolidation** | **B) YAML only.** Remove Python configs. Use agent to migrate. Keep filename constants. |
| **Orphan node handling** | **ista merge handles it.** Ask Jay re: 7–10 GB import performance. |
| **Custom parser contribution** | **Add to CardioKB branch of BaseAgent on GitHub.** |
| **Jensen TISSUES** | **Cut entirely.** |
| **ClinVar yield** | Not addressed — revisit after architecture migration. |

---

## Action Items

### Immediate
- [ ] Follow up with Binglan on ista progress — check status of her fixes landing
- [ ] Schedule earlier meeting if needed before next Thursday (2026-06-04)
- [ ] Ask Jay about fastest way to import 7–10 GB TSV into Memgraph

### Migration Tasks
- [ ] Create CardioKB branch on BaseAgent GitHub repo
- [ ] Migrate `ontology_configs.py` → YAML using agent (keep filename constants)
- [ ] Integrate 6 custom parsers into CardioKB branch of BaseAgent
- [ ] Remove Jensen TISSUES parser and configs
- [ ] Separate initialization and evaluation steps in pipeline
- [ ] Fix parsers, update prompts to include templates + custom parsers

### Pre-Meeting Checklist (completed)

- [x] Pull latest BaseAgent changes to `~/Desktop/BaseAgent/`
- [x] Review the specific commits Binglan mentioned
- [x] Have `meeting_notes_binglan.md` open for reference
