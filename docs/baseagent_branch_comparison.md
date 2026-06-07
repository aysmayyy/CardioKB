# BaseAgent Branch Comparison: `cardiokb` vs `main`

**Date:** 2026-06-06
**Repository:** BinglanLi/BaseAgent
**Merge base:** `e08e8d9` (common ancestor)

## Summary

No structural divergence from the BaseAgent pipeline. The `cardiokb` branch adds CardioKB-specific parsers, configs, and mapping files on top of `main`, plus targeted bug fixes to the core exporter/populator. Total diff: **+9,799 / -4,440 lines** across 38 files.

---

## Commits on `cardiokb` not on `main` (11)

| Commit | Description |
|--------|-------------|
| `5c3e554` | fix: handle mixed-endpoint edge types, remove broken Drug merge configs |
| `c001d5e` | feat(ontology): implement lazy loading for edge property lookups |
| `59157cf` | fix: stream RDF edge extraction to prevent rdflib triple loss on large ontologies |
| `ba7331a` | fix: Disease synonyms, ClinicalTrial condition matching, Drug deduplication, DrugBank column names |
| `7ab5774` | fix: resolve 4 ista mapping issues — CTD expression, Pathway/TF/SideEffect labels, STUDIES_CONDITION matching, source labels |
| `faa2a76` | fix: use ista owl2.DataLoader execute() for 60000x speedup, fix populate performance bottleneck |
| `b346746` | fix: resolve double prefix, edge properties, source labels, BindingDB and OpenTargets mapping issues |
| `bf7009b` | fix(mappings): resolve 8 inactive relationship mappings in CardioKB pipeline |
| `aa80d04` | Merge branch 'main' of github.com:BinglanLi/BaseAgent |
| `73bd6f9` | Merge branch 'main' of github.com:BinglanLi/BaseAgent |
| `508bcfa` | Add CardioKB notebook adapted from AlzKB |

## Commits on `main` not on `cardiokb` (11)

| Commit | Description | Notes |
|--------|-------------|-------|
| `6947cd8` | feat(populator): track total runtime for ontology population | Minor logging |
| `b51fb27` | feat(ontology): implement lazy loading for edge property lookups and improve ID resolution | Already cherry-picked as `c001d5e` |
| `80fcf30` | fix(eval): support subclass during evaluation | Eval-only |
| `29de0d2` | feat(ontology): add xrefMeSHSupplementary for enhanced chemical cross-referencing | Ontology schema |
| `2ead1d7` | feat(ctd-parser): enhance CTDParser to include additional cross-reference identifiers | Parser enhancement |
| `2e67505` | fix(ontology): remove obsolete xrefDrugBankID and use xrefDrugbank | Xref rename |
| `f3e7875` | fix(ontology): use xrefMedDRA instead of xrefMeSH for chemical effect cross-referencing | Xref rename |
| `66b6859` | fix(ontology): update the first drug mapping | Mapping fix |
| `9959ce4` | fix(project): correct edge type names for gene-disease associations | Config fix |
| `bc44512` | chore(gitignore): ignore template/edirect | Housekeeping |
| `15f4c88` | fix(eval): enhance metrics for node and edge type completeness | Eval-only |

None of the `main`-only commits are critical for the CardioKB build. Merging `main` into `cardiokb` is optional to stay current.

---

## File-Level Breakdown

### Core Pipeline Changes (3 files — bug fixes)

| File | Lines Changed | Description |
|------|---------------|-------------|
| `template/src/export/memgraph_exporter.py` | +173 / -83 | Mixed-endpoint LOAD CSV fix (split into per-label blocks), sidecar edge property support |
| `template/src/main.py` | +138 / -35 | Pipeline orchestration adjustments for CardioKB |
| `template/src/ontology/populator.py` | +44 / -12 | Cherry-picked lazy loading fix for edge property collection |

### CardioKB-Specific Additions (expected)

| File(s) | Lines | Description |
|---------|-------|-------------|
| `cardiokb.ipynb` | +476 | Main CardioKB notebook |
| `config/ista_mapping.yaml` | +732 | Full CardioKB ista mapping config |
| `config/ontology_mappings.yaml` | +969 | Full CardioKB ontology mapping config |
| 11 new parsers in `template/src/parsers/` | +2,513 | clinicaltrials, clinpgx, clinvar, hgnc, hpo, lincs, opentargets, pubtator, sider, + `__init__.py` |
| `template/src/condition_normalizer.py` | +49 | Disease condition normalization |
| `template/src/drug_merger.py` | +220 | Drug deduplication utility |
| `template/src/id_mappings.py` | +408 | Cross-database ID mapping |
| `src/export/tsv_exporter.py` | +592 | TSV export for CardioKB |
| `src/parsers/clinicaltrials_parser.py` | +218 | ClinicalTrials.gov parser (top-level) |
| `scripts/load_csvs_to_memgraph.py` | +240 | Memgraph CSV loader script |
| `generate_ista_mapping.py` | +140 | Mapping generator utility |

### Skill File Updates (6 files)

| File | Description |
|------|-------------|
| `skills/database-protocol/SKILL.md` | CardioKB-specific adjustments |
| `skills/evaluation-protocol/SKILL.md` | CardioKB-specific adjustments |
| `skills/mapping-protocol/SKILL.md` | CardioKB-specific adjustments |
| `skills/memgraph-protocol/SKILL.md` | CardioKB-specific adjustments |
| `skills/parser-protocol/SKILL.md` | CardioKB-specific adjustments |
| `skills/supervisor-protocol/SKILL.md` | CardioKB-specific adjustments |

### Ontology Schema

| File | Lines Changed | Description |
|------|---------------|-------------|
| `template/data/ontology/ontology.rdf` | net -1,600 | Cleanup/dedup of OWL schema for CardioKB's 17 node types |

### Config Changes

| File | Lines Changed | Description |
|------|---------------|-------------|
| `template/config/databases.yaml` | +231 / -? | Database source definitions for CardioKB |
| `template/config/ontology_mappings.yaml` | +844 / -? | Ontology mapping overrides |
| `template/config/project.yaml` | +421 / -? | Project config for CardioKB |

### Minor / Miscellaneous

| File | Description |
|------|-------------|
| `BaseAgent/llm.py` | +49 / -1 — LLM config adjustment |
| `examples/mcp_config.yaml` | +1 — Example config |
| `template/src/parsers/bindingdb_parser.py` | +3 / -1 — Minor fix |
| `template/src/parsers/disease_ontology_parser.py` | +15 / -1 — Minor fix |
| `template/src/parsers/gene_ontology_parser.py` | +2 / -1 — Minor fix |
