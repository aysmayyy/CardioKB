# CardioKB: Cardiovascular Disease Knowledge Base

A biomedical knowledge graph pipeline that integrates 25 data sources (25 parsers) into a Neo4j graph for cardiovascular disease research, feature selection, and precision medicine. Adapted from the AlzKB (Alzheimer's Knowledge Base) architecture with additional custom parsers and Hetionet component integrations. Includes an AI-powered disease agent that can build knowledge subgraphs for any disease on demand via Claude API + DisGeNET. Features a web dashboard with interactive graph exploration (specificity-ranked subgraphs) and a Neo4j Browser-style multi-panel query interface.

**Graph stats:** 371,934 nodes | 24,877,691 relationships | 18 node types | 34 relationship types

## Pipeline Status

| Category | Count | Details |
|----------|-------|---------|
| Total databases | 25 | 25 parsers (1 per source) |
| Active & loaded | 24 | Successfully parsed + loaded into Neo4j (verified by r.source query) |
| Credential-gated (loaded) | 4 | OMIM, DisGeNET, DrugBank (XML), AOP-DB (SQL dump) |
| Stale/partial | 1 | MeSH (nodes only, no relationship data) |
| Ontology configs | 59 | Neo4j node/relationship type mappings |
| Source-labeled relationships | 20 | All relationships carry `r.source` property (20 unique source labels) |

## Data Sources

### Phase 1: Core Parsers

| # | Source | Access | Status |
|---|--------|--------|--------|
| 1 | ClinicalTrials.gov | AACT bulk download | Working (576,029 trials, all diseases — full database) |
| 2 | ClinPGx (PharmGKB successor) | Public API | Working (454 annotations, 1,060 variants, 294 AFFECTS_RESPONSE_TO edges) |
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
| 15 | MEDLINE (literature cooccurrence) | Public | Working (7,213 cooccurrence edges) |
| 16 | DrugCentral (drug-disease) | Public | Working (14,572 relationships) |
| 17 | GWAS Catalog (associations) | Public | Working (90,578 gene-disease associations after 3-strategy DOID remap) |
| 18 | BindingDB (drug-target) | Public | Working (23,954 drug-gene bindings via UniProt→Entrez mapping) |
| 19 | PubTator Central (literature mining) | Public FTP | Working (69M+ literature edges) |
| 20 | CTD (chemical-gene) | Public | Working (677,015 expression edges) |
| 21 | Bgee (gene expression) | Public FTP | Working (6,609,112 expression edges) |
| 22 | Hetionet (precomputed edges) | Public | Working (613,470 precomputed edges) |
| 23 | Jensen Lab DISEASES | Public | Working (gene-disease associations) |
| 24 | Jensen Lab TISSUES | Public | Working (988,006 gene-tissue edges, 262 BTO tissue nodes) |
| 25 | HPO (Human Phenotype Ontology) | Public | Working (19,389 phenotypes, 270,272 gene-phenotype edges) |

## Neo4j Graph Schema

**Node types (18):** Gene (193,687), Disease (20,029), Drug (41,566), Pathway (4,646), TranscriptionFactor (367), ClinicalTrial (20,219), Variant (1,060), DrugLabel (378), SideEffect (5,734), PharmacologicClass (1,646), Symptom (966), BodyPart (14,937), BiologicalProcess (24,547), MolecularFunction (10,123), CellularComponent (4,069), Phenotype (19,389), DiseaseCache (3), Chemical (173,500)

**Key relationship types (34):** geneAssociatesWithDisease, geneAssociatesWithPhenotype, geneParticipatesInBiologicalProcess, geneHasMolecularFunction, geneAssociatedWithCellularComponent, geneInteractsWithGene, geneCovariesWithGene, geneRegulatesGene, geneInPathway, geneExpressedInBodyPart, bodyPartUnderexpressesGene, bodyPartOverexpressesGene, chemicalIncreasesExpression, chemicalDecreasesExpression, chemicalBindsGene, compoundCausesSideEffect, compoundUpregulatesGene, compoundDownregulatesGene, pharmacologicClassIncludesCompound, compoundInPharmacologicClass, pathwayContainsGene, drugTreatsDisease, drugPalliatesDisease, diseaseAssociatesWithDisease, diseaseLocalizesToAnatomy, diseasePresentsSymptom, diseaseResemblesDisease, transcriptionFactorInteractsWithGene, drugLabelAnnotatesGene, drugLabelDescribesDrug, AFFECTS_RESPONSE_TO, STUDIES_CONDITION, TESTS_INTERVENTION, VARIANT_IN

**Relationship source labels:** All relationships carry a `source` property (e.g., `DisGeNET`, `GWAS Catalog`, `PubTator`, `Bgee`, etc.) for provenance tracking across 20 source-labeled databases. Disease Ontology contributes nodes only (no relationship source label).

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                 # Pipeline orchestrator (--skip-neo4j, --skip-download)
│   ├── agent.py                # AI disease KB builder (Claude API + DisGeNET)
│   ├── api.py                  # Flask backend with SSE streaming + agent endpoint
│   ├── orchestrator.py         # Health check with dynamic Neo4j parser detection
│   ├── neo4j_loader.py         # Cypher-based Neo4j batch loader
│   ├── ontology_configs.py     # 59 ontology configs for Neo4j schema mapping
│   ├── id_mapping.py           # Central ID mapping: validate, suggest, create_missing_nodes, CLI
│   ├── utils.py                # Disease filtering utilities (load_disease_terms, etc.)
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
│       ├── jensenlab_parser.py
│       ├── jensen_tissues_parser.py
│       ├── hpo_parser.py
│       └── hetionet_components/    # 14 Hetionet-derived component parsers
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
├── interface/
│   └── index.html              # Web dashboard (Explore graph + Query multi-panel UI)
├── scripts/
│   ├── compute_specificity.py  # Pre-compute disease-specificity scores (auto-runs in pipeline)
│   ├── verify_graph.py         # Neo4j graph verification and validation
│   ├── run_aopdb.py            # Standalone AOP-DB parser + Neo4j loader
│   └── run_drugbank.py         # Standalone DrugBank parser + Neo4j loader
├── data/
│   ├── raw/                    # Downloaded source data (gitignored)
│   ├── processed/              # Exported TSV files per source (gitignored)
│   └── output/                 # Release notes and build artifacts (gitignored)
├── ontology/
│   ├── disease_filter.txt         # Symlink → diseases/cvd.txt (active filter)
│   └── diseases/                  # Disease term files (one per disease area)
│       ├── cvd.txt                # Cardiovascular disease (90 terms, default)
│       ├── alzheimers.txt         # Alzheimer's & dementias (35 terms)
│       ├── cancer.txt             # Cancer / oncology (70 terms)
│       ├── asthma.txt             # Asthma & respiratory (48 terms)
│       └── diabetes.txt           # Diabetes & metabolic (52 terms)
├── reports/                    # Pipeline health reports + ID mapping validation report
├── docs/                       # Research plan, specific aims, data inventory xlsx
├── tests/                      # pytest test files
├── .claude/
│   └── skills/                 # Claude Code skill files (auto-loaded for AI-assisted development)
│       └── database-parsing/   # Step-by-step guide for adding new data source parsers
├── models/                     # (Future) ML models
└── run.sh                      # Launches Flask web interface
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

## Disease Scope & Filtering

Disease term files live in **`ontology/diseases/`** (one term per line, `#` for comments):

| File | Terms | Disease Area |
|------|-------|-------------|
| `cvd.txt` | 90 | Cardiovascular disease (default) |
| `alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `cancer.txt` | 70 | Cancer / oncology |
| `asthma.txt` | 48 | Asthma & respiratory diseases |
| `diabetes.txt` | 52 | Diabetes & metabolic diseases |

**`ontology/disease_filter.txt`** is a symlink to `diseases/cvd.txt`. Code that reads it directly (OMIM `is_cvd` tagging, Neo4j CVD node tagging) works without changes.

**ClinicalTrialsParser** downloads the full AACT bulk flat files (~2.4 GB, all 576K+ trials) and is **completely disease-agnostic** — no filtering is applied. Run it once to load all trials.

**DisGeNETParser** is the only parser that accepts a `disease_filter` parameter to target any disease area:

```python
# Target a specific disease area:
DisGeNETParser(data_dir="data/raw", disease_filter="ontology/diseases/cancer.txt")
```

When `disease_filter` is omitted, DisGeNET defaults to `ontology/disease_filter.txt` (→ CVD). OMIMParser reads the symlink to tag rows with `is_cvd` but loads all data regardless. All other 23 parsers are fully disease-agnostic.

## Web Interface

Launch with `bash run.sh` or `python src/api.py --port 5050`. Features:

- **Explore tab** — Interactive vis.js graph visualization of disease subgraphs
  - Nodes ranked by disease-specificity score (`1 / number of diseases connected`)
  - Core layer (direct associations) + Discovery layer (2-hop hypothesis generation)
  - Search by disease name, gene, or drug; filter by node type
  - Click nodes for detail panel with properties, neighbors, and specificity score
  - Export subgraph as CSV or JSON
- **Query tab** — Neo4j Browser-style multi-panel Cypher interface
  - Each query creates a new result panel (newest at top)
  - Panels show results as both table and graph visualization with tab switching
  - Collapse/expand, close individual panels, or Clear All
  - Query templates for common patterns; Ctrl+Enter shortcut
- **Dashboard** — Live graph stats (nodes, relationships, types, sources)
- **Help system** — Welcome tour, tooltips on all UI elements, methodology info, node type legend
- **Admin** — Parser status, pipeline health check with SSE streaming, ID mapping validation report

## Architecture Notes

- All parsers extend `BaseParser` from `src/parsers/base_parser.py`
- Neo4j loading uses UNWIND-based Cypher batching (batch size: 1000) with MERGE to prevent duplicates
- All relationships are tagged with `r.source` property from the config's `source_label` for provenance tracking
- Graph schema is defined declaratively in `src/ontology_configs.py` (59 configs)
- Post-load ID mapping validation automatically checks all relationship match rates and creates missing nodes for low-match configs
- Parsers with missing credentials are automatically skipped at runtime
- DrugBank and AOP-DB auto-detect local data files (XML / SQL dump) and work without credentials
- Phase 2 Hetionet component parsers are adapted from the AlzKB updater; integration is functional but not yet fully aligned with the original AlzKB graph structure
