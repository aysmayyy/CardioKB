# CardioKB Setup Guide

## Option 1: Docker Deployment (Recommended)

The easiest way to run CardioKB. Bundles the Flask web app and Memgraph graph database into a single Docker Compose stack.

### Prerequisites

- Docker and Docker Compose
- The graph export archive (`data/export/memgraph-data.tar.gz`)

### Steps

#### 1. Clone the Repository

```bash
git clone <repo-url>
cd Cardio-KB
```

#### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

| Variable | Required | Purpose |
|----------|----------|---------|
| `MEMGRAPH_PASSWORD` | **Yes** | Memgraph authentication. The web app returns 503 on all graph endpoints without this. |
| `MEMGRAPH_URI` | No | Auto-set to `bolt://memgraph:7687` inside Docker Compose. Only change for external Memgraph. |
| `MEMGRAPH_USERNAME` | No | Leave blank for default Memgraph auth. |
| `ANTHROPIC_API_KEY` | For AI features | Powers the "Build Knowledge Graph" sidebar feature that uses Claude API to enrich the graph with clinical trials for any disease on demand. Get a key at https://console.anthropic.com/ |
| `ADMIN_PASSWORD` | For admin features | Password for admin-only UI features: running the full ETL pipeline and adding new database sources via the DatabaseAgent. |
| `DRUGBANK_USERNAME` | For pipeline rebuild | Only needed if re-running the ETL pipeline from scratch. |
| `DRUGBANK_PASSWORD` | For pipeline rebuild | Alternatively, place the DrugBank XML file at `data/raw/drugbank/`. |

#### 3. Import the Graph Data

The pre-built graph (459K nodes, 5.4M relationships) is distributed as a compressed Memgraph volume backup (~1.2 GB):

```bash
./scripts/import_graph.sh data/export/memgraph-data.tar.gz
```

This creates a Docker volume with the full graph data and starts Memgraph.

#### 4. Start the Stack

```bash
docker compose up -d
```

The web interface is now live at **http://localhost:5050**.

#### Verify

```bash
# Check both containers are running
docker compose ps

# Test the API
curl http://localhost:5050/api/graph-stats
```

#### Stop / Restart

```bash
docker compose down      # Stop (data persists in Docker volume)
docker compose up -d     # Restart
```

### Docker Architecture

```
docker compose up -d
  ├── memgraph     (memgraph/memgraph:latest)  — Graph database on port 7687
  │                 Volume: memgraph-data (persists across restarts)
  └── app          (Dockerfile, Python 3.11)   — Flask web app on port 5050
                    Connects to bolt://memgraph:7687
```

### Graph Export (for transferring to another host)

```bash
# Export from current Memgraph instance
./scripts/export_graph.sh
# Produces: data/export/memgraph-data.tar.gz (~1.2 GB)

# Transfer to target host and import
scp data/export/memgraph-data.tar.gz user@host:/path/to/Cardio-KB/data/export/
ssh user@host "cd /path/to/Cardio-KB && ./scripts/import_graph.sh data/export/memgraph-data.tar.gz"
```

---

## Option 2: Local Development Setup

For running the ETL pipeline or developing new parsers.

### Prerequisites

- Python 3.11 (conda recommended)
- Memgraph (via Docker or native install)
- pip or conda package manager

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
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- **neo4j**: Bolt protocol graph database driver (compatible with Memgraph)
- **pandas & numpy**: Data processing
- **requests**: API calls (ClinPGx, DoRothEA, ClinicalTrials.gov, etc.)
- **flask**: Web dashboard backend
- **obonet**: OBO ontology parsing (Disease Ontology, Gene Ontology, Uberon)
- **lxml**: XML parsing (DrugBank)
- **scipy**: Scientific computing
- **python-dotenv**: Environment variable management

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum set `MEMGRAPH_PASSWORD`.

### 4. Start Memgraph

```bash
docker run -d --name memgraph -p 7687:7687 -p 7444:7444 \
  -v memgraph-data:/var/lib/memgraph memgraph/memgraph:latest \
  --storage-snapshot-interval-sec=300 --storage-wal-enabled=true \
  --storage-snapshot-on-exit=true
```

### 5. Run the Pipeline

```bash
# Full pipeline: download -> parse -> TSV export -> Memgraph load
python src/main.py

# Parse and export only (no graph loading)
python src/main.py --skip-neo4j

# Use cached downloads (no re-downloading)
python src/main.py --skip-download
```

### 6. Launch Web Dashboard (local dev)

```bash
./run.sh
# or
python src/api.py --port 5050
```

---

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                  # Pipeline orchestrator
│   ├── api.py                   # Flask web backend
│   ├── agent.py                 # Base disease agent (Claude API)
│   ├── disease_agent.py         # DiseaseQueryAgent (ClinicalTrials.gov API v2)
│   ├── database_agent.py        # Autonomous parser generator (Claude API)
│   ├── orchestrator.py          # Pipeline health check
│   ├── memgraph_loader.py       # Cypher-based Memgraph batch loader
│   ├── ontology_configs.py      # 86 ontology configs (source -> graph schema)
│   ├── id_mapping.py            # Cross-database ID remapping
│   ├── utils.py                 # Shared utilities
│   └── parsers/                 # 28 data source parsers (24 active + 4 legacy/unused)
├── interface/
│   └── index.html               # Web dashboard (Explore + Query tabs)
├── scripts/
│   ├── export_graph.sh          # Export Memgraph data for deployment
│   ├── import_graph.sh          # Import Memgraph data on target host
│   ├── compute_specificity.py   # Pre-compute disease-specificity scores
│   └── verify_graph.py          # Graph verification
├── ontology/                    # Disease term files, gene lists, schema definitions
├── data/                        # Raw downloads, processed TSVs, export archives
├── Dockerfile                   # Flask web app container
├── docker-compose.yml           # Full stack: Memgraph + Flask app
├── .env.example                 # Environment variable template
└── requirements.txt             # Python dependencies
```

## Troubleshooting

### Docker Issues
- **Port conflict**: If port 5050 or 7687 is in use, stop existing services or change ports in `docker-compose.yml`
- **Volume permissions**: Run `docker compose down -v` to reset volumes (destroys graph data — re-import needed)
- **Container logs**: `docker compose logs app` or `docker compose logs memgraph`

### Module Not Found Errors (local dev)
1. Ensure conda/venv is activated
2. Install dependencies: `pip install -r requirements.txt`
3. Run from project root (parsers use relative imports)

### Memgraph Connection Issues
- Verify Memgraph is running: `docker ps --filter name=memgraph`
- Restart if needed: `docker restart memgraph`
- Ensure bolt port 7687 is not blocked

### Large Downloads (pipeline only)
Some sources download large files:
- **PubTator Central**: ~4 GB FTP files
- **Bgee**: ~1.5 GB expression data
- **ClinVar**: ~1.5 GB variant summary

Use `--skip-download` to reuse cached data after the first run.

## Resources

- [Memgraph Documentation](https://memgraph.com/docs)
- [Neo4j Python Driver (Bolt compatible)](https://neo4j.com/docs/python-manual/current/)
- [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api)
- [Disease Ontology](https://disease-ontology.org/)
