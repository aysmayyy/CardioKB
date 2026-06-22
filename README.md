# CardioKB — Cardiovascular Disease Knowledge Graph

A biomedical knowledge graph integrating **22 data sources** for cardiovascular disease research, feature selection, and precision medicine.

## Current Graph Stats

- **459,092 nodes** | **5,424,652 relationships** | **17 node types** | **22 relationship types** | **22 data sources** (16 with edge source labels + 6 node-only)
- All relationships carry a `source` property identifying the originating database
- 7 edge types carry quantitative properties (combinedScore, expressionScore, morScore, etc.)

## Quick Start

### Deploy (Docker — recommended)

```bash
git clone https://github.com/aysmayyy/CardioKB.git
cd CardioKB
git checkout baseagent-build

cp .env.example .env           # Fill in MEMGRAPH_PASSWORD and ADMIN_PASSWORD

# Download the pre-built graph data tar.gz from Google Drive,
# then place it in data/export/ and import:
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-07.tar.gz

# Launch web app + Memgraph
docker compose up -d           # UI at http://localhost:5050
```

### Local Development

```bash
conda activate cardiokb        # Python 3.11

# Start Memgraph via Docker Compose (or standalone)
docker compose up -d memgraph

# Import graph data (volume backup)
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-07.tar.gz

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

The UI at `http://localhost:5050` provides:

- **Explore** — Search any gene, drug, or disease and visualize its neighborhood as an interactive graph. Nodes are ranked by disease-specificity score. Two layers: core (1-hop, evidence-backed) and discovery (2-hop, hypothesis-generating). ML-predicted drug-disease edges shown as orange dashed lines with a separate toggle. Includes search autocomplete, clickable quick-search examples, and an active graph breadcrumb showing what's currently displayed.
- **Edge Provenance** — Click any edge in the graph to see its source database, evidence scores, and a description of the data source ("Why is this here?"). Predicted edges show their confidence score, model details, and a "not clinically validated" warning.
- **Filters** — Toggle node types and edge types on/off. Show/hide discovery layer and ML-predicted edges independently.
- **Query** — Run custom Cypher queries with built-in templates (Disease Subgraph, Gene Neighbors, Drug Targets, Drug Repurposing with ML predictions, Clinical Trials, Shared Genes, etc.). Save and reuse queries. Results shown as tables and/or graph visualizations.
- **Node Detail** — Click any node to see its properties, then "View All Connections" to browse every connection paginated from the database.
- **Extract Disease Subgraph** — Bulk export of all nodes and edges within N hops of a disease as JSON or CSV. For interactive visualization, use Explore instead.
- **Export** — Download the current graph view as CSV, JSON, or PNG image. Print to PDF via browser.

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
│   ├── api.py                    # Flask web API
│   ├── admin_agent.py            # Pipeline health check agent
│   ├── utils.py                  # Shared utilities
│   ├── main.py                   # Pipeline orchestrator
│   ├── memgraph_loader.py        # Cypher-based Memgraph loader
│   ├── ontology_configs.py       # 86 ontology mappings
│   ├── parsers/                  # Data source parsers
│   └── export/                   # TSV and Memgraph exporters
├── interface/
│   └── index.html                # Single-page web dashboard
├── eval/                         # Evaluation scripts
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
├── ml/
│   ├── graph_export.py           # Export graph to Node2Vec format
│   ├── train_node2vec.py         # Train Node2Vec on train split
│   ├── link_prediction.py        # Evaluate decoders + store predictions
│   └── data/                     # Embeddings, splits, predictions
├── data/
│   ├── raw/                      # Downloaded source data (~21 GB)
│   ├── processed/                # Parsed TSV files
│   └── export/                   # Graph data volume backups
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
| `ADMIN_PASSWORD` | Admin UI features (health check, pipeline run) |
| `ANTHROPIC_API_KEY` | AI features (optional, not needed for web UI) |
| `ANTHROPIC_FOUNDRY_API_KEY` / `ANTHROPIC_FOUNDRY_BASE_URL` | Azure AI Foundry (optional) |
| `DRUGBANK_USERNAME` / `DRUGBANK_PASSWORD` | Pipeline only (optional) |

## Pipeline

The graph is built using [BaseAgent](https://github.com/BinglanLi/BaseAgent) on the `cardiokb` branch. The pipeline:

1. **Downloads** raw data from biomedical databases
2. **Parses** each source into standardized TSV files
3. **Loads** into Memgraph via Cypher-based batch loader

```bash
# Run from ~/Desktop/CardioKB
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
# Export graph data for transfer to another machine
./scripts/export_graph.sh             # -> data/export/memgraph-data.tar.gz (~1.2 GB)

# Import on target host
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-07.tar.gz
docker compose up -d
```

## Machine Learning: Drug Repurposing via Link Prediction

CardioKB includes a Node2Vec-based link prediction pipeline for identifying potential drug-disease relationships not present in the curated knowledge graph.

### Methodology

- **Graph embedding**: Node2Vec (128-dim) trained on the training split only (no data leakage)
- **Edge splits**: 80/10/10 stratified train/val/test on `drugTreatsDisease` edges
- **Negative sampling**: 1:1 ratio, excluding all known Drug-Disease edges across all splits
- **Features**: Hadamard product + absolute difference of embeddings + cosine similarity + L2 distance + structural features (shared neighbors, Jaccard, Adamic-Adar, preferential attachment, degree)
- **Therapeutic drug filter**: Only drugs with therapeutic signal edges (drugBindsGene, drugTreatsDisease, AFFECTS_RESPONSE_TO, etc.) are considered

### Decoder Comparison

| Decoder | Val AUROC | Val AUPRC | Test AUROC | Test AUPRC | MRR | Hits@100 |
|---------|----------|----------|-----------|-----------|------|---------|
| Cosine | 0.7358 | 0.7299 | 0.7195 | 0.7142 | 0.0170 | 0.2516 |
| **XGBoost** | **0.9628** | **0.9670** | **0.9504** | **0.9579** | **0.0196** | **0.3106** |
| MLP | 0.9650 | 0.9671 | 0.9441 | 0.9535 | 0.0196 | 0.3075 |

**Best decoder**: XGBoost (Test AUROC = 0.9504, Test AUPRC = 0.9579)

### Dataset Scale

- **9,735** therapeutic drugs with embeddings
- **457** diseases with embeddings
- **3,026** train / **309** val / **322** test positive `drugTreatsDisease` edges

### Predictions in the Graph

The top 500 predictions (confidence >= 0.5) are stored in Memgraph as `predictedTreatsDisease` edges with a `confidence` property and `source: "Node2Vec_LinkPrediction"`. These are visible in the web UI with orange dashed lines and can be toggled on/off independently.

### Pipeline

```
ml/
├── graph_export.py       # Export graph to Node2Vec format
├── train_node2vec.py     # Train Node2Vec on train split only
├── link_prediction.py    # Evaluate decoders + store predictions
└── data/
    ├── evaluation_report.json   # Full evaluation metrics
    ├── predictions.tsv          # Top 500 ranked predictions
    ├── train_embeddings.npz     # 128-dim Node2Vec embeddings
    ├── nodes.tsv                # Node metadata
    ├── edges.tsv                # All edges
    └── splits/                  # Train/val/test edge splits
```

## Data Sources

**19 active parsers** with data in the current graph build:

Bgee, BindingDB, ClinicalTrials.gov, ClinVar, CTD, Disease Ontology (nodes only), DoRothEA, DrugBank, DrugCentral, Gene Ontology, HGNC, HPO, LINCS L1000 (legacy), MeSH (nodes only), NCBI Gene (nodes only), PubTator, Reactome, SIDER (legacy), STRING

**Node-only sources** (provide nodes but no edges with source labels): NCBI Gene, Disease Ontology, Uberon, MeSH, OpenTargets, ClinPGx
