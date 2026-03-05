# CardioKB: Cardiovascular Disease Knowledge Base

A biomedical knowledge graph pipeline that integrates 8 data sources into a Neo4j graph for cardiovascular disease research, feature selection, and precision medicine.

## Data Sources

| Source | Type | Auth Required | Description |
|--------|------|---------------|-------------|
| **NCBIGene** | FTP download | None | Human gene annotations |
| **DrugBank** | Web download | Optional (HTTP Basic) | Drug information and identifiers |
| **AOP-DB** | MySQL database | MySQL credentials | Adverse outcome pathways, gene-pathway relationships |
| **DoRothEA** | OmniPath API | None | Transcription factor regulatory networks |
| **DisGeNET** | REST API + files | Optional API key | Gene-disease associations (CVD-scoped) |
| **ClinicalTrials.gov** | REST API v2 | None | CVD clinical trials, interventions, conditions |
| **ClinPGx** | REST API | None | Pharmacogenomics: gene-drug interactions, variants, CPIC guidelines |
| **OMIM** | Bulk files + API | Optional API key | Mendelian genetic disorders, gene-disease relationships |

## Neo4j Graph Schema

**Node types:** Gene, Disease, Drug, Pathway, TranscriptionFactor, ClinicalTrial, Variant, DrugLabel, SideEffect, PharmacologicClass

**Relationship types:** geneAssociatesWithDisease, geneInPathway, STUDIES_CONDITION, TESTS_INTERVENTION, AFFECTS_RESPONSE_TO, VARIANT_IN, transcriptionFactorInteractsWithGene, compoundCausesSideEffect, and others

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                 # Pipeline orchestrator (entry point)
│   ├── neo4j_loader.py         # Cypher-based Neo4j batch loader
│   ├── ontology_configs.py     # Node/relationship schema definitions
│   ├── utils.py                # CVD term filtering utilities
│   └── parsers/
│       ├── base_parser.py      # Abstract base class for all parsers
│       ├── ncbigene_parser.py
│       ├── drugbank_parser.py
│       ├── aopdb_parser.py
│       ├── dorothea_parser.py
│       ├── disgenet_parser.py
│       ├── clinicaltrials_parser.py
│       ├── clinpgx_parser.py
│       └── omim_parser.py
├── scripts/
│   └── verify_graph.py         # Neo4j graph verification and validation
├── data/
│   ├── raw/                    # Downloaded source data
│   ├── processed/              # Exported TSV files (per source)
│   └── output/                 # Release notes
├── ontology/
│   └── cvd_disease_hierarchy.txt  # 115 CVD terms for filtering
├── docs/                       # Research plan, specific aims, ontology docs
├── examples/                   # Example scripts for individual parsers
├── notebooks/                  # Jupyter notebooks for exploration
├── tests/                      # pytest test files
├── models/                     # (Future) ML models
└── web/                        # (Future) Web interface
```

## Running the Pipeline

### Prerequisites

- Python 3.11 (conda env: `cardiokb`)
- Neo4j instance running locally or remotely

### Installation

```bash
conda activate cardiokb
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>

# Optional — parsers are disabled if credentials are missing
DISGENET_API_KEY=<key>
DRUGBANK_USERNAME=<username>
DRUGBANK_PASSWORD=<password>
MYSQL_USERNAME=<mysql-user>        # For AOP-DB parser
MYSQL_PASSWORD=<mysql-password>
MYSQL_DB_NAME=aopdb

# Optional — enables OMIM API enrichment
OMIM_API_KEY=<key>

# Optional
CARDIOKB_LOG_LEVEL=INFO
```

### Run

```bash
# Full pipeline: download → parse → TSV export → Neo4j load
python src/main.py

# Parse and export only (no Neo4j)
python src/main.py --skip-neo4j

# Re-parse from cached data (no downloads)
python src/main.py --skip-download

# All options
python src/main.py --base-dir . --log-level INFO --skip-download --skip-neo4j
```

### TSV Export

The pipeline exports all parsed data to `data/processed/<source>/` as tab-separated files. These serve as an archived, reproducible snapshot of each run.

### Verify the Graph

After loading, run the verification script to check node/relationship counts, sample edges, and data quality:

```bash
python scripts/verify_graph.py --uri bolt://localhost:7687 --username neo4j --password <password>
```

The script also reads from `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` environment variables.

## CVD Scope

All cardiovascular diseases including arrhythmias, coronary artery disease, heart failure, cardiomyopathies, hypertension, stroke, valvular heart disease, peripheral artery disease, and lipid disorders. The full term list (115 terms) is in `ontology/cvd_disease_hierarchy.txt`.

## Phase 2: Hetionet Component Parsers

The next phase will add parsers for individual Hetionet component databases to expand the knowledge graph with additional gene, disease, compound, and pathway relationships.

## Architecture Notes

- All parsers extend `BaseParser` from `src/parsers/base_parser.py`
- Neo4j loading uses UNWIND-based Cypher batching (batch size: 1000) with MERGE to prevent duplicates
- Graph schema is defined declaratively in `src/ontology_configs.py`
- Parsers with missing credentials are automatically skipped at runtime
