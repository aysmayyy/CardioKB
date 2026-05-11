# CardioKB - Biomedical Knowledge Graph

## Security Rules
- **Never** print, display, or include in any output the contents of `.env` files, API keys, passwords, or any credentials.
- Read credentials silently from `.env` only. Do not echo, log, or surface secret values in code output, tool calls, or conversation.

## Auto-Update Rules
- After every successful pipeline run or significant code change, automatically update `README.md` with current graph stats (node/relationship counts, source counts) and commit and push without being asked.

## Project Overview
12-week rotation project (Jan-Apr 2026) building a CVD-focused biomedical knowledge graph. The graph integrates 24 deduplicated data sources (each node type and edge type served by exactly one authoritative database) into Memgraph for disease research, feature selection, and precision medicine. Adapted from AlzKB (Alzheimer's Knowledge Base) with custom parsers and AI-powered parser generation. The **DatabaseAgent** (`src/database_agent.py`) autonomously generates new parsers from just a name and URL using Claude API. The **DiseaseQueryAgent** (`src/disease_agent.py`) enriches the graph for any disease on demand via ClinicalTrials.gov API v2. Three legacy sources (SIDER, LINCS L1000, MEDLINE) are retained as-is — no live API alternatives available.

## Current Graph Stats
- **4,891,227 nodes** | **7,682,399 relationships** | **17 node types** | **42 relationship types** | **24 sources** | **21 source labels**
- All relationships carry a `source` property identifying the originating database (e.g., `source: "OpenTargets"`)
- *Stats are current as of last pipeline run; see Memgraph or `GET /api/graph-stats` for live counts.*

## Tech Stack
- **Language**: Python 3.11 (conda env: `cardiokb` for local dev)
- **Database**: Memgraph (knowledge graph, bolt protocol, Neo4j driver compatible)
- **Deployment**: Docker Compose (Flask app + Memgraph, see `docker-compose.yml`)
- **Key libraries**: pandas, numpy, requests, neo4j, flask, scipy, obonet, lxml
- **Testing**: pytest
- **Notebooks**: Jupyter

## Project Structure
- `src/main.py` — Pipeline orchestrator (supports `--skip-neo4j`, `--skip-download`)
- `src/parsers/` — 26 data source parsers (inherit from `BaseParser` in `base_parser.py`)
  - `src/parsers/hetionet_components/` — 12 Hetionet-derived component parsers
- `src/database_agent.py` — Autonomous parser generator (Claude API + sample download + graph load)
- `src/ontology_configs.py` — 86 ontology configs mapping source data to graph schema
- `src/memgraph_loader.py` — Cypher-based Memgraph batch loader (auto-sets `r.source` from config `source_label`)
- `src/id_mapping.py` — Central ID mapping module: cross-database ID remapping (PubTator MeSH-to-DOID), validate_mapping(), suggest_mapping(), create_missing_nodes(), CLI interface
- `src/utils.py` — Shared utilities (`load_disease_terms()`, `get_disease_search_pattern()`)
- `ontology/disease_filter.txt` — Symlink to `diseases/cvd.txt` (active disease filter)
- `ontology/diseases/` — Disease term files: `cvd.txt` (184), `alzheimers.txt` (35), `cancer.txt` (70), `asthma.txt` (48), `diabetes.txt` (52)
- `data/raw/` — Downloaded source data
- `data/processed/` — Exported TSV files for graph loading
- `data/output/` — Release notes and build artifacts
- `interface/index.html` — Web dashboard with Explore (graph viz), Query (multi-panel), sidebar Build Knowledge Graph (AI disease enrichment), and Extract Disease Subgraph (N-hop extraction + JSON/CSV export)
- `src/agent.py` — Base disease agent (Claude API)
- `src/disease_agent.py` — DiseaseQueryAgent class: ClinicalTrials.gov API v2 fetching, graph loading, caching, SSE progress
- `src/api.py` — Flask backend with SSE streaming, disease subgraph API, and agent builds (`/api/agent/build`, `/api/agent/build-disease-graph`)
- `src/orchestrator.py` — Pipeline health check with dynamic graph-based parser status detection
- `run.sh` — Launches Flask + opens browser (local dev)
- `Dockerfile` — Flask web app container (Python 3.11-slim)
- `docker-compose.yml` — Full stack: Memgraph + Flask app
- `.dockerignore` — Excludes data/ (48GB), .git, .env from Docker build
- `.env.example` — Environment variable template with documentation
- `scripts/export_graph.sh` — Export Memgraph data volume as tar.gz for deployment
- `scripts/import_graph.sh` — Import Memgraph data volume on target host
- `scripts/compute_specificity.py` — Pre-computes `specificityScore` node property in graph (auto-runs at end of pipeline)
- `scripts/` — Data processing and verification scripts
- `reports/` — Generated pipeline health reports and cached ID mapping validation report (`id_mapping_report.json`)
- `docs/` — Documentation, research plan, specific aims
- `models/` — Future ML models
- `.claude/skills/` — Claude Code custom skills (see below)

## Claude Code Skills
Reusable skill files in `.claude/skills/` that Claude Code auto-loads when relevant tasks are detected. These are committed to the repo so any Claude Code instance working on this project has access.

| Skill | File | Purpose |
|-------|------|---------|
| `database-parsing` | `.claude/skills/database-parsing/SKILL.md` | Step-by-step guide for adding a new data source parser to CardioKB. Covers access type determination, parser creation, ontology config, pipeline registration, and verification. **Use this skill whenever integrating a new database.** |
| `clinicaltrials-cvd` | `.claude/skills/clinicaltrials-cvd/SKILL.md` | ClinicalTrials.gov API v2 query reference |
| `clinpgx-parser` | `.claude/skills/clinpgx-parser/SKILL.md` | ClinPGx REST API parsing reference |
| `clinpgx-database` | `.claude/skills/clinpgx-database/SKILL.md` | ClinPGx pharmacogenomics data access reference |

## Deployment (Docker)
```bash
# Deploy the web app + Memgraph (production)
cp .env.example .env           # Fill in MEMGRAPH_PASSWORD, ANTHROPIC_API_KEY, ADMIN_PASSWORD
./scripts/import_graph.sh data/export/memgraph-data.tar.gz
docker compose up -d           # App live at http://localhost:5050

# Export graph data for transfer to another host
./scripts/export_graph.sh      # Produces data/export/memgraph-data.tar.gz (~1.2 GB)
```

## Running the Pipeline (Local Dev)
```bash
# Full pipeline: download → parse → TSV export → Memgraph load
python src/main.py

# Parse and export only (no graph load)
python src/main.py --skip-neo4j

# Use existing cached data (no downloads)
python src/main.py --skip-download

# Both flags
python src/main.py --skip-download --skip-neo4j
```

## Environment Variables
All env vars use `MEMGRAPH_` prefix (not `NEO4J_`). See `.env.example` for the full list:
- `MEMGRAPH_URI`, `MEMGRAPH_USERNAME`, `MEMGRAPH_PASSWORD` — Graph database connection
- `ANTHROPIC_API_KEY` — AI agent features (Build Knowledge Graph) — direct Anthropic API
- `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL` — Azure AI Foundry (preferred; takes priority over `ANTHROPIC_API_KEY` when both are set)
- `ADMIN_PASSWORD` — Admin UI features (pipeline run, add database)
- `DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD` — Pipeline only (optional)

## Conventions
- New parsers should extend `BaseParser` from `src/parsers/base_parser.py`
- Raw data downloads go to `data/raw/<source_name>/`
- Parsed TSV output goes to `data/processed/<source_name>/`
- Environment variables for credentials go in `.env` (not committed); template in `.env.example`
- Run tests with `pytest`
- Every relationship ontology config must include a `source_label` field

## Disease Scope & Filtering
Disease term files live in `ontology/diseases/` (one term per line, `#` for comments). Available filters:

| File | Terms | Disease Area |
|------|-------|-------------|
| `cvd.txt` | 184 | Cardiovascular disease (default) |
| `alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `cancer.txt` | 70 | Cancer / oncology |
| `asthma.txt` | 48 | Asthma & respiratory diseases |
| `diabetes.txt` | 52 | Diabetes & metabolic diseases |

`ontology/disease_filter.txt` is a symlink to `diseases/cvd.txt` — existing code that reads it directly (e.g., `main.py` CVD node tagging) works without changes.

**ClinicalTrialsParser** accepts a `disease_filter` parameter — when omitted, defaults to `ontology/disease_filter.txt` (CVD). Queries ClinicalTrials.gov API v2 per disease term, caches JSON responses. All other parsers are fully disease-agnostic.

CVD ontology files: `ontology/genes/cvd.txt` (3,984 gene symbols from OMIM + DisGeNET, cleaned of LOC* loci and OMIM phenotype symbols), `ontology/schema/node_types.txt` (17 types), `ontology/schema/edge_types.txt` (36 types).

## Data Sources — 24 Sources (24 Parsers)

### Direct Parsers (5)
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 1 | ClinicalTrials.gov | ClinicalTrialsParser | Public API v2 | Working (85,691 trials, 27,866 STUDIES_CONDITION + 17,492 TESTS_INTERVENTION edges) |
| 2 | ClinPGx (PharmGKB successor) | ClinPGxParser | Public API | Working (1,091 VARIANT_IN, 503 drugLabelAnnotatesGene, 345 drugLabelDescribesDrug, 243 AFFECTS_RESPONSE_TO edges) |
| 3 | NCBI Gene | NCBIGeneParser | Public FTP | Working (194,553 genes) |
| 4 | DoRothEA (OmniPath) | DoRothEAParser | Public API | Working (12,985 TF-gene interactions, with morScore + confidence properties) |
| 5 | DrugBank | DrugBankParser | XML file | Working (19,842 drugs + 4,572 CTD unique Drug nodes, 12,089 drugBindsGene edges) |

### Hetionet-Derived Component Parsers (17)
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 6 | Disease Ontology (DOID) | DiseaseOntologyParser | Public | Working (12,012 diseases, 6,447 diseaseIsSubtypeOf edges) |
| 7 | Gene Ontology (GO) | GeneOntologyParser | Public | Working (50,350 BP + 26,935 MF + 25,794 CC edges) |
| 8 | Uberon (anatomy) | UberonParser | Public | Working (14,937 anatomy nodes) |
| 9 | MeSH (symptoms) | MeSHParser | Public | Working (966 symptom nodes, no relationship data) |
| 10 | SIDER (side effects) | SIDERParser | Public | Working (148,518 edges) **Legacy: retained — no live API alternative** |
| 11 | LINCS L1000 (gene expression) | LINCS1000Parser | Public | Working (150,540 geneRegulates + 10,218 downreg + 10,278 upreg edges, with zScore) **Legacy: retained — clue.io requires institutional access** |
| 12 | MEDLINE (literature cooccurrence) | MEDLINECooccurrenceParser | Public | Working (365 edges: 244 anatomy + 117 symptom + 4 disease cooccurrence) **Legacy: pinned GitHub commit** |
| 13 | DrugCentral (drug-disease) | DrugCentralParser | Public | Working (16,403 pharmacologic class + 779 treats + 189 palliates edges, CUI-to-DOID mapped) |
| 14 | BindingDB (drug-target) | BindingDBParser | Public | Working (12,250 chemicalBindsGene edges) |
| 15 | PubTator Central (literature mining) | PubTatorParser | Public FTP | Working (673,374 geneAssociatesWithDisease + 806,900 diseaseAssociatesWithDisease edges after CVD AND-filter) |
| 16 | CTD (chemical-gene) | CTDParser | Public | Working (4,572 unique Drug nodes, 116,451 chemicalIncreasesExpression + 97,951 chemicalDecreasesExpression edges) |
| 17 | Bgee (gene expression) | BgeeParser | Public FTP | Working (784,026 underexpresses + 1,872 overexpresses edges, with expressionScore property) |
| 18 | Jensen TISSUES (gene-tissue) | JensenTissuesParser | Public | Working (271,657 gene-tissue edges) |
| 19 | HPO (Human Phenotype Ontology) | HPOParser | Public | Working (19,389 phenotypes, 162,994 gene-phenotype edges) |
| 20 | Reactome | ReactomeParser | Public | Working (44,979 geneInPathway + 44,979 pathwayContainsGene edges) |
| 21 | STRING | STRINGParser | Public | Working (121,170 geneInteractsWithGene edges, confidence > 700) |
| 22 | OpenTargets | OpenTargetsParser | Public | Working (103,879 geneAssociatesWithDisease edges after CVD AND-filter, via EFO-to-DOID mapping) |

### Agent-Generated Parsers (2)
| # | Source | Parser | Access | Status |
|---|--------|--------|--------|--------|
| 23 | HGNC Gene Families | HGNCFamiliesParser | Public | Working (1,934 GeneFamily nodes, 5,123 geneInFamily + 5,123 familyContainsGene edges) |
| 24 | ClinVar | ClinVarParser | Public FTP | Working (4,488,042 Variant nodes, 2,267,095 hasVariant + 2,267,095 variantInGene + 594,101 associatedWithVariant + 594,101 variantAssociatedWithDisease edges) |

### Sources Removed (12) — see docs/CardioKB_Redundancy_Changelog.docx
DisGeNET, GWAS Catalog, Jensen DISEASES, OMIM, WikiPathways, AOP-DB, HGNC (base), CellAge, GenAge, Hetionet (precomputed), DrugAge, AnAge

## Ontology Configs
86 entries in `src/ontology_configs.py` mapping parsed TSV files to graph node/relationship types, properties, and loading strategies. Each relationship config includes a `source_label` field that the loader sets as `r.source` on every relationship.

## Relationship Source Labels
All relationships carry a `source` property. Current labels (21 in graph):
`Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinVar`, `ClinicalTrials.gov`, `Disease Ontology`, `DoRothEA`, `DrugBank`, `DrugCentral`, `Gene Ontology`, `HGNC`, `HPO`, `Jensen TISSUES`, `LINCS L1000`, `MEDLINE`, `OpenTargets`, `PubTator`, `Reactome`, `SIDER`, `STRING`
Note: HGNC Families uses `HGNC` as its source label.
