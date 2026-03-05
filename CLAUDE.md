# CardioKB - Cardiovascular Disease Knowledge Base

## Project Overview
12-week rotation project (Jan–Apr 2026) building a cardiovascular disease knowledge base. The base KB structure is adapted from AlzKB (Alzheimer's Knowledge Base) files. BaseAgent (agentic AI tool) handles building the core knowledge graph from databases similar to AlzKB. On top of that, additional data sources are integrated via custom parsers. The final KB is stored in a Neo4j knowledge graph for CVD research, feature selection, and precision medicine.

## Tech Stack
- **Language**: Python 3.11 (conda env: `cardiokb`)
- **Database**: Neo4j (knowledge graph)
- **Optional**: MySQL (for AOP-DB parser)
- **Key libraries**: pandas, numpy, requests, neo4j, scipy, matplotlib
- **Testing**: pytest
- **Notebooks**: Jupyter

## Project Structure
- `src/main.py` — Pipeline orchestrator (supports `--skip-neo4j`, `--skip-download`)
- `src/parsers/` — 18 data source parsers (inherit from `BaseParser` in `base_parser.py`)
  - `src/parsers/hetionet_components/` — 13 Hetionet-derived component parsers
- `src/ontology_configs.py` — 50 ontology configs mapping source data to Neo4j schema
- `src/neo4j_loader.py` — Cypher-based Neo4j batch loader
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

## CVD Scope
All cardiovascular diseases: arrhythmias, coronary artery disease, heart failure, cardiomyopathies, hypertension, stroke, valvular heart disease.

## Parsers — 18 Total

### Working (13)
| Parser | Source | Notes |
|--------|--------|-------|
| ClinicalTrialsParser | ClinicalTrials.gov API v2 | Public API, RNA therapeutics trials |
| ClinPGxParser | ClinPGx (PharmGKB successor) | Public API, gene-drug interactions |
| NCBIGeneParser | NCBI Gene FTP | Public FTP |
| DoRothEAParser | OmniPath API (DoRothEA) | Public API, TF-gene interactions |
| DiseaseOntologyParser | Disease Ontology (DOID) | Hetionet component |
| GeneOntologyParser | Gene Ontology (GO) | Hetionet component |
| UberonParser | Uberon anatomy ontology | Hetionet component |
| SIDERParser | SIDER side effects | Hetionet component |
| LINCS1000Parser | LINCS L1000 gene expression | Hetionet component |
| PubTatorParser | PubTator literature mining | Hetionet component |
| CTDParser | CTD chemical-gene interactions | Hetionet component |
| BgeeParser | Bgee gene expression | Hetionet component |
| HetionetPrecomputedParser | Hetionet precomputed edges | Hetionet component |

### Stale URLs / Download Failures (5)
| Parser | Source | Issue |
|--------|--------|-------|
| MeSHParser | MeSH symptom terms | No data parsed |
| MEDLINECooccurrenceParser | MEDLINE co-occurrences | Stale download URLs |
| DrugCentralParser | DrugCentral drug-disease | Download failure |
| GWASParser | GWAS Catalog | Download failure |
| BindingDBParser | BindingDB drug-target | Download failure |

### Credential-Gated (4, disabled without keys)
| Parser | Source | Required Env Vars |
|--------|--------|-------------------|
| OMIMParser | OMIM genetic disorders | `OMIM_API_KEY` |
| DisGeNETParser | DisGeNET gene-disease | `DISGENET_API_KEY` |
| DrugBankParser | DrugBank drugs | `DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD` |
| AOPDBParser | AOP-DB adverse outcome pathways | `MYSQL_USERNAME`, `MYSQL_PASSWORD`, `MYSQL_DB_NAME` |

## Ontology Configs
50 entries in `src/ontology_configs.py` mapping parsed TSV files to Neo4j node/relationship types, properties, and loading strategies.
