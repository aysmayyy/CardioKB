# CardioKB System Design

## 1. System Overview

CardioKB is a CVD-focused biomedical knowledge graph integrating 26 deduplicated data sources into Memgraph. The system consists of four main components:

1. **ETL Pipeline** — Downloads, parses, and loads biomedical data into the graph (runs locally)
2. **Graph Database** — Memgraph instance storing 4.9M nodes and 7.7M relationships
3. **Web Interface** — Flask backend + vis.js frontend for exploration and querying
4. **AI Agents** — DatabaseAgent (parser generation) and DiseaseQueryAgent (on-demand enrichment)

The web app and Memgraph are fully Dockerized via `docker-compose.yml`. The ETL pipeline runs separately on a development machine.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CardioKB Architecture                            │
│                                                                      │
│  ┌─────────────┐    ┌──────────────┐                                 │
│  │ 26 Data     │───>│ ETL Pipeline │──┐  (runs locally, not in       │
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
│  │  │ /api/query       │  │ 4,896,258 nodes             │  │   │     │
│  │  │ /api/graph-stats │  │ 7,683,150 relationships     │  │   │     │
│  │  │ /api/agent/*     │  │ 19 node types               │  │   │     │
│  │  │ /api/subgraph    │  │ 43 relationship types       │  │   │     │
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
| Total nodes | 4,896,258 |
| Total relationships | 7,683,150 |
| Node types | 19 |
| Relationship types | 43 |
| Data sources | 26 |
| Source labels on edges | 23 |
| Ontology configs | 86 |

## 3. Source-to-Schema Mapping

### 3.1 Node Type Ownership

Each node type has exactly one authoritative source that creates/manages those nodes.

| Node Type | Count | Authoritative Source | Key Properties |
|-----------|------:|---------------------|----------------|
| Variant | 4,488,042 | ClinVar | `variantId`, `commonName`, `chromosome`, `position`, `changeClassification`, `gene` |
| Gene | 194,553 | NCBI Gene | `xrefNcbiGene`, `geneSymbol`, `commonName`, `chromosome`, `typeOfGene`, `xrefEnsembl`, `xrefHGNC`, `xrefOMIM` |
| ClinicalTrial | 85,691 | ClinicalTrials.gov | `trialId`, `commonName`, `condition`, `interventionName`, `phase`, `status` |
| BiologicalProcess | 24,547 | Gene Ontology | `geneOntologyId`, `commonName`, `definition` |
| Drug | 24,414 | DrugBank + CTD | `xrefDrugbank`, `commonName`, `xrefCasRN` |
| Phenotype | 19,389 | HPO | `xrefHPO`, `commonName`, `definition`, `synonyms` |
| BodyPart | 14,937 | Uberon | `xrefUberon`, `commonName`, `definition` |
| Disease | 12,012 | Disease Ontology | `xrefDiseaseOntology`, `commonName`, `definition` |
| MolecularFunction | 10,123 | Gene Ontology | `geneOntologyId`, `commonName`, `definition` |
| SideEffect | 5,734 | SIDER | `xrefUmlsCUI`, `commonName` |
| Species | 4,645 | AnAge | `speciesName`, `commonName`, `maximumLifespan`, `sampleSize` |
| CellularComponent | 4,069 | Gene Ontology | `geneOntologyId`, `commonName`, `definition` |
| Pathway | 2,806 | Reactome | `pathwayName` |
| GeneFamily | 1,934 | HGNC Families | `familyId`, `familyName` |
| PharmacologicClass | 1,646 | DrugCentral | `classId`, `classType`, `commonName` |
| Symptom | 966 | NCBI MeSH | `xrefMeSH`, `commonName`, `meshTreeNumber` |
| DrugLabel | 378 | ClinPGx | `labelId`, `commonName`, `drug`, `gene`, `regulatorySource`, `testing`, `biomarkerStatus`, `alternateDrugAvailable` |
| TranscriptionFactor | 367 | DoRothEA | `TF` |
| AgeingProperty | 3 | DrugAge | `propertyName` |

All nodes carry `specificityScore` (pre-computed: `1.0 / count(Disease neighbors)`; Disease nodes get 0.0, unconnected nodes get 1.0).

### 3.2 Edge Type Ownership

Each row shows the source database, the edge it contributes, the node types it connects, and the current count in the graph.

| Source | Relationship | From → To | Count | Edge Properties |
|--------|-------------|-----------|------:|-----------------|
| **ClinVar** | `hasVariant` | Gene → Variant | 2,267,095 | — |
| **ClinVar** | `variantInGene` | Variant → Gene | 2,267,095 | — |
| **ClinVar** | `variantAssociatedWithDisease` | Variant → Disease | 99,707 | — |
| **ClinVar** | `associatedWithVariant` | Disease → Variant | 99,707 | — |
| **Bgee** | `bodyPartUnderexpressesGene` | BodyPart → Gene | 784,026 | `expressionScore` |
| **Bgee** | `bodyPartOverexpressesGene` | BodyPart → Gene | 1,872 | `expressionScore` |
| **OpenTargets** | `geneAssociatesWithDisease` | Gene → Disease | 103,879 | — |
| **PubTator** | `geneAssociatesWithDisease` | Gene → Disease | 673,374 | — |
| **PubTator** | `diseaseAssociatesWithDisease` | Disease → Disease | 4,320 | — |
| **Jensen TISSUES** | `geneExpressedInBodyPart` | Gene → BodyPart | 215,235 | — |
| **HPO** | `geneAssociatesWithPhenotype` | Gene → Phenotype | 162,994 | — |
| **LINCS L1000** | `geneRegulatesGene` | Gene → Gene | 150,540 | `zScore` |
| **LINCS L1000** | `compoundUpregulatesGene` | Drug → Gene | 10,278 | `zScore` |
| **LINCS L1000** | `compoundDownregulatesGene` | Drug → Gene | 10,218 | `zScore` |
| **SIDER** | `compoundCausesSideEffect` | Drug → SideEffect | 148,518 | — |
| **STRING** | `geneInteractsWithGene` | Gene → Gene | 121,170 | `confidence` |
| **CTD** | `chemicalIncreasesExpression` | Drug → Gene | 116,451 | — |
| **CTD** | `chemicalDecreasesExpression` | Drug → Gene | 97,951 | — |
| **Gene Ontology** | `geneParticipatesInBiologicalProcess` | Gene → BiologicalProcess | 50,350 | — |
| **Gene Ontology** | `geneHasMolecularFunction` | Gene → MolecularFunction | 26,935 | — |
| **Gene Ontology** | `geneAssociatedWithCellularComponent` | Gene → CellularComponent | 25,794 | — |
| **Reactome** | `geneInPathway` | Gene → Pathway | 44,979 | — |
| **Reactome** | `pathwayContainsGene` | Pathway → Gene | 44,979 | — |
| **ClinicalTrials.gov** | `STUDIES_CONDITION` | ClinicalTrial → Disease | 27,866 | — |
| **ClinicalTrials.gov** | `TESTS_INTERVENTION` | ClinicalTrial → Drug | 17,492 | — |
| **NCBI Gene** | `geneInSpecies` | Gene → Species | 26,417 | — |
| **DrugCentral** | `pharmacologicClassIncludesCompound` | PharmacologicClass → Drug | 16,403 | — |
| **DrugCentral** | `compoundInPharmacologicClass` | Drug → PharmacologicClass | 16,403 | — |
| **DrugCentral** | `drugTreatsDisease` | Drug → Disease | 245 | — |
| **DrugCentral** | `drugPalliatesDisease` | Drug → Disease | 96 | — |
| **DoRothEA** | `transcriptionFactorInteractsWithGene` | TranscriptionFactor → Gene | 12,985 | `morScore`, `confidence` |
| **BindingDB** | `chemicalBindsGene` | Drug → Gene | 12,250 | — |
| **DrugBank** | `drugBindsGene` | Drug → Gene | 12,089 | — |
| **HGNC** | `geneInFamily` | Gene → GeneFamily | 5,123 | — |
| **HGNC** | `familyContainsGene` | GeneFamily → Gene | 5,123 | — |
| **ClinPGx** | `VARIANT_IN` | Variant → Gene | 1,091 | — |
| **ClinPGx** | `drugLabelAnnotatesGene` | DrugLabel → Gene | 503 | — |
| **ClinPGx** | `drugLabelDescribesDrug` | DrugLabel → Drug | 345 | — |
| **ClinPGx** | `AFFECTS_RESPONSE_TO` | Gene → Drug / PharmacologicClass | 243 | — |
| **DrugAge** | `associatedWithAging` | Gene → AgeingProperty | 386 | — |
| **Disease Ontology** | `diseaseIsSubtypeOf` | Disease → Disease | 258 | — |
| **MEDLINE** | `diseaseLocalizesToAnatomy` | Disease → BodyPart | 244 | — |
| **MEDLINE** | `diseasePresentsSymptom` | Disease → Symptom | 117 | — |
| **MEDLINE** | `diseaseResemblesDisease` | Disease → Disease | 4 | — |

### 3.3 Per-Source Summary

| # | Source | Parser | Access | Nodes Contributed | Edges Contributed | Total Edges |
|---|--------|--------|--------|-------------------|-------------------|------------:|
| 1 | ClinicalTrials.gov | ClinicalTrialsParser | Public API v2 | ClinicalTrial (85,691) | STUDIES_CONDITION, TESTS_INTERVENTION | 45,358 |
| 2 | ClinPGx | ClinPGxParser | Public API | DrugLabel (378) | VARIANT_IN, drugLabelAnnotatesGene, drugLabelDescribesDrug, AFFECTS_RESPONSE_TO | 2,182 |
| 3 | NCBI Gene | NCBIGeneParser | Public FTP | Gene (194,553) | geneInSpecies | 26,417 |
| 4 | DoRothEA | DoRothEAParser | Public API | TranscriptionFactor (367) | transcriptionFactorInteractsWithGene | 12,985 |
| 5 | DrugBank | DrugBankParser | XML file | Drug (19,842) | drugBindsGene | 12,089 |
| 6 | Disease Ontology | DiseaseOntologyParser | Public | Disease (12,012) | diseaseIsSubtypeOf | 258 |
| 7 | Gene Ontology | GeneOntologyParser | Public | BiologicalProcess (24,547), MolecularFunction (10,123), CellularComponent (4,069) | 3 edge types | 103,079 |
| 8 | Uberon | UberonParser | Public | BodyPart (14,937) | — | 0 |
| 9 | NCBI MeSH | MeSHParser | Public | Symptom (966) | — | 0 |
| 10 | SIDER | SIDERParser | Public | SideEffect (5,734) | compoundCausesSideEffect | 148,518 |
| 11 | LINCS L1000 | LINCS1000Parser | Public | — | geneRegulatesGene, compoundUpregulatesGene, compoundDownregulatesGene | 171,036 |
| 12 | MEDLINE | MEDLINECooccurrenceParser | Public | — | diseaseLocalizesToAnatomy, diseasePresentsSymptom, diseaseResemblesDisease | 365 |
| 13 | DrugCentral | DrugCentralParser | Public | PharmacologicClass (1,646) | 4 edge types | 33,147 |
| 14 | BindingDB | BindingDBParser | Public | — | chemicalBindsGene | 12,250 |
| 15 | PubTator | PubTatorParser | Public FTP | — | geneAssociatesWithDisease, diseaseAssociatesWithDisease | 677,694 |
| 16 | CTD | CTDParser | Public | Drug (4,572 unique) | chemicalIncreasesExpression, chemicalDecreasesExpression | 214,402 |
| 17 | Bgee | BgeeParser | Public FTP | — | bodyPartUnderexpressesGene, bodyPartOverexpressesGene | 785,898 |
| 18 | Jensen TISSUES | JensenTissuesParser | Public | — | geneExpressedInBodyPart | 215,235 |
| 19 | HPO | HPOParser | Public | Phenotype (19,389) | geneAssociatesWithPhenotype | 162,994 |
| 20 | Reactome | ReactomeParser | Public | Pathway (2,806) | geneInPathway, pathwayContainsGene | 89,958 |
| 21 | STRING | STRINGParser | Public | — | geneInteractsWithGene | 121,170 |
| 22 | OpenTargets | OpenTargetsParser | Public | — | geneAssociatesWithDisease | 103,879 |
| 23 | HGNC Families | HGNCFamiliesParser | Public | GeneFamily (1,934) | geneInFamily, familyContainsGene | 10,246 |
| 24 | ClinVar | ClinVarParser | Public FTP | Variant (4,488,042) | hasVariant, variantInGene, associatedWithVariant, variantAssociatedWithDisease | 4,733,604 |
| 25 | DrugAge | DrugAgeParser | Public | AgeingProperty (3) | associatedWithAging | 386 |
| 26 | AnAge | AnAgeParser | Public | Species (4,645) | — | 0 |

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

All 26 parsers inherit from `BaseParser` (`src/parsers/base_parser.py`):

```python
class BaseParser:
    def download(self)    # Fetch raw data → data/raw/<source>/
    def parse(self)       # Extract nodes + edges → DataFrames
    def export_tsv(self)  # Write DataFrames → data/processed/<source>/
```

Parser categories:
- **Direct (5)**: Custom parsers hitting live APIs/files (ClinicalTrials, ClinPGx, NCBI Gene, DoRothEA, DrugBank)
- **Hetionet-derived (17)**: Parse from Hetionet component files or original source data (in `parsers/hetionet_components/`)
- **Agent-generated (4)**: Created by DatabaseAgent (HGNC Families, ClinVar, DrugAge, AnAge)

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
- **OpenTargets**: EFO-to-DOID mapped, filtered to CVD diseases → 103,879 edges
- **PubTator**: Literature-mined associations filtered to CVD scope → 677,694 edges
- **ClinVar**: Variant-disease associations filtered to CVD diseases → 199,414 edges
- **ClinicalTrials.gov**: Queries per CVD disease term → 45,358 edges

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

### 6.2 Frontend (interface/index.html)

- **Explore tab**: vis.js force-directed graph with DataSet-based rendering, node type filtering, specificity-ranked results, click-to-inspect detail panels, CSV/JSON export
- **Query tab**: Neo4j Browser-style multi-panel results; each query appends a new panel with table/graph tabs
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

**4 parsers in production**: HGNC Families, ClinVar, DrugAge, AnAge

### 7.2 DiseaseQueryAgent (`src/disease_agent.py`)

On-demand disease enrichment via web interface:

1. User enters disease name in "Build Knowledge Graph" sidebar
2. Claude API standardizes the disease name
3. Queries ClinicalTrials.gov API v2 for matching trials
4. Loads results into Memgraph (ClinicalTrial nodes + edges)
5. Caches results in `DiseaseCache` node (same disease returns instantly)
6. SSE-streamed progress to frontend

## 8. Legacy Sources

Three sources use archived/pinned data with no live API replacement:

| Source | Data Vintage | Edges | Why Retained |
|--------|-------------|------:|-------------|
| SIDER | 2015 GitHub commit | 148,518 | Only source for drug → side effect relationships |
| LINCS L1000 | 2020 GitHub commit | 171,036 | Gene regulation + drug expression effects; clue.io requires institutional access |
| MEDLINE | Pinned GitHub commit | 365 | Unique disease → anatomy/symptom cooccurrence not in PubTator |

## 9. Deduplication Principles

1. **One authoritative source per edge type** — no two databases contribute the same relationship type, with the exception of `geneAssociatesWithDisease` (OpenTargets curated + PubTator literature-mined = complementary evidence)
2. **10 sources removed** during systematic dedup audit (DisGeNET, GWAS Catalog, Jensen DISEASES, OMIM, WikiPathways, AOP-DB, HGNC base, CellAge, GenAge, Hetionet precomputed)
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

The graph (4.9M nodes, 7.7M rels) is transferred between machines via Memgraph volume backups:

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
