# CardioKB System Design

## 1. System Overview

CardioKB is a CVD-focused biomedical knowledge graph integrating 22 deduplicated data sources into Memgraph. The system consists of four main components:

1. **ETL Pipeline** — Downloads, parses, and loads biomedical data into the graph (runs locally)
2. **Graph Database** — Memgraph instance storing 459K nodes and 5.4M relationships
3. **Web Interface** — Flask backend + vis.js frontend for exploration and querying
4. **AI Agents** — DatabaseAgent (parser generation) and DiseaseQueryAgent (on-demand enrichment)

The web app and Memgraph are fully Dockerized via `docker-compose.yml`. The ETL pipeline runs separately on a development machine.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CardioKB Architecture                            │
│                                                                      │
│  ┌─────────────┐    ┌──────────────┐                                 │
│  │ 22 Data     │───>│ ETL Pipeline │──┐  (runs locally, not in       │
│  │ Sources     │    │ (main.py)    │  │   Docker — pipeline only)    │
│  │ (APIs, FTP, │    └──────────────┘  │                              │
│  │  XML, TSV)  │                      │                              │
│  └─────────────┘                      ▼                              │
│                              ┌─────────────────────────────────┐     │
│  Docker Compose Stack        │                                 │     │
│  ┌───────────────────────────┼─────────────────────────────┐   │     │
│  │                           │                             │   │     │
│  │  ┌──────────────────┐  ┌─┴───────────────────────────┐  │   │     │
│  │  │ Flask App (:5050)│  │ Memgraph (bolt://memgraph:  │  │   │     │
│  │  │                  │──│          7687)               │  │   │     │
│  │  │ /api/query       │  │ 459,092 nodes               │  │   │     │
│  │  │ /api/graph-stats │  │ 5,443,134 relationships     │  │   │     │
│  │  │ /api/agent/*     │  │ 17 node types               │  │   │     │
│  │  │ /api/subgraph    │  │ 27 relationship types       │  │   │     │
│  │  └────────┬─────────┘  └─────────────────────────────┘  │   │     │
│  │           │             Volume: memgraph-data            │   │     │
│  └───────────┼──────────────────────────────────────────────┘   │     │
│              │                                                  │     │
│      ┌───────┴───────┐                                          │     │
│      │ Web Dashboard │   ┌──────────────┐   ┌──────────────┐   │     │
│      │ (index.html)  │   │ DatabaseAgent│   │ DiseaseQuery │   │     │
│      │ vis.js graphs │   │ (Claude API) │   │ Agent        │   │     │
│      └───────────────┘   └──────────────┘   └──────────────┘   │     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Deployment

```bash
# 1. Configure environment
cp .env.example .env   # Set MEMGRAPH_PASSWORD, ANTHROPIC_API_KEY, ADMIN_PASSWORD

# 2. Import graph data
./scripts/import_graph.sh data/export/memgraph-data.tar.gz

# 3. Start
docker compose up -d   # App at http://localhost:5050
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `MEMGRAPH_PASSWORD` | Yes | Memgraph auth (503 without it) |
| `ANTHROPIC_API_KEY` | For AI features | Build Knowledge Graph sidebar |
| `ADMIN_PASSWORD` | For admin features | Pipeline run / add database from UI |

See `.env.example` for the full list with descriptions.

## 2. Graph Statistics

| Metric | Value |
|--------|-------|
| Total nodes | 459,092 |
| Total relationships | 5,443,134 |
| Node types | 17 |
| Relationship types | 27 |
| Data sources | 22 |
| Source labels on edges | 22 (19 data + 3 ML prediction) |
| Ontology configs | 86 |

## 3. Source-to-Schema Mapping

### 3.1 Node Type Ownership

Each node type has exactly one authoritative source that creates/manages those nodes.

| Node Type | Count | Authoritative Source | Key Properties |
|-----------|------:|---------------------|----------------|
| Gene | 193,795 | NCBI Gene | `geneId`, `geneSymbol`, `description`, `xrefEnsembl`, `xrefHGNC`, `xrefOMIM` |
| Variant | 135,555 | ClinVar | `variantId`, `variantName`, `clinicalSignificance`, `xrefDbSNP` |
| Drug | 32,849 | DrugBank + CTD | `drugId`, `commonName`, `xrefDrugBank`, `xrefPubChem`, `xrefMeSH` |
| BiologicalProcess | 24,428 | Gene Ontology | `geneOntologyId`, `processName` |
| ClinicalTrial | 21,578 | ClinicalTrials.gov | `trialId`, `title`, `phase`, `status`, `sponsor` |
| Phenotype | 19,389 | HPO | `phenotypeName`, `xrefHPO` |
| MolecularFunction | 10,056 | Gene Ontology | `functionName`, `geneOntologyId` |
| GeneFamily | 4,257 | HGNC Families | `familyId`, `familyName` |
| CellularComponent | 4,076 | Gene Ontology | `componentName`, `geneOntologyId` |
| Disease | 3,442 | Disease Ontology | `diseaseName`, `definition`, `xrefDiseaseOntology`, `xrefUmlsCUI` |
| Pathway | 2,870 | Reactome | `pathwayId`, `pathwayName` |
| PharmacologicClass | 2,359 | DrugCentral | `classId`, `className` |
| SideEffect | 2,227 | SIDER | `sideEffectName`, `xrefUmlsCUI` |
| BodyPart | 1,400 | Uberon | `bodyPartName`, `xrefUberon` |
| Symptom | 415 | NCBI MeSH | `symptomName`, `xrefMeSH` |
| TranscriptionFactor | 367 | DoRothEA | `tfSymbol` |
| DrugLabel | 29 | ClinPGx | `labelId`, `labelName` |

All nodes carry `specificityScore` (pre-computed: `1.0 / count(Disease neighbors)`; Disease nodes get 0.0, unconnected nodes get 1.0).

### 3.2 Edge Type Ownership

Each row shows the source database, the edge it contributes, the node types it connects, and the current count in the graph.

| Source | Relationship | From → To | Count | Edge Properties |
|--------|-------------|-----------|------:|-----------------|
| **Bgee** | `bodyPartOverexpressesGene` | BodyPart → Gene | 2,749,193 | `expressionScore` |
| **PubTator** | `geneAssociatesWithDisease` | Gene → Disease | 539,964 | — |
| **CTD** | `chemicalIncreasesExpression` | Drug → Gene | 343,823 | — |
| **CTD** | `chemicalDecreasesExpression` | Drug → Gene | 328,726 | — |
| **HPO** | `geneAssociatesWithPhenotype` | Gene → Phenotype | 270,265 | — |
| **STRING** | `geneInteractsWithGene` | Gene → Gene | 229,007 | `confidence` |
| **Reactome** | `geneInPathway` | Gene → Pathway | 137,116 | — |
| **ClinVar** | `variantInGene` | Variant → Gene | 135,393 | — |
| **Gene Ontology** | `geneParticipatesInBiologicalProcess` | Gene → BiologicalProcess | 122,117 | — |
| **Gene Ontology** | `geneAssociatedWithCellularComponent` | Gene → CellularComponent | 90,141 | — |
| **Gene Ontology** | `geneHasMolecularFunction` | Gene → MolecularFunction | 76,612 | — |
| **LINCS L1000** | `compoundUpregulatesGene` | Drug → Gene | 74,854 | `zScore` |
| **SIDER** | `compoundCausesSideEffect` | Drug → SideEffect | 67,721 | — |
| **LINCS L1000** | `compoundDownregulatesGene` | Drug → Gene | 64,661 | `zScore` |
| **ClinVar** | `variantAssociatedWithDisease` | Variant → Disease | 51,323 | — |
| **DrugBank** | `drugBindsGene` | Drug → Gene | 29,363 | — |
| **HGNC** | `geneInFamily` | Gene → GeneFamily | 27,022 | — |
| **DrugCentral** | `compoundInPharmacologicClass` | Drug → PharmacologicClass | 25,687 | — |
| **BindingDB** | `chemicalBindsGene` | Drug → Gene | 22,735 | — |
| **ClinicalTrials.gov** | `STUDIES_CONDITION` | ClinicalTrial → Disease | 20,667 | — |
| **DoRothEA** | `transcriptionFactorInteractsWithGene` | TranscriptionFactor → Gene | 15,082 | `morScore`, `confidence` |
| **ClinVar** | `hasVariant` | Gene → Variant | 8,413 | — |
| **CTD + ClinicalTrials + DrugCentral** | `drugTreatsDisease` | Drug → Disease | 3,782 | — |
| **ClinicalTrials.gov** | `TESTS_INTERVENTION` | ClinicalTrial → Drug | 3,180 | — |
| **Disease Ontology** | `diseaseIsSubtypeOf` | Disease → Disease | 2,581 | — |
| **OpenTargets** | `geneAssociatesWithDisease` | Gene → Disease | 2,132 | — |
| **ML Predictions** | `predictedTreatsDisease` | Drug → Disease | 1,500 | `confidence` |
| **ClinPGx** | `AFFECTS_RESPONSE_TO` | Gene → Drug | 74 | — |

### 3.3 Per-Source Summary

| # | Source | Parser | Access | Nodes Contributed | Edges Contributed | Total Edges |
|---|--------|--------|--------|-------------------|-------------------|------------:|
| 1 | ClinicalTrials.gov | ClinicalTrialsParser | Public API v2 | ClinicalTrial (21,578) | STUDIES_CONDITION, TESTS_INTERVENTION | 23,847 |
| 2 | ClinPGx | ClinPGxParser | Public API | DrugLabel (29) | AFFECTS_RESPONSE_TO | 74 |
| 3 | NCBI Gene | NCBIGeneParser | Public FTP | Gene (193,795) | — | 0 |
| 4 | DoRothEA | DoRothEAParser | Public API | TranscriptionFactor (367) | transcriptionFactorInteractsWithGene | 15,082 |
| 5 | DrugBank | DrugBankParser | XML file | Drug (19,842) | drugBindsGene | 29,363 |
| 6 | Disease Ontology | DiseaseOntologyParser | Public | Disease (3,442) | diseaseIsSubtypeOf | 2,581 |
| 7 | Gene Ontology | GeneOntologyParser | Public | BiologicalProcess (24,428), MolecularFunction (10,056), CellularComponent (4,076) | 3 edge types | 288,870 |
| 8 | Uberon | UberonParser | Public | BodyPart (1,400) | — | 0 |
| 9 | NCBI MeSH | MeSHParser | Public | Symptom (415) | — | 0 |
| 10 | SIDER | SIDERParser | Public | SideEffect (2,227) | compoundCausesSideEffect | 67,721 |
| 11 | LINCS L1000 | LINCS1000Parser | Public | — | compoundUpregulatesGene, compoundDownregulatesGene | 139,515 |
| 12 | DrugCentral | DrugCentralParser | Public | PharmacologicClass (2,359) | compoundInPharmacologicClass, drugTreatsDisease | 25,844 |
| 13 | BindingDB | BindingDBParser | Public | — | chemicalBindsGene | 22,735 |
| 14 | PubTator | PubTatorParser | Public FTP | — | geneAssociatesWithDisease | 539,964 |
| 15 | CTD | CTDParser | Public | Drug (4,572 unique) | chemicalIncreasesExpression, chemicalDecreasesExpression | 675,306 |
| 16 | Bgee | BgeeParser | Public FTP | — | bodyPartOverexpressesGene | 2,749,193 |
| 17 | Jensen TISSUES | JensenTissuesParser | Public | — | geneInteractsWithGene (tissue edges) | — |
| 18 | HPO | HPOParser | Public | Phenotype (19,389) | geneAssociatesWithPhenotype | 270,265 |
| 19 | Reactome | ReactomeParser | Public | Pathway (2,870) | geneInPathway | 137,116 |
| 20 | STRING | STRINGParser | Public | — | geneInteractsWithGene | 229,007 |
| 21 | OpenTargets | OpenTargetsParser | Public | — | geneAssociatesWithDisease | 2,132 |
| 22 | HGNC Families | HGNCFamiliesParser | Public | GeneFamily (4,257) | geneInFamily | 27,022 |
| 23 | ClinVar | ClinVarParser | Public FTP | Variant (135,555) | hasVariant, variantInGene, variantAssociatedWithDisease | 195,129 |

## 4. ETL Pipeline Architecture

### 4.1 Pipeline Flow

```
main.py [--skip-download] [--skip-neo4j]
  │
  ├─ Phase 1: Download (skippable)
  │   └─ Each parser downloads raw data to data/raw/<source>/
  │
  ├─ Phase 2: Parse
  │   └─ Each parser extracts nodes + edges → pandas DataFrames
  │
  ├─ Phase 3: TSV Export
  │   └─ DataFrames written to data/processed/<source>/*.tsv
  │
  ├─ Phase 4: Graph Load (skippable)
  │   └─ memgraph_loader.py reads TSV + ontology_configs.py
  │       → UNWIND-based Cypher batching (batch_size=1000)
  │       → MERGE to prevent duplicates
  │       → Sets r.source on every relationship
  │
  └─ Phase 5: Post-processing
      └─ compute_specificity.py → sets n.specificityScore on all nodes
```

### 4.2 Parser Architecture

All parsers inherit from `BaseParser` (`src/parsers/base_parser.py`):

```python
class BaseParser:
    def download(self)    # Fetch raw data → data/raw/<source>/
    def parse(self)       # Extract nodes + edges → DataFrames
    def export_tsv(self)  # Write DataFrames → data/processed/<source>/
```

Parser categories:
- **Direct (5)**: Custom parsers hitting live APIs/files (ClinicalTrials, ClinPGx, NCBI Gene, DoRothEA, DrugBank)
- **Hetionet-derived (16)**: Parse from Hetionet component files or original source data (in `parsers/hetionet_components/`)
- **Agent-generated (2)**: Created by DatabaseAgent (HGNC Families, ClinVar)

### 4.3 Ontology Configs

86 entries in `src/ontology_configs.py` map TSV files to the graph schema. Two config types:

**Node config:**
```python
{
    "type": "node",
    "node_label": "Gene",
    "file_pattern": "ncbigene_nodes.tsv",
    "id_field": "xrefNcbiGene",
    "properties": ["commonName", "geneSymbol", "chromosome", ...]
}
```

**Relationship config:**
```python
{
    "type": "relationship",
    "rel_type": "drugBindsGene",
    "file_pattern": "drugbank_drug_gene.tsv",
    "source_id_field": "drug_id",
    "target_id_field": "gene_id",
    "source_label": "DrugBank",        # → sets r.source
    "source_node_label": "Drug",
    "target_node_label": "Gene",
    "properties": [...]
}
```

### 4.4 ID Harmonization

Cross-database ID mapping (`src/id_mapping.py`) resolves identifier conflicts:

| Mapping | Purpose |
|---------|---------|
| MeSH → DOID | PubTator disease IDs to Disease Ontology |
| EFO → DOID | OpenTargets disease IDs to Disease Ontology |
| CUI → DOID | DrugCentral disease IDs to Disease Ontology |
| DrugBank ID merging | CTD chemicals matched to existing DrugBank Drug nodes |

## 5. CVD Disease Scoping

### 5.1 Disease Filter

`ontology/disease_filter.txt` → symlink to `ontology/diseases/cvd.txt` (184 CVD terms).

The CVD AND-filter applies strict disease scoping with word-boundary matching to:
- **OpenTargets**: EFO-to-DOID mapped, filtered to CVD diseases → 2,132 edges
- **PubTator**: Literature-mined associations filtered to CVD scope → 539,964 edges
- **ClinVar**: Variant-disease associations filtered to CVD diseases → 195,129 edges
- **ClinicalTrials.gov**: Queries per CVD disease term → 23,847 edges

### 5.2 Available Disease Filters

| File | Terms | Disease Area |
|------|------:|-------------|
| `cvd.txt` | 184 | Cardiovascular disease (active default) |
| `alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `cancer.txt` | 70 | Cancer / oncology |
| `asthma.txt` | 48 | Asthma & respiratory diseases |
| `diabetes.txt` | 52 | Diabetes & metabolic diseases |

### 5.3 CVD Gene List

`ontology/genes/cvd.txt` contains 3,984 CVD gene symbols sourced from OMIM + DisGeNET, cleaned of LOC* loci and OMIM phenotype symbols.

## 6. Web Interface

### 6.1 Backend (Flask, port 5050, Dockerized)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/graph-stats` | GET | Live node/relationship counts from Memgraph |
| `/api/query` | POST | Execute arbitrary Cypher queries |
| `/api/explore` | GET | Disease subgraph exploration with specificity ranking |
| `/api/subgraph` | POST | N-hop disease subgraph extraction (JSON/CSV export) |
| `/api/agent/build` | POST | DiseaseQueryAgent: enrich graph for a disease |
| `/api/agent/build-disease-graph` | POST | SSE-streamed disease graph building with progress |
| `/api/specificity-info` | GET | Specificity score metadata (timestamp, total nodes) |
| `/api/nl2cypher` | POST | Natural language to Cypher translation (CypherGPT by Jay Moran) |

### 6.2 Frontend (interface/index.html)

- **Explore tab**: vis.js force-directed graph with DataSet-based rendering, node type filtering, specificity-ranked results, click-to-inspect detail panels, CSV/JSON export
- **Query tab**: AI-powered natural language querying (powered by [CypherGPT/Eng2Cypher](https://github.com/CenterAIResearch/Eng2Cypher) by Jay Moran) plus Neo4j Browser-style multi-panel results; each query appends a new panel with table/graph tabs
- **Build Knowledge Graph** (sidebar): Claude API standardizes disease name → ClinicalTrials.gov API v2 fetch → Memgraph load → auto-explore
- **Extract Disease Subgraph** (sidebar): 1-3 hop extraction with JSON/CSV export
- **Dashboard**: Live stats from `/api/graph-stats`
- **Admin**: Parser status, health checks, full pipeline trigger

### 6.3 Specificity Scoring

Pre-computed as `n.specificityScore` on every node:
- Formula: `1.0 / count(Disease neighbors)`
- Disease nodes: 0.0 (by definition)
- Nodes with no Disease connections: 1.0
- Script: `scripts/compute_specificity.py` (auto-runs at end of pipeline)
- Metadata stored in `_Metadata` node with timestamp

## 7. AI Agents

### 7.1 DatabaseAgent (`src/database_agent.py`)

Autonomously generates new parsers from a database name + download URL:

1. Downloads first 64KB to detect format (TSV, CSV, JSON, XML)
2. Sends sample + BaseParser source to Claude API → generates parser + ontology configs
3. Saves parser file, registers configs, integrates into pipeline
4. Executes parser, validates output, loads into Memgraph

**2 parsers in production**: HGNC Families, ClinVar

### 7.2 DiseaseQueryAgent (`src/disease_agent.py`)

On-demand disease enrichment via web interface:

1. User enters disease name in "Build Knowledge Graph" sidebar
2. Claude API standardizes the disease name
3. Queries ClinicalTrials.gov API v2 for matching trials
4. Loads results into Memgraph (ClinicalTrial nodes + edges)
5. Caches results in `DiseaseCache` node (same disease returns instantly)
6. SSE-streamed progress to frontend

## 8. Legacy Sources

Two sources use archived/pinned data with no live API replacement:

| Source | Data Vintage | Edges | Why Retained |
|--------|-------------|------:|-------------|
| SIDER | 2015 GitHub commit | 67,721 | Only source for drug → side effect relationships |
| LINCS L1000 | 2020 GitHub commit | 139,515 | Drug expression effects (upreg/downreg); clue.io requires institutional access |

## 9. Deduplication Principles

1. **One authoritative source per edge type** — no two databases contribute the same relationship type, with the exception of `geneAssociatesWithDisease` (OpenTargets curated + PubTator literature-mined = complementary evidence)
2. **12 sources removed** during systematic dedup audit (DisGeNET, GWAS Catalog, Jensen DISEASES, OMIM, WikiPathways, AOP-DB, HGNC base, CellAge, GenAge, Hetionet precomputed, DrugAge, AnAge)
3. **Full rationale** documented in `docs/CardioKB_Redundancy_Changelog.docx`

## 10. Docker Deployment

### 10.1 Container Architecture

The production deployment uses Docker Compose with two services:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `memgraph` | `memgraph/memgraph:latest` | 7687, 7444 | Graph database with persistent volume |
| `app` | Custom (`Dockerfile`) | 5050 | Flask web app (Python 3.11-slim) |

The Flask app connects to Memgraph via `bolt://memgraph:7687` (Docker internal networking). Memgraph data is persisted in a Docker volume (`memgraph-data`) that survives container restarts and redeployments.

### 10.2 Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds Flask app image: Python 3.11-slim, installs requirements.txt, copies src/, interface/, ontology/, reports/, scripts/ |
| `docker-compose.yml` | Defines memgraph + app services, networking, volumes, env var passthrough |
| `.dockerignore` | Excludes data/ (48GB pipeline data), .git, .env, notebooks, docs from build context |
| `.env.example` | Documented template for all environment variables |
| `scripts/export_graph.sh` | Exports Memgraph data volume as tar.gz (~1.2 GB compressed) |
| `scripts/import_graph.sh` | Imports Memgraph data volume on target host |

### 10.3 Graph Data Transfer

The graph (459K nodes, 5.4M rels) is transferred between machines via Memgraph volume backups:

```
Source machine                    Target machine
──────────────                    ──────────────
export_graph.sh                   import_graph.sh
  │ stops Memgraph                  │ creates Docker volume
  │ tars /var/lib/memgraph          │ extracts archive into volume
  │ restarts Memgraph               │ starts Memgraph
  ▼                                 ▼
data/export/memgraph-data.tar.gz  Docker volume: memgraph-data
(~1.2 GB)                         (14 GB uncompressed)
```

### 10.4 Environment Variables

All database connection variables use the `MEMGRAPH_` prefix. See `.env.example` for the full documented list. Key variables:

| Variable | Required | Purpose |
|----------|----------|---------|
| `MEMGRAPH_PASSWORD` | **Yes** | Memgraph auth — web app returns 503 without it |
| `ANTHROPIC_API_KEY` | For AI features | Powers "Build Knowledge Graph" (Claude API) |
| `ADMIN_PASSWORD` | For admin features | Pipeline run, database agent from UI |
