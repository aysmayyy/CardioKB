# CardioKB — Cardiovascular Disease Knowledge Graph

A biomedical knowledge graph integrating **22 data sources** for cardiovascular disease research, feature selection, and precision medicine.

## Current Graph Stats

- **459,092 nodes** | **5,443,134 relationships** | **17 node types** | **27 relationship types** | **22 data sources** + 3 ML prediction sources
- All relationships carry a `source` property identifying the originating database
- 7 edge types carry quantitative properties (combinedScore, expressionScore, morScore, etc.)

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (v2) — [Install Docker](https://docs.docker.com/get-docker/)
- **Graph data archive** (`memgraph-baseagent-2026-06-08.tar.gz`, ~298 MB) — obtain from the project owner or shared storage

### Deploy (Docker — recommended)

```bash
git clone https://github.com/aysmayyy/CardioKB.git
cd CardioKB
git checkout baseagent-build

# 1. Configure environment
cp .env.example .env
# Edit .env — set MEMGRAPH_PASSWORD and ADMIN_PASSWORD (see .env.example for docs)
# Optionally set ANTHROPIC_API_KEY to enable the "Ask AI" natural language query feature

# 2. Import the pre-built graph data
mkdir -p data/export
# Place the tar.gz in data/export/, then:
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-08.tar.gz

# 3. Launch web app + Memgraph
docker compose up -d           # UI at http://localhost:5050
```

The import script will restore the graph into a Docker volume, start Memgraph, and verify the node/relationship counts. The full stack (Memgraph + Flask app) starts with `docker compose up -d`.

### Verify It's Working

```bash
docker compose ps              # Both 'memgraph' and 'app' should be running
curl http://localhost:5050/api/graph-stats   # Should return node/rel counts as JSON
```

Then open http://localhost:5050 in a browser.

### Local Development

```bash
conda activate cardiokb        # Python 3.11

# Start Memgraph via Docker Compose (or standalone)
docker compose up -d memgraph

# Import graph data (volume backup) — only needed once
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-08.tar.gz

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
- **Query** — Ask questions in plain English (powered by [CypherGPT/Eng2Cypher](https://github.com/CenterAIResearch/Eng2Cypher) by Jay Moran) or write Cypher directly. AI translates natural language to Cypher using graph schema introspection, with auto-validation and fuzzy correction. Built-in templates for common queries (Disease Subgraph, Gene Neighbors, Drug Targets, Drug Repurposing, Clinical Trials, etc.). Results shown as tables and/or graph visualizations.
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
│   ├── export_edges.py           # Export graph from Memgraph
│   ├── split_edges.py            # Stratified train/val/test split
│   ├── link_prediction.py        # Node2Vec decoder evaluation
│   ├── link_prediction_rotate.py # RotatE decoder evaluation
│   └── data/                     # Shared exports + per-method subdirs
├── hpc/
│   ├── train_node2vec.py         # Node2Vec training (SLURM)
│   └── train_rotate.py           # RotatE training (SLURM + PyKEEN)
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
./scripts/export_graph.sh             # -> data/export/memgraph-data.tar.gz (~300 MB)

# Import on target host
./scripts/import_graph.sh data/export/memgraph-baseagent-2026-06-08.tar.gz
docker compose up -d
```

## Machine Learning: Drug Repurposing via Link Prediction

CardioKB uses graph embedding methods to predict potential drug-disease treatment relationships not present in the curated knowledge graph. Three embedding methods have been evaluated.

### Methodology

- **Edge splits**: 80/10/10 stratified train/val/test on all edge types (3,782 `drugTreatsDisease` edges)
- **Embeddings trained on train split only** — no data leakage from val/test edges
- **Negative sampling**: 1:1 ratio, excluding all known Drug-Disease edges across all splits
- **Features**: Hadamard product + absolute difference of embeddings + cosine similarity + L2 distance + structural features (shared neighbors, Jaccard, Adamic-Adar, preferential attachment, degree)
- **Therapeutic drug filter**: Only drugs with therapeutic signal edges are considered
- **Three decoders compared**: Cosine similarity, XGBoost, MLP

### Embedding Method Comparison

| Method | Decoder | Test AUROC | Test AUPRC | Hits@100 | Hits@200 |
|--------|---------|-----------|-----------|---------|---------|
| Node2Vec (128-dim) | Cosine | 0.7195 | 0.7142 | 25.2% | — |
| Node2Vec (128-dim) | **XGBoost** | **0.9504** | **0.9579** | **31.1%** | — |
| Node2Vec (128-dim) | MLP | 0.9441 | 0.9535 | 30.8% | — |
| RotatE (256-dim) | Cosine | 0.5299 | 0.5401 | 19.3% | 32.3% |
| RotatE (256-dim) | **XGBoost** | **0.9652** | **0.9655** | **31.1%** | **60.0%** |
| RotatE (256-dim) | MLP | 0.9607 | 0.9588 | 30.7% | 60.9% |
| CompGCN (128-dim) | Cosine | 0.5058 | 0.5041 | 16.9% | 30.2% |
| CompGCN (128-dim) | **XGBoost** | **0.9717** | **0.9709** | **30.5%** | **60.6%** |
| CompGCN (128-dim) | MLP | 0.9625 | 0.9625 | 30.5% | 59.7% |

**Best overall**: CompGCN + XGBoost (Test AUROC = 0.9717, AUPRC = 0.9709)

- CompGCN improves over RotatE by +0.0065 and Node2Vec by +0.0213 AUROC with XGBoost decoder
- CompGCN uses relation-aware message passing (subtraction composition, 2 GCN layers, 32M params)
- All three methods achieve similar Hits@200 (~60%) with learned decoders, suggesting structural features drive ranking
- Cosine decoder near-random for RotatE/CompGCN — embeddings are not optimized for cosine similarity

### Dataset Scale

- **9,735** therapeutic drugs with embeddings
- **457** diseases with embeddings
- **3,026** train / **309** val / **322** test positive `drugTreatsDisease` edges

### Predictions in the Graph

Top 500 predictions per method (confidence >= 0.5) are stored in Memgraph as `predictedTreatsDisease` edges:
- `source: "Node2Vec_LinkPrediction"` — 500 edges
- `source: "RotatE_LinkPrediction"` — 500 edges
- `source: "CompGCN_LinkPrediction"` — 500 edges (pending storage)

These are visible in the web UI as orange dashed lines with a separate toggle. Edge provenance shows confidence score, method, and "not clinically validated" warning.

### ML Pipeline Structure

```
ml/
├── export_edges.py            # Export graph from Memgraph
├── split_edges.py             # 80/10/10 stratified split
├── link_prediction.py         # Node2Vec decoder evaluation
├── link_prediction_rotate.py  # RotatE decoder evaluation
├── link_prediction_compgcn.py # CompGCN decoder evaluation
├── evaluate_xgboost.py        # Node2Vec XGBoost plots/reports
├── evaluate_rotate.py         # RotatE XGBoost plots/reports
├── evaluate_compgcn.py        # CompGCN XGBoost plots/reports
├── store_rotate_predictions.py
├── store_compgcn_predictions.py
└── data/
    ├── edges.tsv, nodes.tsv   # Shared graph export
    ├── splits/                # Shared train/val/test splits
    ├── node2vec/              # Node2Vec embeddings + results
    │   ├── train_embeddings.npz
    │   ├── evaluation_report.json
    │   ├── predictions.tsv
    │   ├── models/            # XGBoost model + embeddings
    │   └── results/           # ROC, PR, confusion matrix plots
    ├── rotate/                # RotatE embeddings + results
    │   ├── rotate_embeddings.npz
    │   ├── training_summary.json
    │   ├── evaluation_report.json
    │   ├── predictions.tsv
    │   ├── models/            # XGBoost model
    │   └── results/           # ROC, PR, confusion matrix plots
    └── compgcn/               # CompGCN embeddings + results
        ├── compgcn_embeddings.npz
        ├── training_summary.json
        ├── evaluation_report.json
        ├── predictions.tsv
        ├── models/            # XGBoost model
        └── results/           # ROC, PR, confusion matrix plots

hpc/
├── train_node2vec.py          # Node2Vec training (HPC)
├── node2vec_job.slurm
├── train_compgcn.py           # CompGCN training (HPC)
├── compgcn_job.slurm
├── train_rotate.py            # RotatE training (HPC, PyKEEN)
└── rotate_job.slurm
```

## Data Sources

**22 active data sources** in the current graph build:

Bgee, BindingDB, ClinicalTrials.gov, ClinPGx, ClinVar, CTD, Disease Ontology (nodes only), DoRothEA, DrugBank, DrugCentral, Gene Ontology, HGNC, HPO, LINCS L1000 (legacy), MeSH (nodes only), NCBI Gene (nodes only), OpenTargets, PubTator, Reactome, SIDER (legacy), STRING, Uberon (nodes only)
