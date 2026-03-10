# CardioKB: Cardiovascular Disease Knowledge Base

A biomedical knowledge graph pipeline that integrates 22 data sources (20 parsers) into a Neo4j graph for cardiovascular disease research, feature selection, and precision medicine. Adapted from the AlzKB (Alzheimer's Knowledge Base) architecture with additional custom parsers and Hetionet component integrations.

**Graph stats:** 330,801 nodes | 7,469,592 relationships | 14 node types | 15 relationship types

## Pipeline Status

| Category | Count | Details |
|----------|-------|---------|
| Total databases | 22 | 20 parsers (some parsers handle multiple sources) |
| Active & loaded | 17 | Successfully parsed + loaded into Neo4j |
| Credential-gated (loaded) | 4 | OMIM, DisGeNET, DrugBank (XML), AOP-DB (SQL dump) |
| Stale/partial | 3 | MeSH (nodes only), MEDLINE (cached), BindingDB (NaN error) |
| Ontology configs | 52 | Neo4j node/relationship type mappings |
| Source-labeled relationships | 18 | All relationships carry `r.source` property |

## Data Sources

### Phase 1: Core Parsers

| # | Source | Access | Status |
|---|--------|--------|--------|
| 1 | ClinicalTrials.gov | Public API v2 | Working (14,856 CVD trials) |
| 2 | ClinPGx (PharmGKB successor) | Public API | Working (454 annotations, 1,060 variants) |
| 3 | NCBI Gene | Public FTP | Working (193,687 genes) |
| 4 | DoRothEA (OmniPath) | Public API | Working (15,092 TF-gene interactions) |
| 5 | OMIM | API key required | Working (1,556 CVD diseases, 1,632 gene-disease edges) |
| 6 | DisGeNET | API key required | Working (341 DO-matched + 559 new diseases, 5,010 gene-disease edges) |
| 7 | DrugBank | XML file or login | Working (19,842 drugs from full database XML) |
| 8 | AOP-DB | SQL dump or MySQL | Working (173,500 chemicals, 4,646 pathways, 187,247 gene-pathway edges) |

### Phase 2: Hetionet Component Parsers

| # | Source | Access | Status |
|---|--------|--------|--------|
| 9 | Disease Ontology (DOID) | Public | Working (12,012 diseases) |
| 10 | Gene Ontology (GO) | Public | Working (38,739 GO terms, 376,442 annotations) |
| 11 | Uberon (anatomy) | Public | Working (14,675 anatomy nodes) |
| 12 | MeSH (symptoms) | Public | Working (966 symptom nodes) |
| 13 | SIDER (side effects) | Public | Working (5,734 side effects, 153,663 edges) |
| 14 | LINCS L1000 (gene expression) | Public | Working (336,999 edges) |
| 15 | MEDLINE (literature cooccurrence) | Public | Working (7,502 cooccurrence edges) |
| 16 | DrugCentral (drug-disease) | Public | Working (14,572 relationships) |
| 17 | GWAS Catalog (associations) | Public | Working (760,270 gene-disease associations) |
| 18 | BindingDB (drug-target) | Public | Working (1,632,198 drug-gene bindings) |
| 19 | PubTator Central (literature mining) | Public FTP | Working (69M+ literature edges) |
| 20 | CTD (chemical-gene) | Public | Working (677,015 expression edges) |
| 21 | Bgee (gene expression) | Public FTP | Working (6,609,112 expression edges) |
| 22 | Hetionet (precomputed edges) | Public | Working (613,470 precomputed edges) |

## Neo4j Graph Schema

**Node types (14):** Gene (193,687), Disease (14,127), Drug (41,566), Pathway (4,646), TranscriptionFactor (367), ClinicalTrial (14,856), Variant (1,060), DrugLabel (378), SideEffect (5,734), Symptom (966), BodyPart (14,675), BiologicalProcess (24,547), MolecularFunction (10,123), CellularComponent (4,069)

**Key relationship types (15):** geneAssociatesWithDisease, geneParticipatesInBiologicalProcess, geneHasMolecularFunction, geneAssociatedWithCellularComponent, bodyPartUnderexpressesGene, bodyPartOverexpressesGene, diseaseAssociatesWithDisease, compoundCausesSideEffect, transcriptionFactorInteractsWithGene, diseaseLocalizesToAnatomy, diseasePresentsSymptom, diseaseResemblesDisease, STUDIES_CONDITION, TESTS_INTERVENTION, VARIANT_IN

**Relationship source labels:** All relationships carry a `source` property (e.g., `OMIM`, `DisGeNET`, `GWAS Catalog`, `PubTator`, `Bgee`, etc.) for provenance tracking across 18 databases.

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                 # Pipeline orchestrator (--skip-neo4j, --skip-download)
│   ├── neo4j_loader.py         # Cypher-based Neo4j batch loader
│   ├── ontology_configs.py     # 52 ontology configs for Neo4j schema mapping
│   ├── utils.py                # CVD term filtering utilities
│   └── parsers/
│       ├── base_parser.py      # Abstract base class for all parsers
│       ├── clinicaltrials_parser.py
│       ├── clinpgx_parser.py
│       ├── ncbigene_parser.py
│       ├── dorothea_parser.py
│       ├── omim_parser.py
│       ├── disgenet_parser.py
│       ├── drugbank_parser.py
│       ├── aopdb_parser.py
│       └── hetionet_components/    # 13 Hetionet-derived component parsers
│           ├── disease_ontology_parser.py
│           ├── gene_ontology_parser.py
│           ├── uberon_parser.py
│           ├── mesh_parser.py
│           ├── sider_parser.py
│           ├── lincs_parser.py
│           ├── medline_cooccurrence_parser.py
│           ├── drugcentral_parser.py
│           ├── gwas_parser.py
│           ├── bindingdb_parser.py
│           ├── pubtator_parser.py
│           ├── ctd_parser.py
│           ├── bgee_parser.py
│           └── hetionet_precomputed_parser.py
├── scripts/
│   ├── verify_graph.py         # Neo4j graph verification and validation
│   ├── run_aopdb.py            # Standalone AOP-DB parser + Neo4j loader
│   └── run_drugbank.py         # Standalone DrugBank parser + Neo4j loader
├── data/
│   ├── raw/                    # Downloaded source data (gitignored)
│   ├── processed/              # Exported TSV files per source (gitignored)
│   └── output/                 # Release notes and build artifacts (gitignored)
├── ontology/
│   └── cvd_disease_hierarchy.txt  # 115 CVD terms for filtering
├── docs/                       # Research plan, specific aims, data inventory xlsx
├── examples/                   # Example scripts for individual parsers
├── notebooks/                  # Jupyter notebooks for exploration
├── tests/                      # pytest test files
├── models/                     # (Future) ML models
└── web/                        # (Future) Web interface
```

## Running the Pipeline

### Prerequisites

- Python 3.11 (conda env: `cardiokb`)
- Neo4j instance running locally or remotely (only needed without `--skip-neo4j`)

### Installation

```bash
conda activate cardiokb
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required for Neo4j loading
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>

# Optional — parsers are disabled if credentials are missing
OMIM_API_KEY=<key>
DISGENET_API_KEY=<key>
DRUGBANK_USERNAME=<username>        # Not needed if XML file exists in data/raw/drugbank/
DRUGBANK_PASSWORD=<password>
MYSQL_USERNAME=<mysql-user>        # Not needed if SQL dump exists in data/raw/aopdb/
MYSQL_PASSWORD=<mysql-password>
MYSQL_DB_NAME=aopdb

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

# Both flags
python src/main.py --skip-download --skip-neo4j

# Run individual source parsers standalone
python scripts/run_aopdb.py              # AOP-DB only (parses SQL dump)
python scripts/run_drugbank.py           # DrugBank only (parses XML)
python scripts/run_drugbank.py --skip-neo4j  # Parse + TSV only, no Neo4j
```

### TSV Export

The pipeline exports all parsed data to `data/processed/<source>/` as tab-separated files. These serve as an archived, reproducible snapshot of each run. See `docs/cardiokb_data_inventory.xlsx` for the full file inventory with row counts and column schemas.

### Verify the Graph

After loading into Neo4j, run the verification script:

```bash
python scripts/verify_graph.py --uri bolt://localhost:7687 --username neo4j --password <password>
```

The script also reads from `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` environment variables.

## CVD Scope

All cardiovascular diseases including arrhythmias, coronary artery disease, heart failure, cardiomyopathies, hypertension, stroke, valvular heart disease, peripheral artery disease, and lipid disorders. The full term list (115 terms) is in `ontology/cvd_disease_hierarchy.txt`.

## Architecture Notes

- All parsers extend `BaseParser` from `src/parsers/base_parser.py`
- Neo4j loading uses UNWIND-based Cypher batching (batch size: 1000) with MERGE to prevent duplicates
- All relationships are tagged with `r.source` property from the config's `source_label` for provenance tracking
- Graph schema is defined declaratively in `src/ontology_configs.py` (52 configs)
- Parsers with missing credentials are automatically skipped at runtime
- DrugBank and AOP-DB auto-detect local data files (XML / SQL dump) and work without credentials
- Phase 2 Hetionet component parsers are adapted from the AlzKB updater; integration is functional but not yet fully aligned with the original AlzKB graph structure
