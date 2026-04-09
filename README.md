# CardioKB: CVD Biomedical Knowledge Graph

A cardiovascular disease (CVD) focused biomedical knowledge graph pipeline that integrates 26 deduplicated data sources into a Memgraph graph for disease research, feature selection, and precision medicine. Each node type and edge type is served by exactly one authoritative database — no redundancy. Adapted from the AlzKB (Alzheimer's Knowledge Base) architecture with custom parsers and AI-powered parser generation. Features a **DatabaseAgent** that autonomously generates new parsers from just a name and URL, a **DiseaseQueryAgent** for on-demand disease enrichment, and a web dashboard with interactive graph exploration and Browser-style querying.

**Graph stats:** 4,896,258 nodes | 7,683,150 relationships | 19 node types | 43 relationship types | 26 sources | 23 source labels
*Stats are current as of last pipeline run; see Memgraph or `GET /api/graph-stats` for live counts.*

## Pipeline Status

| Category | Count | Details |
|----------|-------|---------|
| Total databases | 26 | 26 parsers (1 per source), deduplicated |
| Active & loaded | 26 | Successfully parsed + loaded into Memgraph |
| Integration paths | 3 | Direct (5), Hetionet-derived (17), Agent-generated (4) |
| Legacy (retained as-is) | 3 | SIDER (2015), LINCS L1000 (2020), MEDLINE cooccurrence (pinned) |
| Ontology configs | 86 | Graph node/relationship type mappings |
| Source-labeled relationships | 23 | All relationships carry `r.source` property |

## Data Sources (26)

### Direct Parsers (5)

| # | Source | Access | Status |
|---|--------|--------|--------|
| 1 | ClinicalTrials.gov | Public API v2 | Working (85,691 trials, 27,866 STUDIES_CONDITION + 17,492 TESTS_INTERVENTION edges) |
| 2 | ClinPGx (PharmGKB successor) | Public API | Working (1,091 VARIANT_IN, 503 drugLabelAnnotatesGene, 345 drugLabelDescribesDrug, 243 AFFECTS_RESPONSE_TO edges) |
| 3 | NCBI Gene | Public FTP | Working (194,553 genes, 26,417 geneInSpecies edges) |
| 4 | DoRothEA (OmniPath) | Public API | Working (12,985 TF-gene interactions, with morScore + confidence properties) |
| 5 | DrugBank | XML file | Working (19,842 drugs + 4,572 CTD unique Drug nodes, 12,089 drugBindsGene edges) |

### Hetionet-Derived Component Parsers (17)

| # | Source | Access | Status |
|---|--------|--------|--------|
| 6 | Disease Ontology (DOID) | Public | Working (12,012 diseases, 258 diseaseIsSubtypeOf edges) |
| 7 | Gene Ontology (GO) | Public | Working (50,350 BP + 26,935 MF + 25,794 CC edges) |
| 8 | Uberon (anatomy) | Public | Working (14,937 anatomy nodes) |
| 9 | MeSH (symptoms) | Public | Working (966 symptom nodes) |
| 10 | SIDER (side effects) | Public | Working (5,734 side effects, 148,518 compoundCausesSideEffect edges) -- **Legacy: pinned to 2015 GitHub commit; retained — no live API alternative** |
| 11 | LINCS L1000 (gene expression) | Public | Working (150,540 geneRegulates + 10,218 downreg + 10,278 upreg edges, with zScore) -- **Legacy: pinned to 2020 GitHub commit; retained — clue.io requires institutional access** |
| 12 | MEDLINE (literature cooccurrence) | Public | Working (244 anatomy + 117 symptom + 4 disease cooccurrence edges) -- **Legacy: pinned GitHub commit; retained — unique anatomy/symptom cooccurrence** |
| 13 | DrugCentral (drug-disease) | Public | Working (16,403 pharmacologic class + 245 treats + 96 palliates edges, CUI-to-DOID mapped) |
| 14 | BindingDB (drug-target) | Public | Working (12,250 chemicalBindsGene edges) |
| 15 | PubTator Central (literature mining) | Public FTP | Working (673,374 geneAssociatesWithDisease + 4,320 diseaseAssociatesWithDisease edges after CVD AND-filter) |
| 16 | CTD (chemical-gene) | Public | Working (4,572 unique Drug nodes, 116,451 chemicalIncreasesExpression + 97,951 chemicalDecreasesExpression edges) |
| 17 | Bgee (gene expression) | Public FTP | Working (784,026 underexpresses + 1,872 overexpresses edges, with expressionScore) |
| 18 | Jensen TISSUES (gene-tissue) | Public | Working (215,235 geneExpressedInBodyPart edges) |
| 19 | HPO (Human Phenotype Ontology) | Public | Working (19,389 phenotypes, 162,994 gene-phenotype edges) |
| 20 | Reactome | Public | Working (44,979 geneInPathway + 44,979 pathwayContainsGene edges) |
| 21 | STRING | Public | Working (121,170 geneInteractsWithGene edges, confidence > 700) |
| 22 | OpenTargets | Public | Working (103,879 geneAssociatesWithDisease edges after CVD AND-filter, via EFO-to-DOID mapping) |

### Agent-Generated Parsers (4)

| # | Source | Access | Status |
|---|--------|--------|--------|
| 23 | HGNC Gene Families | Public | Working (1,934 GeneFamily nodes, 5,123 geneInFamily + 5,123 familyContainsGene edges) |
| 24 | ClinVar | Public FTP | Working (4,488,042 Variant nodes, 2,267,095 hasVariant + 2,267,095 variantInGene + 99,707 associatedWithVariant + 99,707 variantAssociatedWithDisease edges) |
| 25 | DrugAge | Public | Working (386 associatedWithAging edges, 3 AgeingProperty nodes) |
| 26 | AnAge | Public | Working (4,645 Species longevity nodes) |

### Sources Removed During Deduplication (10)

The following sources were removed because their data is fully covered by remaining authoritative sources:

| Removed Source | Was Providing | Replaced By |
|---------------|---------------|-------------|
| DisGeNET | 20K gene-disease edges | OpenTargets (curated evidence scores) |
| GWAS Catalog | 45K gene-disease edges | OpenTargets (ingests GWAS directly) |
| Jensen DISEASES | 20K gene-disease edges | OpenTargets (covers text-mining with better scoring) |
| OMIM | 7.3K gene-disease edges | OpenTargets (includes genetic evidence) |
| WikiPathways | 8.6K pathway edges | Reactome (gold-standard curated) |
| AOP-DB | 18.5K pathway edges | Reactome (broader CVD coverage) |
| HGNC (base) | Gene node enrichment | NCBI Gene (primary gene reference) |
| CellAge | Senescence gene nodes | NCBI Gene (already contains these genes) |
| GenAge | Aging gene nodes | NCBI Gene (already contains these genes) |
| Hetionet (precomputed) | 138K side effects + 5K PPI + 127 covariance | SIDER (side effects), STRING (PPI); covariance dropped (127 edges) |

See `docs/CardioKB_Redundancy_Changelog.docx` for full rationale and impact assessment.

## Graph Schema

### Node Types (19)

| Node Type | Count | Source |
|-----------|------:|--------|
| Variant | 4,488,042 | ClinVar |
| Gene | 194,553 | NCBI Gene |
| ClinicalTrial | 85,691 | ClinicalTrials.gov |
| BiologicalProcess | 24,547 | Gene Ontology |
| Drug | 24,414 | DrugBank + CTD |
| Phenotype | 19,389 | HPO |
| BodyPart | 14,937 | Uberon |
| Disease | 12,012 | Disease Ontology |
| MolecularFunction | 10,123 | Gene Ontology |
| SideEffect | 5,734 | SIDER |
| Species | 4,645 | AnAge |
| CellularComponent | 4,069 | Gene Ontology |
| Pathway | 2,806 | Reactome |
| GeneFamily | 1,934 | HGNC Families |
| PharmacologicClass | 1,646 | DrugCentral |
| Symptom | 966 | NCBI MeSH |
| DrugLabel | 378 | ClinPGx |
| TranscriptionFactor | 367 | DoRothEA |
| AgeingProperty | 3 | DrugAge |

### Relationship Types (43)

| Relationship Type | Source | Count |
|-------------------|--------|------:|
| hasVariant | ClinVar | 2,267,095 |
| variantInGene | ClinVar | 2,267,095 |
| bodyPartUnderexpressesGene | Bgee | 784,026 |
| geneAssociatesWithDisease | OpenTargets + PubTator | 777,253 |
| geneExpressedInBodyPart | Jensen TISSUES | 215,235 |
| geneAssociatesWithPhenotype | HPO | 162,994 |
| geneRegulatesGene | LINCS L1000 | 150,540 |
| compoundCausesSideEffect | SIDER | 148,518 |
| geneInteractsWithGene | STRING | 121,170 |
| chemicalIncreasesExpression | CTD | 116,451 |
| variantAssociatedWithDisease | ClinVar | 99,707 |
| associatedWithVariant | ClinVar | 99,707 |
| chemicalDecreasesExpression | CTD | 97,951 |
| geneParticipatesInBiologicalProcess | Gene Ontology | 50,350 |
| geneInPathway | Reactome | 44,979 |
| pathwayContainsGene | Reactome | 44,979 |
| STUDIES_CONDITION | ClinicalTrials.gov | 27,866 |
| geneHasMolecularFunction | Gene Ontology | 26,935 |
| geneInSpecies | NCBI Gene | 26,417 |
| geneAssociatedWithCellularComponent | Gene Ontology | 25,794 |
| TESTS_INTERVENTION | ClinicalTrials.gov | 17,492 |
| compoundInPharmacologicClass | DrugCentral | 16,403 |
| pharmacologicClassIncludesCompound | DrugCentral | 16,403 |
| transcriptionFactorInteractsWithGene | DoRothEA | 12,985 |
| chemicalBindsGene | BindingDB | 12,250 |
| drugBindsGene | DrugBank | 12,089 |
| compoundUpregulatesGene | LINCS L1000 | 10,278 |
| compoundDownregulatesGene | LINCS L1000 | 10,218 |
| geneInFamily | HGNC Families | 5,123 |
| familyContainsGene | HGNC Families | 5,123 |
| diseaseAssociatesWithDisease | PubTator | 4,320 |
| bodyPartOverexpressesGene | Bgee | 1,872 |
| VARIANT_IN | ClinPGx | 1,091 |
| drugLabelAnnotatesGene | ClinPGx | 503 |
| associatedWithAging | DrugAge | 386 |
| drugLabelDescribesDrug | ClinPGx | 345 |
| diseaseIsSubtypeOf | Disease Ontology | 258 |
| drugTreatsDisease | DrugCentral | 245 |
| diseaseLocalizesToAnatomy | MEDLINE | 244 |
| AFFECTS_RESPONSE_TO | ClinPGx | 243 |
| diseasePresentsSymptom | MEDLINE | 117 |
| drugPalliatesDisease | DrugCentral | 96 |
| diseaseResemblesDisease | MEDLINE | 4 |

**Relationship source labels (23):** Bgee, BindingDB, CTD, ClinPGx, ClinVar, ClinicalTrials.gov, Disease Ontology, DoRothEA, DrugAge, DrugBank, DrugCentral, Gene Ontology, HGNC, HPO, Jensen TISSUES, LINCS L1000, MEDLINE, NCBI Gene, OpenTargets, PubTator, Reactome, SIDER, STRING

## Project Structure

```
Cardio-KB/
├── src/
│   ├── main.py                 # Pipeline orchestrator (--skip-neo4j, --skip-download)
│   ├── agent.py                # Base disease agent (Claude API)
│   ├── disease_agent.py        # DiseaseQueryAgent (ClinicalTrials.gov API v2)
│   ├── database_agent.py       # Autonomous parser generator (Claude API + sample download)
│   ├── api.py                  # Flask backend with SSE streaming + agent endpoints
│   ├── orchestrator.py         # Health check with dynamic graph-based parser detection
│   ├── memgraph_loader.py      # Cypher-based Memgraph batch loader
│   ├── ontology_configs.py     # 86 ontology configs for graph schema mapping
│   ├── id_mapping.py           # Central ID mapping: validate, suggest, create_missing_nodes, CLI
│   ├── utils.py                # Disease filtering utilities (load_disease_terms, etc.)
│   └── parsers/
│       ├── base_parser.py      # Abstract base class for all parsers
│       ├── clinicaltrials_parser.py
│       ├── clinpgx_parser.py
│       ├── ncbigene_parser.py
│       ├── dorothea_parser.py
│       ├── drugbank_parser.py
│       ├── jensen_tissues_parser.py
│       ├── hpo_parser.py
│       ├── reactome_parser.py
│       ├── string_parser.py
│       ├── opentargets_parser.py
│       ├── hgncfamilies_parser.py  # Agent-generated
│       ├── clinvar_parser.py       # Agent-generated
│       ├── drugage_parser.py       # Agent-generated
│       ├── anage_parser.py         # Agent-generated
│       └── hetionet_components/    # Hetionet-derived component parsers
│           ├── disease_ontology_parser.py
│           ├── gene_ontology_parser.py
│           ├── uberon_parser.py
│           ├── mesh_parser.py
│           ├── sider_parser.py
│           ├── lincs_parser.py
│           ├── medline_cooccurrence_parser.py
│           ├── drugcentral_parser.py
│           ├── bindingdb_parser.py
│           ├── pubtator_parser.py
│           ├── ctd_parser.py
│           └── bgee_parser.py
├── interface/
│   └── index.html              # Web dashboard (Explore graph + Query multi-panel UI)
├── scripts/
│   ├── compute_specificity.py  # Pre-compute disease-specificity scores (auto-runs in pipeline)
│   ├── verify_graph.py         # Graph verification and validation
│   └── run_drugbank.py         # Standalone DrugBank parser + graph loader
├── data/
│   ├── raw/                    # Downloaded source data (gitignored)
│   ├── processed/              # Exported TSV files per source (gitignored)
│   └── output/                 # Release notes and build artifacts (gitignored)
├── ontology/
│   ├── disease_filter.txt         # Symlink -> diseases/cvd.txt (active filter)
│   ├── schema/
│   │   ├── node_types.txt         # 19 node types with sources
│   │   └── edge_types.txt         # 43 edge types with sources and counts
│   ├── genes/
│   │   └── cvd.txt                # 3,984 CVD gene symbols (OMIM + DisGeNET, cleaned)
│   └── diseases/                  # Disease term files (one per disease area)
│       ├── cvd.txt                # Cardiovascular disease (184 terms, default)
│       ├── alzheimers.txt         # Alzheimer's & dementias (35 terms)
│       ├── cancer.txt             # Cancer / oncology (70 terms)
│       ├── asthma.txt             # Asthma & respiratory (48 terms)
│       └── diabetes.txt           # Diabetes & metabolic (52 terms)
├── database_visualization/
│   ├── cardiokb_databases.csv               # 26 source database inventory
│   ├── cardiokb_source_schema_template.html # D3 force graph template (19 nodes, 43 edges)
│   ├── cardiokb_source_schema_latest.html   # Generated interactive visualization
│   └── build_latest_schema.py               # Build script (injects CSV data into template)
├── reports/                    # Pipeline health reports + ID mapping validation report
├── docs/                       # Research plan, specific aims, changelog, system design
├── .claude/
│   └── skills/                 # Claude Code skill files (auto-loaded for AI-assisted development)
│       └── database-parsing/   # Step-by-step guide for adding new data source parsers
├── models/                     # (Future) ML models
└── run.sh                      # Launches Flask web interface
```

## Running the Pipeline

### Prerequisites

- Python 3.11 (conda env: `cardiokb`)
- Memgraph instance running locally or remotely (only needed without `--skip-neo4j`)

### Installation

```bash
conda activate cardiokb
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required for Memgraph loading
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=
NEO4J_PASSWORD=

# Optional — DrugBank XML auto-detected if present in data/raw/drugbank/
DRUGBANK_USERNAME=<username>
DRUGBANK_PASSWORD=<password>

# Optional
CARDIOKB_LOG_LEVEL=INFO
```

### Run

```bash
# Full pipeline: download -> parse -> TSV export -> Memgraph load
python src/main.py

# Parse and export only (no graph load)
python src/main.py --skip-neo4j

# Re-parse from cached data (no downloads)
python src/main.py --skip-download

# Both flags
python src/main.py --skip-download --skip-neo4j

# Run individual source parsers standalone
python scripts/run_drugbank.py              # DrugBank only (parses XML)
python scripts/run_drugbank.py --skip-neo4j  # Parse + TSV only, no graph load
```

### TSV Export

The pipeline exports all parsed data to `data/processed/<source>/` as tab-separated files. These serve as an archived, reproducible snapshot of each run.

### Verify the Graph

After loading into Memgraph, run the verification script:

```bash
python scripts/verify_graph.py --uri bolt://localhost:7687
```

## Disease Scope & Filtering

CardioKB is scoped to cardiovascular disease. CVD-specific ontology files define the scope:

| File | Contents | Count |
|------|----------|-------|
| `ontology/genes/cvd.txt` | CVD gene symbols (OMIM + DisGeNET, cleaned) | 3,984 genes |
| `ontology/diseases/cvd.txt` | CVD disease terms | 184 terms |
| `ontology/schema/node_types.txt` | Node type definitions | 19 types |
| `ontology/schema/edge_types.txt` | Edge type definitions | 43 types |

**`ontology/disease_filter.txt`** is a symlink to `diseases/cvd.txt`. The **ClinicalTrialsParser** queries ClinicalTrials.gov API v2 per disease term from this filter. All other parsers are disease-agnostic.

Additional disease filters available for future use: `alzheimers.txt` (35), `cancer.txt` (70), `asthma.txt` (48), `diabetes.txt` (52).

## Web Interface

Launch with `bash run.sh` or `python src/api.py --port 5050`. Features:

- **Explore tab** — Interactive vis.js graph visualization of disease subgraphs
  - Nodes ranked by disease-specificity score (`1 / number of diseases connected`)
  - Core layer (direct associations) + Discovery layer (2-hop hypothesis generation)
  - Search by disease name, gene, or drug; filter by node type
  - Click nodes for detail panel with properties, neighbors, and specificity score
  - Export subgraph as CSV or JSON
- **Query tab** — Browser-style multi-panel Cypher interface
  - Each query creates a new result panel (newest at top)
  - Panels show results as both table and graph visualization with tab switching
  - Collapse/expand, close individual panels, or Clear All
  - Query templates for common patterns; Ctrl+Enter shortcut
- **Build Knowledge Graph** (sidebar) — AI-powered disease enrichment
  - Enter any disease name; AI standardizes via Claude, fetches clinical trials from ClinicalTrials.gov API v2
  - Loads data into Memgraph, caches results (same disease returns instantly next time)
  - Auto-opens Explore tab with the disease after building
- **Extract Disease Subgraph** (sidebar) — Extract complete N-hop subgraphs from existing data
  - Configurable hop slider (1-3): 1-hop = direct, 2-hop = shared pathways, 3-hop = broad hypothesis generation
  - Export as JSON or CSV for downstream analysis
- **Dashboard** — Live graph stats (nodes, relationships, types, sources)
- **Admin** — Parser status, pipeline health check, full pipeline run

## DatabaseAgent: Autonomous Parser Generation

The **DatabaseAgent** (`src/database_agent.py`) uses Claude API to autonomously generate complete parsers for new biomedical data sources. Users provide only a database name and a download URL.

### How It Works

1. **Sample download** — Downloads the first 64KB to detect format (TSV, CSV, JSON, XML)
2. **Code generation** — Sends file sample + BaseParser source to Claude, generates parser + ontology configs
3. **Pipeline integration** — Saves parser, adds configs, registers in pipeline
4. **Execute & validate** — Runs parser, validates IDs, loads into Memgraph, verifies counts

### Agent-Generated Parsers in Production

| Source | Nodes/Edges Added |
|--------|-------------------|
| HGNC Gene Families | 1,934 GeneFamily nodes, 5,123 geneInFamily + 5,123 familyContainsGene edges |
| ClinVar | 4,488,042 Variant nodes, 2,267,095 hasVariant + 2,267,095 variantInGene + 99,707 associatedWithVariant + 99,707 variantAssociatedWithDisease edges |
| DrugAge | 386 associatedWithAging edges, 3 AgeingProperty nodes |
| AnAge | 4,645 Species longevity nodes |

## Architecture Notes

- All parsers extend `BaseParser` from `src/parsers/base_parser.py`
- Graph loading uses UNWIND-based Cypher batching (batch size: 1000) with MERGE to prevent duplicates
- All relationships tagged with `r.source` property from config's `source_label`
- Graph schema defined declaratively in `src/ontology_configs.py` (86 configs)
- Each node type and edge type has exactly one authoritative source (no redundancy)
- DrugBank auto-detects local XML file and works without credentials
- 3 legacy sources (SIDER, LINCS L1000, MEDLINE) are flagged for replacement with live alternatives
