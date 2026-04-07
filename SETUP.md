# CardioKB Setup Guide

## Prerequisites

- Python 3.11 (conda recommended)
- Memgraph (knowledge graph database, via Docker)
- pip or conda package manager

## Installation

### 1. Create a Virtual Environment

**Using conda (recommended):**
```bash
conda create -n cardiokb python=3.11
conda activate cardiokb
```

**Using venv:**
```bash
python -m venv cardiokb
source cardiokb/bin/activate  # On macOS/Linux
# or
cardiokb\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- **neo4j**: Bolt protocol graph database driver (works with Memgraph)
- **pandas & numpy**: Data processing
- **requests**: API calls (DisGeNET, ClinPGx, DoRothEA, etc.)
- **flask**: Web dashboard backend
- **obonet**: OBO ontology parsing (Disease Ontology, Gene Ontology, Uberon)
- **lxml**: XML parsing (DrugBank)
- **scipy**: Scientific computing
- **python-dotenv**: Environment variable management
- **pytest**: Testing framework

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Memgraph (required)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=
NEO4J_PASSWORD=

# OMIM API key (required for OMIM parser)
OMIM_API_KEY=your_key

# DisGeNET API key (required for DisGeNET parser)
DISGENET_API_KEY=your_key

# DrugBank credentials (or place full-database XML at data/raw/drugbank/)
DRUGBANK_USERNAME=your_email
DRUGBANK_PASSWORD=your_password

# MySQL for AOP-DB (or use SQL dump at data/raw/aopdb/)
MYSQL_USERNAME=root
MYSQL_PASSWORD=your_password
```

### Memgraph Setup

1. Install Docker and start Memgraph with persistence:
   ```bash
   docker run -d --name memgraph -p 7687:7687 -p 7444:7444 \
     -v memgraph-data:/var/lib/memgraph memgraph/memgraph:latest \
     --storage-snapshot-interval-sec=300 --storage-wal-enabled=true \
     --storage-snapshot-on-exit=true
   ```
2. Ensure `bolt://localhost:7687` is reachable

## Running the Pipeline

```bash
# Full pipeline: download -> parse -> TSV export -> Memgraph load
python src/main.py

# Parse and export only (no graph loading)
python src/main.py --skip-neo4j

# Use cached downloads (no re-downloading)
python src/main.py --skip-download

# Both flags (parse from cache, no graph load)
python src/main.py --skip-download --skip-neo4j
```

## Web Dashboard

The web dashboard provides interactive graph visualization, Cypher querying, and pipeline health monitoring.

```bash
# Launch Flask server + open browser
./run.sh

# Or manually
python src/api.py --port 5050
```

**Dashboard features:**
- **Explore tab**: Interactive vis.js force-directed graph of disease subgraphs, click nodes to inspect properties and neighbors, filter by node type, export as CSV/JSON
- **Query tab**: Run Cypher queries with results displayed as both table and graph visualization, pre-built query templates for common patterns
- **Sidebar**: Disease filter selector, agent-powered KB builder, health check runner
- **Admin section**: Parser status, health checks, node/relationship charts, pipeline log

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                  # Pipeline orchestrator
│   ├── api.py                   # Flask web backend
│   ├── agent.py                 # AI-powered disease KB builder
│   ├── orchestrator.py          # Pipeline health check
│   ├── neo4j_loader.py          # Cypher-based Memgraph batch loader
│   ├── ontology_configs.py      # 58 ontology configs (source -> graph schema)
│   ├── id_mapping.py            # Cross-database ID remapping
│   ├── utils.py                 # Shared utilities
│   └── parsers/                 # 25 data source parsers
│       ├── base_parser.py       # BaseParser abstract class
│       └── hetionet_components/ # 14 Hetionet-derived component parsers
├── interface/
│   └── index.html               # Web dashboard (Explore + Query tabs)
├── ontology/
│   ├── disease_filter.txt       # Symlink -> diseases/cvd.txt
│   └── diseases/                # Disease term files (cvd, alzheimers, cancer, etc.)
├── data/
│   ├── raw/                     # Downloaded source data
│   └── processed/               # Exported TSV files for Memgraph
├── tests/                       # pytest test files
├── scripts/                     # Data processing and verification scripts
├── reports/                     # Generated pipeline health reports
├── docs/                        # Documentation, research plan
├── .claude/skills/              # Claude Code custom skills
├── run.sh                       # Launch script
└── requirements.txt             # Python dependencies
```

## Data Sources (25 Parsers)

All parsers extend `BaseParser` from `src/parsers/base_parser.py`.

**Credential-gated (require env vars):**
- OMIM (`OMIM_API_KEY`)
- DisGeNET (`DISGENET_API_KEY`)
- DrugBank (`DRUGBANK_USERNAME`/`DRUGBANK_PASSWORD` or XML file)
- AOP-DB (`MYSQL_USERNAME`/`MYSQL_PASSWORD` or SQL dump)

**Public sources (no credentials needed):**
ClinicalTrials.gov, ClinPGx, NCBI Gene, DoRothEA, Disease Ontology, Gene Ontology, Uberon, MeSH, SIDER, LINCS L1000, MEDLINE, DrugCentral, GWAS Catalog, BindingDB, PubTator Central, CTD, Bgee, Hetionet, Jensen Lab DISEASES, Jensen Lab TISSUES, HPO

## Disease Scope

Disease term files in `ontology/diseases/` control which diseases are filtered:

| File | Terms | Area |
|------|-------|------|
| `cvd.txt` | 90 | Cardiovascular disease (default) |
| `alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `cancer.txt` | 70 | Cancer / oncology |
| `asthma.txt` | 48 | Asthma & respiratory diseases |
| `diabetes.txt` | 52 | Diabetes & metabolic diseases |

The active filter is `ontology/disease_filter.txt` (symlink to `diseases/cvd.txt`). Most parsers are disease-agnostic; only DisGeNET accepts a `disease_filter` parameter.

## Running Tests

```bash
pytest tests/
```

## Troubleshooting

### Module Not Found Errors
1. Ensure conda/venv is activated
2. Install dependencies: `pip install -r requirements.txt`
3. Run from project root (parsers use relative imports)

### Memgraph Connection Issues
- Verify Memgraph is running: `docker ps --filter name=memgraph`
- Restart if needed: `docker restart memgraph`
- Ensure bolt port 7687 is not blocked

### Large Downloads
Some sources download large files:
- **ClinicalTrials.gov (AACT)**: ~2.4 GB bulk flat files
- **PubTator Central**: ~4 GB FTP files
- **Bgee**: ~1.5 GB expression data

Use `--skip-download` to reuse cached data after the first run.

## Resources

- [Memgraph Documentation](https://memgraph.com/docs)
- [Neo4j Python Driver (Bolt compatible)](https://neo4j.com/docs/python-manual/current/)
- [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api)
- [DisGeNET API](https://www.disgenet.org/api/)
- [Disease Ontology](https://disease-ontology.org/)
