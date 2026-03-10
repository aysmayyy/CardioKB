# CardioKB - Cardiovascular Disease Knowledge Base

## Security Rules
- **Never** print, display, or include in any output the contents of `.env` files, API keys, passwords, or any credentials.
- Read credentials silently from `.env` only. Do not echo, log, or surface secret values in code output, tool calls, or conversation.

## Auto-Update Rules
- After every successful pipeline run or significant code change, automatically update `README.md` with current graph stats (node/relationship counts, source counts) and commit and push without being asked.

## Project Overview
12-week rotation project (Jan–Apr 2026) building a cardiovascular disease knowledge base. The base KB structure is adapted from AlzKB (Alzheimer's Knowledge Base) files. BaseAgent (agentic AI tool) handles building the core knowledge graph from databases similar to AlzKB. On top of that, additional data sources are integrated via custom parsers. The final KB is stored in a Neo4j knowledge graph for CVD research, feature selection, and precision medicine.

## Current Graph Stats
- **332,447 nodes** | **8,869,944 relationships** | **15 node types** | **30 relationship types**
- All relationships carry a `source` property identifying the originating database (e.g., `source: "OMIM"`)

## Tech Stack
- **Language**: Python 3.11 (conda env: `cardiokb`)
- **Database**: Neo4j (knowledge graph)
- **Key libraries**: pandas, numpy, requests, neo4j, scipy, matplotlib
- **Testing**: pytest
- **Notebooks**: Jupyter

## Project Structure
- `src/main.py` — Pipeline orchestrator (supports `--skip-neo4j`, `--skip-download`)
- `src/parsers/` — 20 data source parsers (inherit from `BaseParser` in `base_parser.py`)
  - `src/parsers/hetionet_components/` — 13 Hetionet-derived component parsers
- `src/ontology_configs.py` — 53 ontology configs mapping source data to Neo4j schema
- `src/neo4j_loader.py` — Cypher-based Neo4j batch loader (auto-sets `r.source` from config `source_label`)
- `src/id_mapping.py` — Cross-database ID remapping (PubTator MeSH→DOID, GWAS→DOID)
- `src/utils.py` — Shared utilities (CVD filtering)
- `ontology/` — CVD disease hierarchy (115 terms)
- `data/raw/` — Downloaded source data
- `data/processed/` — Exported TSV files for Neo4j loading
- `data/output/` — Release notes and build artifacts
- `docs/` — Documentation, research plan, specific aims
- `examples/` — Example scripts for running parsers
- `notebooks/` — Jupyter notebooks for exploration
- `scripts/` — Data processing and verification scripts
- `tests/` — pytest test files
- `models/` — Future ML models
- `web/` — Future web interface
- `.claude/skills/` — Claude Code custom skills

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
- Run tests with `pytest tests/`
- Every relationship ontology config must include a `source_label` field

## CVD Scope
All cardiovascular diseases: arrhythmias, coronary artery disease, heart failure, cardiomyopathies, hypertension, stroke, valvular heart disease.

## Parsers — 20 Total

### Active & Loaded (19)
| Parser | Source | Notes |
|--------|--------|-------|
| ClinicalTrialsParser | ClinicalTrials.gov API v2 | Public API, 14,856 CVD trials |
| ClinPGxParser | ClinPGx (PharmGKB successor) | Public API, 454 annotations, 1,060 variants, 294 AFFECTS_RESPONSE_TO edges |
| NCBIGeneParser | NCBI Gene FTP | Public FTP, 193,687 genes |
| DoRothEAParser | OmniPath API (DoRothEA) | Public API, 15,092 TF-gene interactions |
| OMIMParser | OMIM genetic disorders | API key required, 1,556 CVD diseases, 1,632 gene-disease edges |
| DisGeNETParser | DisGeNET gene-disease | API key required, 5,010 gene-disease edges |
| DrugBankParser | DrugBank drugs | XML file or login, 19,842 drugs |
| AOPDBParser | AOP-DB adverse outcome pathways | SQL dump or MySQL, 187,247 gene-pathway edges |
| DiseaseOntologyParser | Disease Ontology (DOID) | Hetionet component, 12,012 diseases |
| GeneOntologyParser | Gene Ontology (GO) | Hetionet component, 376,442 annotations |
| UberonParser | Uberon anatomy ontology | Hetionet component, 14,675 anatomy nodes |
| SIDERParser | SIDER side effects | Hetionet component, 148,518 compound-side effect edges |
| PubTatorParser | PubTator literature mining | Hetionet component, 2.1M+ disease-disease edges |
| CTDParser | CTD chemical-gene interactions | Hetionet component, 677K expression edges |
| BgeeParser | Bgee gene expression | Hetionet component, 4.8M+ expression edges |
| HetionetPrecomputedParser | Hetionet precomputed edges | Hetionet component |
| GWASParser | GWAS Catalog | Hetionet component, 43,453 gene-disease edges |
| BindingDBParser | BindingDB drug-target | Hetionet component, 22,254 chemicalBindsGene edges (UniProt→Entrez mapped) |
| MEDLINECooccurrenceParser | MEDLINE co-occurrences | Hetionet component, 7,213 cooccurrence edges |

### Stale URLs / Download Failures (1)
| Parser | Source | Issue |
|--------|--------|-------|
| MeSHParser | MeSH symptom terms | Nodes loaded (966), no relationship data |

### Credential-Gated (requires env vars, currently loaded)
| Parser | Source | Required Env Vars | Status |
|--------|--------|-------------------|--------|
| OMIMParser | OMIM genetic disorders | `OMIM_API_KEY` | Loaded |
| DisGeNETParser | DisGeNET gene-disease | `DISGENET_API_KEY` | Loaded |
| DrugBankParser | DrugBank drugs | `DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD` (or XML file) | Loaded via XML |
| AOPDBParser | AOP-DB adverse outcome pathways | `MYSQL_USERNAME`, `MYSQL_PASSWORD` (or SQL dump) | Loaded via SQL dump |

## Ontology Configs
53 entries in `src/ontology_configs.py` mapping parsed TSV files to Neo4j node/relationship types, properties, and loading strategies. Each relationship config includes a `source_label` field that the loader sets as `r.source` on every relationship.

## Relationship Source Labels
All relationships carry a `source` property. Current labels:
`AOP-DB`, `Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinicalTrials.gov`, `DisGeNET`, `Disease Ontology`, `DoRothEA`, `DrugCentral`, `Gene Ontology`, `GWAS Catalog`, `Hetionet`, `LINCS L1000`, `MEDLINE`, `OMIM`, `PubTator`, `SIDER`
