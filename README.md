# CardioKB — Cardiovascular Disease Knowledge Graph

A biomedical knowledge graph integrating **24 deduplicated data sources** for cardiovascular disease research, feature selection, and precision medicine.

## Current Graph Stats

- **459,092 nodes** | **5,424,652 relationships** | **17 node types** | **22 relationship types** | **16 source labels**
- All relationships carry a `source` property identifying the originating database
- 7 edge types carry quantitative properties (combinedScore, expressionScore, morScore, etc.)

## Quick Start

### Deploy (Docker — recommended)

```bash
git clone https://github.com/aysmayyy/CardioKB.git
cd CardioKB
git checkout baseagent-build

cp .env.example .env           # Fill in MEMGRAPH_PASSWORD, ANTHROPIC_API_KEY, ADMIN_PASSWORD

# Import pre-built graph data (if available)
./scripts/import_graph.sh data/export/memgraph-data.tar.gz

# Launch web app + Memgraph
docker compose up -d           # UI at http://localhost:5050
```

### Local Development

```bash
conda activate cardiokb        # Python 3.11

# Start Memgraph (Docker)
docker run -d --name memgraph -p 7687:7687 -p 3000:3000 \
  -v $(pwd)/data/output:/import-data memgraph/memgraph-platform

# Import graph
docker exec -i memgraph mgconsole < data/output/import.cypher

# Start Flask UI
python src/api.py --port 5050  # http://localhost:5050
```

## Tech Stack

- **Language:** Python 3.11 (conda env: `cardiokb`)
- **Database:** Memgraph (bolt protocol, Neo4j driver compatible)
- **Web UI:** Flask + vis.js (single-page app)
- **Deployment:** Docker Compose (Flask app + Memgraph)
- **Pipeline:** [BaseAgent](https://github.com/BinglanLi/BaseAgent) multi-agent orchestration (`cardiokb` branch)

## Web Interface

The UI at `http://localhost:5050` provides three main features:

- **Explore** — Search any gene, drug, or disease and visualize its neighborhood as an interactive graph. Nodes are ranked by disease-specificity score. Two layers: core (1-hop, evidence-backed) and discovery (2-hop, hypothesis-generating).
- **Query** — Run custom Cypher queries with built-in templates (Disease Subgraph, Gene Neighbors, Drug Targets, Clinical Trials, Gene Expression, etc.). Results shown as tables and/or graph visualizations.
- **Extract Disease Subgraph** — N-hop extraction around any CVD subtype with JSON/CSV export.

## Node Types (17)

| Type | Count | Description |
|------|------:|-------------|
| Gene | 193,795 | Human genes from NCBI Gene |
| Variant | 135,555 | Genetic variants from ClinVar |
| Drug | 32,849 | Compounds from DrugBank + CTD |
| BiologicalProcess | 24,428 | GO biological processes |
| ClinicalTrial | 21,578 | Trials from ClinicalTrials.gov |
| Phenotype | 19,389 | Clinical phenotypes from HPO |
| MolecularFunction | 10,056 | GO molecular functions |
| GeneFamily | 4,257 | Gene families from HGNC |
| CellularComponent | 4,076 | GO cellular components |
| Disease | 3,442 | Diseases from Disease Ontology |
| Pathway | 2,870 | Pathways from Reactome |
| PharmacologicClass | 2,359 | Drug classes from DrugCentral |
| SideEffect | 2,227 | Side effects from SIDER |
| BodyPart | 1,400 | Anatomy from Uberon |
| Symptom | 415 | Symptoms from MeSH |
| TranscriptionFactor | 367 | TFs from DoRothEA |
| DrugLabel | 29 | Pharmacogenomic labels from ClinPGx |

## Relationship Types (22)

| Relationship | Count | Source |
|-------------|------:|--------|
| bodyPartOverexpressesGene | 2,749,193 | Bgee |
| geneAssociatesWithDisease | 539,964 | PubTator |
| chemicalIncreasesExpression | 343,823 | CTD |
| chemicalDecreasesExpression | 328,726 | CTD |
| geneAssociatesWithPhenotype | 270,265 | HPO |
| geneInteractsWithGene | 229,007 | STRING |
| geneInPathway | 137,116 | Reactome |
| variantInGene | 135,393 | ClinVar |
| geneParticipatesInBiologicalProcess | 122,117 | Gene Ontology |
| geneAssociatedWithCellularComponent | 90,141 | Gene Ontology |
| geneHasMolecularFunction | 76,612 | Gene Ontology |
| compoundUpregulatesGene | 74,854 | CTD |
| compoundCausesSideEffect | 67,721 | SIDER |
| compoundDownregulatesGene | 64,661 | CTD |
| variantAssociatedWithDisease | 51,323 | ClinVar |
| drugBindsGene | 29,363 | DrugBank |
| geneInFamily | 27,022 | HGNC |
| compoundInPharmacologicClass | 25,687 | DrugCentral |
| chemicalBindsGene | 22,735 | BindingDB |
| STUDIES_CONDITION | 20,667 | ClinicalTrials.gov |
| transcriptionFactorInteractsWithGene | 15,082 | DoRothEA |
| TESTS_INTERVENTION | 3,180 | ClinicalTrials.gov |

## Edge Properties

7 relationship types carry quantitative data properties beyond `source`:

| Relationship | Properties |
|-------------|-----------|
| geneInteractsWithGene | `combinedScore` (STRING confidence, 0-1000) |
| bodyPartOverexpressesGene | `expressionScore` (Bgee expression level) |
| transcriptionFactorInteractsWithGene | `morScore`, `confidence` (DoRothEA A/B/C/D) |
| geneInPathway | `evidenceCode` (Reactome evidence, e.g. TAS) |
| geneAssociatesWithDisease | `score` (OpenTargets overall score, 0-1) |
| drugBindsGene | `interactionType` (DrugBank action, e.g. inhibitor) |
| variantAssociatedWithDisease | `clinicalSignificance` (ClinVar, e.g. Pathogenic) |

## Project Structure

```
CardioKB/
├── src/
│   ├── api.py                    # Flask web API (5 endpoints)
│   ├── admin_agent.py            # Pipeline health check agent
│   ├── utils.py                  # Shared utilities
│   ├── main.py                   # Pipeline orchestrator
│   ├── memgraph_loader.py        # Cypher-based Memgraph loader
│   ├── ontology_configs.py       # 86 ontology mappings
│   ├── parsers/                  # 24 data source parsers
│   └── export/                   # TSV and Memgraph exporters
├── interface/
│   └── index.html                # Single-page web dashboard
├── eval/                         # 5 evaluation scripts
│   ├── eval_pipeline.py          # Unified 4-stage runner
│   ├── eval_download.py          # Raw data validation
│   ├── eval_parser.py            # Parser output validation
│   ├── eval_load.py              # TSV→Graph load validation
│   └── eval_graph.py             # Live Memgraph validation
├── scripts/
│   ├── compute_specificity.py    # Pre-compute node specificity scores
│   ├── export_graph.sh           # Export Memgraph data volume
│   └── import_graph.sh           # Import Memgraph data volume
├── ontology/
│   ├── disease_filter.txt        # Active disease filter (symlink)
│   └── diseases/                 # CVD, Alzheimer's, cancer, etc.
├── data/
│   ├── raw/                      # Downloaded source data (~21 GB)
│   ├── processed/                # Parsed TSV files
│   └── output/                   # Memgraph CSV + import.cypher
├── docker-compose.yml            # Full stack: Memgraph + Flask
├── Dockerfile                    # Flask app container
└── .env.example                  # Environment variable template
```

## Environment Variables

See `.env.example` for the full list:

| Variable | Purpose |
|----------|---------|
| `MEMGRAPH_URI` | Graph database connection (default: `bolt://localhost:7687`) |
| `MEMGRAPH_USERNAME` / `MEMGRAPH_PASSWORD` | Graph auth (optional for local Docker) |
| `ANTHROPIC_API_KEY` | AI features |
| `ANTHROPIC_FOUNDRY_API_KEY` / `ANTHROPIC_FOUNDRY_BASE_URL` | Azure AI Foundry (preferred) |
| `ADMIN_PASSWORD` | Admin UI features |
| `DRUGBANK_USERNAME` / `DRUGBANK_PASSWORD` | Pipeline only (optional) |

## Pipeline

The graph is built using [BaseAgent](https://github.com/BinglanLi/BaseAgent) on the `cardiokb` branch. The pipeline:

1. **Downloads** raw data from 24 biomedical databases
2. **Parses** each source into standardized TSV files
3. **Populates** an OWL ontology via ista
4. **Exports** Memgraph-compatible CSVs with typed `LOAD CSV` import script

```bash
# Run from ~/Desktop/BaseAgent on the cardiokb branch
python src/main.py                    # Full pipeline
python src/main.py --skip-download    # Use cached data
python src/main.py --skip-neo4j       # Parse + export only
```

## Evaluation

```bash
python eval/eval_pipeline.py          # Run all 4 stages
python eval/eval_graph.py             # Live Memgraph validation only
```

## Data Export/Import

```bash
# Export graph data for transfer
./scripts/export_graph.sh             # -> data/export/memgraph-data.tar.gz

# Import on target host
./scripts/import_graph.sh data/export/memgraph-data.tar.gz
docker compose up -d
```

## Sources (16 in graph)

Bgee, BindingDB, CTD, ClinVar, ClinicalTrials.gov, DoRothEA, DrugBank, DrugCentral, Gene Ontology, HGNC, HPO, LINCS L1000 (legacy), PubTator, Reactome, SIDER (legacy), STRING

Additional parsers available but edges not in current build: MEDLINE (legacy), MeSH (nodes only), NCBI Gene (nodes only), Disease Ontology (nodes only), Uberon (nodes only).
