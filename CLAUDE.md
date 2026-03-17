# CardioKB - Biomedical Knowledge Graph

## Security Rules
- **Never** print, display, or include in any output the contents of `.env` files, API keys, passwords, or any credentials.
- Read credentials silently from `.env` only. Do not echo, log, or surface secret values in code output, tool calls, or conversation.

## Auto-Update Rules
- After every successful pipeline run or significant code change, automatically update `README.md` with current graph stats (node/relationship counts, source counts) and commit and push without being asked.

## Project Overview
12-week rotation project (Jan–Apr 2026) building a general-purpose biomedical knowledge graph. While initially focused on cardiovascular disease, the graph contains data spanning all human diseases — most data sources are disease-agnostic. The base KB structure is adapted from AlzKB (Alzheimer's Knowledge Base) files. The **DatabaseAgent** (`src/database_agent.py`) autonomously generates new parsers from just a name and URL using Claude API — it samples the file, generates parser code + ontology configs, integrates into the pipeline, and loads data into Neo4j. The **DiseaseQueryAgent** (`src/disease_agent.py`) enriches the graph for any disease on demand — fetches gene-disease associations (DisGeNET) and clinical trials (ClinicalTrials.gov API v2), loads into Neo4j, caches results. Additional data sources are integrated via custom parsers or the agent. The final KB is stored in a Neo4j knowledge graph for disease research, feature selection, and precision medicine.

## Current Graph Stats
- **5,464,107 nodes** | **40,765,325 relationships** | **21 node types** | **42 relationship types** | **36 sources**
- All relationships carry a `source` property identifying the originating database (e.g., `source: "DisGeNET"`)
- *Stats are current as of last pipeline run; see Neo4j or `GET /api/graph-stats` for live counts.*

## Tech Stack
- **Language**: Python 3.11 (conda env: `cardiokb`)
- **Database**: Neo4j (knowledge graph)
- **Key libraries**: pandas, numpy, requests, neo4j, flask, scipy, obonet, lxml
- **Testing**: pytest
- **Notebooks**: Jupyter

## Project Structure
- `src/main.py` — Pipeline orchestrator (supports `--skip-neo4j`, `--skip-download`)
- `src/parsers/` — 36 data source parsers (inherit from `BaseParser` in `base_parser.py`)
  - `src/parsers/hetionet_components/` — 14 Hetionet-derived component parsers
- `src/database_agent.py` — Autonomous parser generator (Claude API + sample download + Neo4j load)
- `src/ontology_configs.py` — 85 ontology configs mapping source data to Neo4j schema
- `src/neo4j_loader.py` — Cypher-based Neo4j batch loader (auto-sets `r.source` from config `source_label`)
- `src/id_mapping.py` — Central ID mapping module: cross-database ID remapping (PubTator MeSH→DOID, GWAS→DOID), validate_mapping(), suggest_mapping(), create_missing_nodes(), CLI interface
- `src/utils.py` — Shared utilities (`load_disease_terms()`, `get_disease_search_pattern()`)
- `ontology/disease_filter.txt` — Symlink to `diseases/cvd.txt` (active disease filter)
- `ontology/diseases/` — Disease term files: `cvd.txt` (90), `alzheimers.txt` (35), `cancer.txt` (70), `asthma.txt` (48), `diabetes.txt` (52)
- `data/raw/` — Downloaded source data
- `data/processed/` — Exported TSV files for Neo4j loading
- `data/output/` — Release notes and build artifacts
- `interface/index.html` — Web dashboard with Explore (graph viz), Query (Neo4j Browser-style multi-panel), sidebar Build Knowledge Graph (AI disease enrichment), and Extract Disease Subgraph (N-hop extraction + JSON/CSV export)
- `src/agent.py` — Base disease agent (Claude API + DisGeNET standardization and fetching)
- `src/disease_agent.py` — DiseaseQueryAgent class: DisGeNET + ClinicalTrials.gov API v2 fetching, Neo4j loading, caching, SSE progress
- `src/api.py` — Flask backend with SSE streaming, disease subgraph API, and agent builds (`/api/agent/build`, `/api/agent/build-disease-graph`)
- `src/orchestrator.py` — Pipeline health check with dynamic Neo4j-based parser status detection
- `run.sh` — Launches Flask + opens browser
- `reports/` — Generated pipeline health reports and cached ID mapping validation report (`id_mapping_report.json`)
- `docs/` — Documentation, research plan, specific aims
- `scripts/compute_specificity.py` — Pre-computes `specificityScore` node property in Neo4j (auto-runs at end of pipeline)
- `scripts/` — Data processing and verification scripts
- `models/` — Future ML models
- `.claude/skills/` — Claude Code custom skills (see below)

## Claude Code Skills
Reusable skill files in `.claude/skills/` that Claude Code auto-loads when relevant tasks are detected. These are committed to the repo so any Claude Code instance working on this project has access.

| Skill | File | Purpose |
|-------|------|---------|
| `database-parsing` | `.claude/skills/database-parsing/SKILL.md` | Step-by-step guide for adding a new data source parser to CardioKB. Covers access type determination, parser creation, ontology config, pipeline registration, and verification. **Use this skill whenever integrating a new database.** |
| `aopdb-parser` | `.claude/skills/aopdb-parser/SKILL.md` | AOP-DB adverse outcome pathway parsing reference |
| `clinicaltrials-cvd` | `.claude/skills/clinicaltrials-cvd/SKILL.md` | ClinicalTrials.gov API v2 query reference |
| `clinpgx-parser` | `.claude/skills/clinpgx-parser/SKILL.md` | ClinPGx REST API parsing reference |
| `clinpgx-database` | `.claude/skills/clinpgx-database/SKILL.md` | ClinPGx pharmacogenomics data access reference |
| `omim-parser` | `.claude/skills/omim-parser/SKILL.md` | OMIM genetic disease parsing reference |

## Running the Pipeline
```bash
# Full pipeline: download → parse → TSV export → Neo4j load
python src/main.py

# Parse and export only (no Neo4j)
python src/main.py --skip-neo4j

# Use existing cached data (no downloads)
python src/main.py --skip-download

# Both flags
python src/main.py --skip-download --skip-neo4j
```

## Conventions
- New parsers should extend `BaseParser` from `src/parsers/base_parser.py`
- Raw data downloads go to `data/raw/<source_name>/`
- Parsed TSV output goes to `data/processed/<source_name>/`
- Environment variables for credentials go in `.env` (not committed)
- Run tests with `pytest`
- Every relationship ontology config must include a `source_label` field

## Disease Scope & Filtering
Disease term files live in `ontology/diseases/` (one term per line, `#` for comments). Available filters:

| File | Terms | Disease Area |
|------|-------|-------------|
| `cvd.txt` | 90 | Cardiovascular disease (default) |
| `alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `cancer.txt` | 70 | Cancer / oncology |
| `asthma.txt` | 48 | Asthma & respiratory diseases |
| `diabetes.txt` | 52 | Diabetes & metabolic diseases |

`ontology/disease_filter.txt` is a symlink to `diseases/cvd.txt` — existing code that reads it directly (e.g., OMIM `is_cvd` tagging, `main.py` CVD node tagging) works without changes.

**ClinicalTrialsParser** downloads the full AACT bulk flat files (~2.4 GB, all 576K+ trials) and is **completely disease-agnostic** — no filtering is applied. Run it once to load all trials.

**DisGeNETParser** is the only parser that accepts a `disease_filter` parameter:
- **DisGeNETParser(disease_filter="ontology/diseases/alzheimers.txt")** — searches the API for diseases matching the term list

When `disease_filter` is omitted, DisGeNET defaults to `ontology/disease_filter.txt` (→ CVD). OMIMParser reads the symlink to tag rows with `is_cvd` but loads all data regardless. All other parsers are fully disease-agnostic.

## Data Sources — 36 Sources (36 Parsers)

### Phase 1: Core Parsers
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 1 | ClinicalTrials.gov | ClinicalTrialsParser | AACT bulk download | Working (576,029 trials, all diseases) |
| 2 | ClinPGx (PharmGKB successor) | ClinPGxParser | Public API | Working (454 annotations, 1,060 variants, 294 AFFECTS_RESPONSE_TO edges) |
| 3 | NCBI Gene | NCBIGeneParser | Public FTP | Working (193,687 genes) |
| 4 | DoRothEA (OmniPath) | DoRothEAParser | Public API | Working (15,092 TF-gene interactions) |
| 5 | OMIM | OMIMParser | API key required | Working (1,556 CVD diseases, 1,632 gene-disease edges) |
| 6 | DisGeNET | DisGeNETParser | API key required | Working (341 DO-matched + 559 new diseases, 5,010 gene-disease edges) |
| 7 | DrugBank | DrugBankParser | XML file or login | Working (19,842 drugs, 19,047 drug-target edges from full database XML) |
| 8 | AOP-DB | AOPDBParser | SQL dump or MySQL | Working (173,500 chemicals, 4,646 pathways, 187,247 gene-pathway edges) |

### Phase 2: Hetionet Component Parsers
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 9 | Disease Ontology (DOID) | DiseaseOntologyParser | Public | Working (12,012 diseases) |
| 10 | Gene Ontology (GO) | GeneOntologyParser | Public | Working (38,739 GO terms, 376,442 annotations) |
| 11 | Uberon (anatomy) | UberonParser | Public | Working (14,675 anatomy nodes) |
| 12 | MeSH (symptoms) | MeSHParser | Public | Working (966 symptom nodes, no relationship data) |
| 13 | SIDER (side effects) | SIDERParser | Public | Working (5,734 side effects, 153,663 edges) |
| 14 | LINCS L1000 (gene expression) | LINCS1000Parser | Public | Working (336,999 edges) |
| 15 | MEDLINE (literature cooccurrence) | MEDLINECooccurrenceParser | Public | Working (7,213 cooccurrence edges) |
| 16 | DrugCentral (drug-disease) | DrugCentralParser | Public | Working (14,572 relationships) |
| 17 | GWAS Catalog (associations) | GWASParser | Public | Working (90,578 gene-disease associations after 3-strategy DOID remap) |
| 18 | BindingDB (drug-target) | BindingDBParser | Public | Working (23,954 drug-gene bindings via UniProt→Entrez mapping) |
| 19 | PubTator Central (literature mining) | PubTatorParser | Public FTP | Working (69M+ literature edges) |
| 20 | CTD (chemical-gene) | CTDParser | Public | Working (677,015 expression edges) |
| 21 | Bgee (gene expression) | BgeeParser | Public FTP | Working (6,609,112 expression edges) |
| 22 | Hetionet (precomputed edges) | HetionetPrecomputedParser | Public | Working (613,470 precomputed edges) |
| 23 | Jensen Lab DISEASES | JensenLabParser | Public | Working (gene-disease associations) |
| 24 | Jensen Lab TISSUES | JensenTissuesParser | Public | Working (988,006 gene-tissue edges, 262 BTO tissue nodes created) |
| 25 | HPO (Human Phenotype Ontology) | HPOParser | Public | Working (19,389 phenotypes, 270,272 gene-phenotype edges) |
| 26 | Reactome | ReactomeParser | Public | Working (2,806 pathways, 147,005 geneInPathway edges) |
| 27 | WikiPathways | WikiPathwaysParser | Public | Working (982 pathways, 40,039 geneInPathway edges) |
| 28 | STRING | STRINGParser | Public | Working (228,193 geneInteractsWithGene edges, confidence > 700) |
| 29 | OpenTargets | OpenTargetsParser | Public | Working (2,345,386 geneAssociatesWithDisease edges via EFO→DOID mapping) |

### Phase 3: Agent-Generated Parsers
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 30 | HGNC | HGNCParser | Public | Working (44,361 Gene nodes enriched with xrefHGNC, geneName, locusGroup, locusType) |
| 31 | HGNC Gene Families | HGNCFamiliesParser | Public | Working (1,934 GeneFamily nodes, 33,967 geneInFamily edges) |
| 32 | ClinVar | ClinVarParser | Public FTP | Working (4,486,982 Variant nodes, 5.7M disease-variant edges, 4.5M gene-variant edges) |
| 33 | DrugAge/CellAge | DrugAgeParser | Public | Working (gene-aging associations, AgeingProperty nodes) |
| 34 | CellAge | CellAgeParser | Public | Working (senescence gene nodes) |
| 35 | AnAge | AnAgeParser | Public | Working (Species longevity nodes) |
| 36 | GenAge | GenAgeParser | Public | Working (aging-associated gene nodes) |

### Credential-Gated (requires env vars, currently loaded)
| Parser | Source | Required Env Vars | Status |
|--------|--------|-------------------|--------|
| OMIMParser | OMIM genetic disorders | `OMIM_API_KEY` | Loaded |
| DisGeNETParser | DisGeNET gene-disease | `DISGENET_API_KEY` | Loaded |
| DrugBankParser | DrugBank drugs | `DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD` (or XML file) | Loaded via XML |
| AOPDBParser | AOP-DB adverse outcome pathways | `MYSQL_USERNAME`, `MYSQL_PASSWORD` (or SQL dump) | Loaded via SQL dump |

## Ontology Configs
85 entries in `src/ontology_configs.py` mapping parsed TSV files to Neo4j node/relationship types, properties, and loading strategies. Each relationship config includes a `source_label` field that the loader sets as `r.source` on every relationship.

## Relationship Source Labels
All relationships carry a `source` property. Current labels (28 with edges in graph):
`AOP-DB`, `Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinVar`, `ClinicalTrials.gov`, `DisGeNET`, `DoRothEA`, `DrugAge`, `DrugBank`, `DrugCentral`, `GWAS Catalog`, `Gene Ontology`, `HGNC`, `HPO`, `Hetionet`, `Jensen DISEASES`, `Jensen TISSUES`, `LINCS L1000`, `MEDLINE`, `OMIM`, `OpenTargets`, `PubTator`, `Reactome`, `SIDER`, `STRING`, `WikiPathways`
Note: 8 node-only parsers (Disease Ontology, Uberon, MeSH, NCBI Gene, HGNC base, CellAge, AnAge, GenAge) contribute nodes without relationship source labels. HGNC Families uses `HGNC` as its source label.
