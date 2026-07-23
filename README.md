# CardioKB — Cardiovascular Disease Knowledge Graph

A biomedical knowledge graph integrating **23 data sources** for cardiovascular disease research, feature selection, and precision medicine.

## Current Graph Stats

- **453,037 nodes** | **5,461,783 relationships** | **17 node types** | **28 relationship types** | **23 data sources** + 2 ML prediction sources
- All relationships carry a `source` property identifying the originating database
- 7 edge types carry quantitative properties (combinedScore, expressionScore, morScore, etc.)

## Quick Start — Deploy in 5 Minutes

### What You Need

1. **Docker** and **Docker Compose** (v2) — [Install Docker](https://docs.docker.com/get-docker/)
2. **Graph data archive** — `memgraph-data.tar.gz` (~304 MB), provided separately
3. **~16 GB RAM** on the server (Memgraph loads the full graph in memory)

### Step 1: Clone the repo

```bash
git clone -b baseagent-build https://github.com/aysmayyy/CardioKB.git
cd CardioKB
```

### Step 2: Configure environment

```bash
cp .env.example .env
```

Open `.env` and set these three values:

| Variable | What to put |
|----------|------------|
| `MEMGRAPH_PASSWORD` | Pick any password |
| `ADMIN_PASSWORD` | Pick any password |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (enables "Ask AI" natural language querying) |

### Step 3: Import the graph data

Place the `memgraph-data.tar.gz` archive anywhere on the machine, then run:

```bash
./scripts/import_graph.sh /path/to/memgraph-data.tar.gz
```

This restores 453,037 nodes and 5,461,783 relationships into a Docker volume. Takes ~30 seconds.

### Step 4: Launch

```bash
docker compose up -d
```

Open **http://localhost:5050** in a browser. Done.

### Verify It's Working

```bash
docker compose ps                            # Both 'memgraph' and 'app' should show "running"
curl http://localhost:5050/api/graph-stats    # Should return {"nodes": 453037, ...}
```

### Local Development

```bash
conda activate cardiokb        # Python 3.11

# Start Memgraph via Docker Compose (or standalone)
docker compose up -d memgraph

# Import graph data (volume backup) — only needed once
./scripts/import_graph.sh data/export/memgraph-data.tar.gz

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
| Drug | 26,794 | Compounds from DrugBank + CTD (deduplicated by xrefDrugBank) |
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

## Relationship Types (28)

| Relationship | Count | Source |
|-------------|------:|--------|
| bodyPartOverexpressesGene | 2,749,193 | Bgee |
| geneAssociatesWithDisease | 542,096 | PubTator + OpenTargets |
| chemicalIncreasesExpression | 343,783 | CTD |
| chemicalDecreasesExpression | 328,708 | CTD |
| geneAssociatesWithPhenotype | 270,265 | HPO |
| geneInteractsWithGene | 229,007 | STRING |
| geneInPathway | 137,116 | Reactome |
| variantInGene | 135,393 | ClinVar |
| geneParticipatesInBiologicalProcess | 122,117 | Gene Ontology |
| geneAssociatedWithCellularComponent | 90,141 | Gene Ontology |
| geneHasMolecularFunction | 76,612 | Gene Ontology |
| compoundUpregulatesGene | 74,854 | CTD |
| compoundCausesSideEffect | 67,646 | SIDER |
| compoundDownregulatesGene | 64,661 | CTD |
| variantAssociatedWithDisease | 51,323 | ClinVar |
| drugBindsGene | 29,363 | DrugBank |
| geneInFamily | 27,022 | HGNC |
| compoundInPharmacologicClass | 24,752 | DrugCentral |
| chemicalBindsGene | 22,735 | BindingDB |
| STUDIES_CONDITION | 20,667 | ClinicalTrials.gov |
| transcriptionFactorInteractsWithGene | 15,082 | DoRothEA |
| drugTreatsPhenotype | 5,714 | DrugBank_Indications |
| hasVariant | 8,413 | ClinVar |
| drugTreatsDisease | 4,852 | CTD + DrugBank_Indications + DrugCentral + ClinicalTrials.gov |
| TESTS_INTERVENTION | 3,178 | ClinicalTrials.gov |
| diseaseIsSubtypeOf | 2,581 | Disease Ontology |
| predictedTreatsDisease | 14,435 | CompGCN (6,607) + RotatE (7,828) Link Prediction |
| AFFECTS_RESPONSE_TO | 74 | ClinPGx |

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
│   ├── link_prediction_rotate.py # RotatE decoder evaluation
│   ├── link_prediction_compgcn.py # CompGCN decoder evaluation
│   ├── score_only.py             # Memory-optimized XGBoost scoring (HPC)
│   ├── store_predictions.py      # Load predictions into Memgraph
│   └── data/                     # Shared exports + per-method subdirs
├── hpc/
│   ├── train_compgcn.py          # CompGCN training (HPC)
│   └── train_rotate.py           # RotatE training (HPC + PyKEEN)
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
./scripts/export_graph.sh             # -> data/export/memgraph-data.tar.gz (~304 MB)

# Import on target host
./scripts/import_graph.sh data/export/memgraph-data.tar.gz
docker compose up -d
```

## Machine Learning: Drug Repurposing via Link Prediction

CardioKB uses graph embedding methods to predict potential drug-disease treatment relationships not present in the curated knowledge graph. Two embedding methods have been evaluated: CompGCN and RotatE.

### Methodology

- **Edge splits**: 80/10/10 stratified train/val/test on all edge types (4,852 curated `drugTreatsDisease` edges post-merge)
- **Embeddings trained on train split only** — no data leakage from val/test edges
- **Negative sampling**: 1:1 ratio, excluding all known Drug-Disease edges across all splits
- **Features**: Hadamard product + absolute difference of embeddings + cosine similarity + L2 distance + structural features (shared neighbors, Jaccard, Adamic-Adar, preferential attachment, degree)
- **Therapeutic drug filter**: Only drugs with therapeutic signal edges are considered
- **Three decoders compared**: Cosine similarity, XGBoost, MLP

### Classification Performance (Post-Merge, July 2026)

| Method | Decoder | Test AUROC | Test AUPRC |
|--------|---------|-----------|-----------|
| RotatE (256-dim) | Cosine | 0.7807 | 0.7569 |
| RotatE (256-dim) | MLP | 0.9810 | 0.9786 |
| RotatE (256-dim) | **XGBoost** | **0.9828** | **0.9812** |
| CompGCN (128-dim) | Cosine | 0.3100 | 0.3810 |
| CompGCN (128-dim) | MLP | 0.9838 | 0.9775 |
| CompGCN (128-dim) | **XGBoost** | **0.9865** | **0.9854** |

### Ranking Performance (Filtered Ranking Protocol, Bordes et al. 2013)

| Method | Decoder | Hits@1 | Hits@3 | Hits@10 | Hits@50 | Hits@100 | Hits@200 | MRR | Med. Rank |
|--------|---------|--------|--------|--------|--------|---------|---------|-----|-----------|
| RotatE (256-dim) | **XGBoost** | **9.5%** | **22.5%** | **43.7%** | **73.4%** | **85.1%** | **94.6%** | **0.2054** | **15.0** |
| CompGCN (128-dim) | **XGBoost** | **14.8%** | **23.2%** | **38.3%** | **70.9%** | **88.1%** | **97.0%** | **0.2284** | **22.0** |

**Best overall**: CompGCN + XGBoost (Test AUROC = 0.9865, AUPRC = 0.9854)

- CompGCN improves over RotatE by +0.0037 AUROC with XGBoost decoder
- CompGCN uses relation-aware message passing (subtraction composition, 2 GCN layers, 32M params)
- Both methods achieve similar Hits@200 (~95%) with learned decoders, suggesting structural features drive ranking
- CompGCN has higher MRR (0.2284 vs 0.2054) but higher median rank (22 vs 15) — CompGCN better at reciprocal ranking, RotatE slightly tighter at top-of-list
- Cosine decoder near-random for CompGCN (0.31) — embeddings are not optimized for cosine similarity
- RotatE Cosine (0.78) performs better than CompGCN Cosine due to inherent distance-based scoring

### Dataset Scale

- **10,310** therapeutic drugs with embeddings
- **2,640** diseases with embeddings (CompGCN) / **2,296** (RotatE)
- **4,469** `drugTreatsDisease` edges in ML export (stratified 80/10/10 split)
- **4,852** total `drugTreatsDisease` edges in live graph (CTD: 3,099, DrugBank_Indications: 1,449, DrugCentral: 157, ClinicalTrials.gov: 147)

### Predictions in the Graph

Top predictions per method stored in Memgraph as `predictedTreatsDisease` edges (confidence >= 0.5):
- `source: "CompGCN_LinkPrediction"` — 6,607 edges (1,038 drugs x 37 diseases, confidence 0.989–0.991; primary, shown in web UI)
- `source: "RotatE_LinkPrediction"` — 7,828 edges (1,165 drugs x 142 diseases, confidence 0.993–0.997; comparison, queryable via Cypher)
- **Total: 14,435** predicted edges

These are visible in the web UI as orange dashed lines with a separate toggle. Edge provenance shows confidence score, method, and "not clinically validated" warning.

### Methodology Notes

**ClinicalTrials.gov Inference Fix.** The original ClinicalTrials.gov parser inferred `drugTreatsDisease` edges from any Phase 3/4 trial linking a drug intervention to a disease condition, yielding 868 edges. A subsequent audit revealed that many of these were spurious: trials with non-treatment primary purposes (e.g., Prevention, Diagnostic), drugs serving as comparators rather than experimental interventions, and diseases matching secondary rather than primary conditions. Four filters were applied: (1) `primaryPurpose == "TREATMENT"`, (2) drug must be in an EXPERIMENTAL arm, (3) disease must match the first-listed condition, (4) edges carry a `trialCount` property. This reduced ClinicalTrials.gov drugTreatsDisease edges from 868 to 147 (83.1% reduction).

**Duplicate Drug Node Merge (Entity Resolution).** The BaseAgent pipeline created duplicate Drug nodes when multiple sources (DrugBank, CTD, ClinPGx, DrugCentral) loaded the same compound under different internal `drugId` values but shared the same `xrefDrugBank` canonical identifier. A post-hoc entity resolution step (`scripts/merge_duplicate_drugs.py`) identified 5,611 duplicate groups (2x–8x duplication, including salt/ester forms), removed 6,055 duplicate nodes, transferred 474,641 edges to survivor nodes, and deduplicated 9,094 redundant edges. This reduced Drug nodes from 32,849 to 26,794. All ML models were retrained on the merged graph with zero cross-split leakage confirmed.

**Stale Memgraph-ID Bug Fix.** After the drug node merge deleted 6,055 nodes, Memgraph recycled their internal IDs. The original `store_predictions.py` matched Drug/Disease nodes by `memgraph_id` from a stale `nodes.tsv` export, causing predicted edges to land on wrong node types (Gene, PharmacologicClass, SideEffect) that had inherited the recycled IDs. This was detected when the UI showed lab reagents and food chemicals as predicted treatments. The fix rewrote `store_predictions.py` to match nodes by name from the live graph instead of stale file-based IDs, making it permanently robust to ID recycling.

### Why CompGCN Is the Primary Model

CompGCN was selected as the primary model for the live web UI based on three factors: (1) highest test AUROC (0.9865 vs RotatE's 0.9828), (2) relation-aware message passing that distinguishes between the 27 relationship types in the graph, and (3) efficient training (~7 min vs RotatE's ~3.4 hrs). RotatE predictions remain stored in the graph and are queryable via Cypher in the Query tab, but only CompGCN predictions are shown in the interactive Explore tab. Both methods achieve comparable ranking performance (Hits@200: 97.0% vs 94.6%), confirming that CompGCN's selection is justified by the AUROC advantage plus practical training efficiency.

### Known Limitations

- **Confidence scores reflect ranking, not calibrated probability.** The XGBoost decoder outputs values between 0 and 1 representing how closely a drug-disease pair's embedding geometry matches known treatment relationships. A confidence of 0.99 means the pair ranks very highly among candidates, not that there is a 99% chance the drug treats the disease. The CompGCN predictions span a narrow confidence range (0.989–0.991) and RotatE spans 0.993–0.997, indicating uniform model confidence across top-ranked predictions. All predicted edges carry a "not clinically validated" warning in the web UI.
- **Pharmacologic-class parent nodes in predictions.** A subset of top predictions involve PharmacologicClass parent nodes (e.g., "ACE Inhibitors", "HMG-CoA Reductase Inhibitors") rather than specific Drug compounds. These class-level predictions are structurally valid (the class node has edges to member drugs) but are less actionable than compound-specific predictions. They reflect the graph structure where drug classes aggregate member drugs' connectivity.
- **Hub-driven prediction concentration.** CompGCN predictions concentrate on high-degree Disease hub nodes: the top 6 diseases (heart disease, coronary artery disease, hypertension, atherosclerosis, congestive heart failure, myocardial infarction) account for a disproportionate share of predictions. This is expected — diseases with more known drug edges provide stronger training signal — but means rarer CVD conditions receive fewer or no predictions.
- **Limited graph connectivity drugs.** Some predicted drugs have limited graph connectivity beyond a `compoundInPharmacologicClass` edge to a class node. These predictions are driven primarily by the class node's embedding rather than the drug's own pharmacological profile, making them lower-confidence hypotheses despite high model scores.
- **Disease-specific embedding dominance (CompGCN).** Pulmonary embolism has substantial overall graph connectivity (6,859 incoming edges) but received only 1 CompGCN prediction (rank 7,861 of 10,000), because 92.9% of its edges are `geneAssociatesWithDisease` relationships versus only 46 `drugTreatsDisease` edges. CompGCN's neighborhood-aggregation mechanism causes its embedding for PE to be dominated by gene-association signal rather than drug-treatment signal, suppressing confident predictions even though the disease is well-represented in the graph overall. RotatE, which learns independent per-entity embeddings rather than aggregating neighbor information, was less susceptible to this effect and produced 75 predictions for PE. As a positive case study: among RotatE's PE predictions, Dabigatran (the active thrombin inhibitor, a separate Drug node from its prodrug Dabigatran etexilate) was predicted to treat PE despite having no curated `drugTreatsDisease` edge for PE — only a CTD edge to stroke. The prodrug form does have a curated PE indication (DrugBank_Indications), so the model effectively bridged the active-metabolite/prodrug entity gap, illustrating both the model's ability to surface pharmacologically valid connections and the role entity resolution plays in prediction quality.

### ML Pipeline Structure

```
ml/
├── export_edges.py            # Export graph from Memgraph
├── split_edges.py             # 80/10/10 stratified split
├── link_prediction_rotate.py  # RotatE decoder evaluation
├── link_prediction_compgcn.py # CompGCN decoder evaluation
├── evaluate_rotate.py         # RotatE XGBoost plots/reports
├── evaluate_compgcn.py        # CompGCN XGBoost plots/reports
├── score_only.py              # Memory-optimized XGBoost scoring (HPC)
├── store_predictions.py       # Load predictions into Memgraph
└── data/
    ├── edges.tsv, nodes.tsv   # Shared graph export
    ├── splits/                # Shared train/val/test splits
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
├── train_compgcn.py           # CompGCN training (HPC)
├── compgcn_job.slurm
├── train_rotate.py            # RotatE training (HPC, PyKEEN)
├── rotate_job.slurm
└── score_job.slurm            # XGBoost scoring (HPC, CPU-only)
```

## Data Sources

**23 active data sources** in the current graph build:

Bgee, BindingDB, ClinicalTrials.gov, ClinPGx, ClinVar, CTD, Disease Ontology (nodes only), DoRothEA, DrugBank, DrugBank_Indications (text-mined), DrugCentral, Gene Ontology, HGNC, HPO, LINCS L1000 (legacy), MeSH (nodes only), NCBI Gene (nodes only), OpenTargets, PubTator, Reactome, SIDER (legacy), STRING, Uberon (nodes only)
