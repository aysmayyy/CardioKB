---
name: database-parsing
description: Guide for parsing a new biomedical database and integrating it into CardioKB. Covers identifying data sources, writing parsers extending BaseParser, creating ontology configs, pipeline integration, and testing. Use when adding a new data source, building a new parser, or integrating external biomedical data into the knowledge graph.
---

# How to Parse a New Biomedical Database for CardioKB

## Overview

This skill teaches how to integrate a new biomedical database into CardioKB's knowledge graph pipeline. The process follows a consistent pattern used across all 20+ existing parsers: identify the data, write a parser, configure ontology mappings, register in the pipeline, and verify.

**Pipeline flow:**
```
Download raw data → Parse into DataFrames → Export TSVs → Load into Neo4j
```

## Step 1: Identify Database Type and Access Method

### Access Method Archetypes

| Type | Examples | Key Considerations |
|------|----------|-------------------|
| **Public FTP/HTTP file** | CTD, Bgee, PubTator, NCBI Gene | Compression handling (gzip, zip), large file streaming |
| **REST API** | ClinPGx, ClinicalTrials.gov, DisGeNET | Rate limiting, pagination, caching JSON responses |
| **Bulk XML/JSON** | DrugBank (XML), Hetionet (JSON) | Memory-efficient parsing, streaming for large files |
| **SQL dump** | AOP-DB | Line-by-line parsing of INSERT statements |
| **OBO/OWL ontology** | Disease Ontology, Gene Ontology, Uberon | Requires `obonet` or `pronto` library |

### What to Determine Before Coding

1. **License and access**: Public? API key required? Credential-gated?
2. **Data format**: TSV, CSV, JSON, XML, OBO, SQL dump?
3. **Size**: Small (<100MB) vs large (multi-GB) — affects parsing strategy
4. **Update frequency**: Static vs regularly updated?
5. **ID systems used**: Entrez, DOID, DrugBank, MeSH, UMLS CUI, UniProt?

## Step 2: Decide What to Extract (Nodes vs Edges)

### Existing Node Types in CardioKB

| Node Type | Primary ID Property | Example Source |
|-----------|-------------------|----------------|
| `Gene` | `xrefNcbiGene` (Entrez) | NCBI Gene |
| `Disease` | `xrefDiseaseOntology` (DOID) | Disease Ontology |
| `Drug` | `xrefDrugbank` (DrugBank ID) | DrugBank, AOP-DB |
| `Pathway` | `pathwayName` | AOP-DB |
| `BiologicalProcess` | `geneOntologyId` | Gene Ontology |
| `MolecularFunction` | `geneOntologyId` | Gene Ontology |
| `CellularComponent` | `geneOntologyId` | Gene Ontology |
| `BodyPart` | `xrefUberon` | Uberon |
| `Symptom` | `xrefMeSH` | MeSH |
| `SideEffect` | `xrefUmlsCUI` | SIDER |
| `TranscriptionFactor` | `geneSymbol` | DoRothEA |
| `ClinicalTrial` | `trialId` (NCT ID) | ClinicalTrials.gov |
| `Variant` | `variantId` (rsID) | ClinPGx |
| `DrugLabel` | `labelId` | ClinPGx |
| `PharmacologicClass` | `classId` | DrugCentral |

### Key Design Decisions

- **New node type or existing?** If the database provides gene-disease associations, you likely reference existing Gene and Disease nodes rather than creating new ones.
- **ID mapping**: If the source uses different IDs than CardioKB (e.g., UniProt instead of Entrez), you need a mapping step. See `src/id_mapping.py` and BindingDB's UniProt-to-Entrez mapping pattern.
- **CVD filtering**: Consider whether to filter to cardiovascular-relevant data or load broadly. Check `src/utils.py` for CVD filtering utilities.
- **Deduplication**: If querying by multiple terms (genes, drugs), deduplicate results.

### Common ID Mapping Patterns

```python
# UniProt → Entrez (BindingDB pattern)
# Query UniProt API in batches, cache results to TSV
def _map_uniprot_to_entrez(self, uniprot_ids):
    cache_file = self.source_dir / "uniprot_to_entrez.tsv"
    # Load cache, query API for missing, save back
    ...

# MeSH → DOID (PubTator pattern)
# Use src/id_mapping.py
from src.id_mapping import remap_mesh_to_doid
df = remap_mesh_to_doid(df, mesh_column='mesh_id', doid_column='disease_id')

# GWAS traits → DOID (GWAS pattern)
from src.id_mapping import remap_gwas_to_doid
df = remap_gwas_to_doid(df, trait_column='trait', doid_column='disease_id')
```

## Step 3: Write the Parser

### Parser Location

- **AlzKB base parsers** (inherited from AlzKB): `src/parsers/<name>_parser.py`
- **CardioKB-specific parsers** (new to CardioKB): `src/parsers/<name>_parser.py`
- **Hetionet component parsers** (Hetionet-aligned): `src/parsers/hetionet_components/<name>_parser.py`

Both AlzKB base and CardioKB-specific parsers live in `src/parsers/`. The distinction is origin, not location.

### Template: File-Based Parser

```python
"""
NewSourceParser: Parser for [Source Name].

[Brief description of what this source provides and why it's useful.]

Source: [URL]
Access: [Public/API key/etc.]
License: [License]
"""

import logging
from typing import Dict, Optional
import pandas as pd
from .base_parser import BaseParser  # or ..base_parser for hetionet_components/

logger = logging.getLogger(__name__)


class NewSourceParser(BaseParser):
    """Parser for [Source Name]."""

    SOURCE_URL = "https://example.com/data.tsv.gz"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        # source_name auto-derived from class: "newsource"
        # source_dir = data_dir / "newsource"

    def download_data(self) -> bool:
        """Download source data files."""
        logger.info("Downloading [Source Name]...")

        result = self.download_file(self.SOURCE_URL, "data.tsv.gz")
        if not result:
            logger.error("Failed to download [Source Name]")
            return False

        # Extract if compressed
        self.extract_gzip(self.source_dir / "data.tsv.gz")
        logger.info("Successfully downloaded [Source Name]")
        return True

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse downloaded data into DataFrames."""
        data_path = self.source_dir / "data.tsv"

        if not data_path.exists():
            logger.error(f"File not found: {data_path}")
            return {}

        logger.info(f"Parsing [Source Name] from {data_path}")

        df = pd.read_csv(data_path, sep='\t', comment='#')

        # Filter to human data if applicable
        df = df[df['organism'] == 'Homo sapiens']

        # Extract nodes
        nodes_df = df[['id', 'name']].drop_duplicates()
        nodes_df['source_database'] = 'SourceName'

        # Extract relationships
        rels_df = df[['gene_id', 'disease_id']].drop_duplicates()
        rels_df['source_database'] = 'SourceName'

        result = {
            'nodes': nodes_df,
            'gene_disease_rels': rels_df,
        }

        for key, d in result.items():
            logger.info(f"  {key}: {len(d)} rows")
        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Return schema description for each output DataFrame."""
        return {
            'nodes': {
                'id': 'Source identifier',
                'name': 'Display name',
                'source_database': 'Source database',
            },
            'gene_disease_rels': {
                'gene_id': 'Entrez gene ID',
                'disease_id': 'Disease Ontology ID',
                'source_database': 'Source database',
            },
        }
```

### Template: API-Based Parser

For API-based parsers, add rate limiting and caching:

```python
import json
import time
import requests

class APISourceParser(BaseParser):

    BASE_URL = "https://api.example.com/v1/"
    RATE_LIMIT_DELAY = 1.0  # seconds between requests

    def __init__(self, data_dir=None, use_cache=True):
        super().__init__(data_dir)
        self.use_cache = use_cache
        self.cache_dir = self.source_dir / "cache"
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self._data = []  # in-memory storage

    def _cached_request(self, cache_key, url, params=None):
        """Make API request with caching."""
        cache_file = self.cache_dir / f"{cache_key}.json"

        if self.use_cache and cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)

        response = self.session.get(url, params=params, timeout=20)
        time.sleep(self.RATE_LIMIT_DELAY)

        if response.status_code == 200:
            data = response.json()
            if self.use_cache:
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
            return data
        return None

    def parse_data(self):
        """Parse data, loading from cache if download was skipped."""
        # IMPORTANT: Support --skip-download by loading from cache
        if not self._data:
            self._load_from_cache()
        ...

    def _load_from_cache(self):
        """Load from cached JSON files when download was skipped."""
        if not self.cache_dir.exists():
            return
        for cache_file in sorted(self.cache_dir.glob("*.json")):
            with open(cache_file, 'r') as f:
                data = json.load(f)
            # Process and append to self._data
            ...
```

### Important Patterns

**Always include `source_database` column** in every output DataFrame:
```python
df['source_database'] = 'SourceName'
```

**Filter to human data** when the source contains multi-species data:
```python
df = df[df['tax_id'] == 9606]  # or 'Homo sapiens'
```

**Support `--skip-download`**: If your parser stores data in instance variables during `download_data()`, ensure `parse_data()` can load from cached files when those variables are empty. This is a common bug source.

## Step 4: Write Ontology Configs

Add configs to `src/ontology_configs.py`. Every parsed DataFrame that should load into Neo4j needs a config entry.

### Node Config Template

```python
# Add constant at top of file
NEWSOURCE_NODES = 'nodes'

# Add config entry
f'newsource.{NEWSOURCE_NODES}': {
    'data_type': 'node',
    'node_type': 'ExistingOrNewNodeType',
    'source_filename': f'{NEWSOURCE_NODES}.tsv',
    'parse_config': {
        'headers': True,
        'iri_column_name': 'id',          # unique identifier column
        'data_property_map': {
            'id': 'xrefSourceId',          # TSV column → Neo4j property
            'name': 'commonName',
            'source_database': 'sourceDatabase',
        },
    },
    'merge': True,   # True = MERGE (update existing), False = CREATE
    'skip': False,
},
```

### Relationship Config Template

```python
NEWSOURCE_GENE_DISEASE = 'gene_disease_rels'

f'newsource.{NEWSOURCE_GENE_DISEASE}': {
    'data_type': 'relationship',
    'relationship_type': 'geneAssociatesWithDisease',
    'source_label': 'SourceName',          # REQUIRED — sets r.source property
    'source_filename': f'{NEWSOURCE_GENE_DISEASE}.tsv',
    'parse_config': {
        'headers': True,
        'subject_node_type': 'Gene',
        'subject_column_name': 'gene_id',          # column in TSV
        'subject_match_property': 'xrefNcbiGene',  # Neo4j property to match
        'object_node_type': 'Disease',
        'object_column_name': 'disease_id',
        'object_match_property': 'xrefDiseaseOntology',
    },
    'merge': False,
    'skip': False,
},
```

### Config Rules

1. **Every relationship config MUST include `source_label`** — the loader sets `r.source` from this.
2. **`merge: True`** for nodes that may already exist (e.g., Gene, Disease, Drug). Uses MERGE (upsert).
3. **`merge: False`** for new nodes or relationships. Uses CREATE.
4. **`skip: True`** to define a config but not load it (e.g., if another source covers that edge type).
5. **`inverse_relationship_type`** (optional) creates a reverse edge automatically.
6. **`filter_column` / `filter_value`** (optional) filters rows before loading.
7. **`data_property_map`** on relationships stores edge properties beyond just `source`.

### Common Match Properties

| Node Type | Match Property | ID Format |
|-----------|---------------|-----------|
| Gene | `xrefNcbiGene` | Entrez integer (e.g., `7157`) |
| Gene | `geneSymbol` | Symbol string (e.g., `TP53`) |
| Disease | `xrefDiseaseOntology` | DOID (e.g., `DOID:114`) |
| Disease | `xrefUmlsCUI` | UMLS CUI (e.g., `C0018799`) |
| Drug | `xrefDrugbank` | DrugBank ID (e.g., `DB00945`) |
| Drug | `xrefMeSH` | MeSH ID (e.g., `D001241`) |
| BodyPart | `xrefUberon` | UBERON ID (e.g., `UBERON:0000948`) |
| SideEffect | `xrefUmlsCUI` | UMLS CUI |
| Symptom | `xrefMeSH` | MeSH ID |

## Step 5: Register in the Pipeline

### Add to `src/main.py`

1. **Import the parser** at the top of `_get_parsers()`.
2. **Instantiate it** in the parser list.
3. **Add post-processing** if needed (ID remapping, column transformations).

```python
# In _get_parsers():
from src.parsers.newsource_parser import NewSourceParser
parsers['newsource'] = NewSourceParser(data_dir=self.data_dir)

# If credential-gated:
api_key = os.getenv('NEWSOURCE_API_KEY')
if api_key:
    parsers['newsource'] = NewSourceParser(data_dir=self.data_dir, api_key=api_key)
else:
    logger.warning("NEWSOURCE_API_KEY not set, skipping NewSource")
```

### Post-Processing Hooks

If your source uses IDs that don't match CardioKB's schema, add remapping in the post-processing section of `main.py`:

```python
# Example: prefix IDs, remap to DOID, convert types
if source_name == 'newsource':
    if 'gene_disease_rels' in dataframes:
        df = dataframes['gene_disease_rels']
        df['gene_id'] = df['gene_id'].astype(str)  # ensure string for matching
        dataframes['gene_disease_rels'] = df
```

## Step 6: Test and Verify

### Unit Test

Create `tests/test_newsource_parser.py`:

```python
import pytest
from src.parsers.newsource_parser import NewSourceParser

def test_parser_init():
    parser = NewSourceParser()
    assert parser.source_name == 'newsource'

def test_parse_data_returns_expected_keys():
    parser = NewSourceParser()
    # Requires data to be downloaded first
    result = parser.parse_data()
    if result:  # Only if data exists
        assert 'nodes' in result
        assert 'gene_disease_rels' in result

def test_get_schema():
    parser = NewSourceParser()
    schema = parser.get_schema()
    assert 'nodes' in schema
```

### Verification Checklist

1. **TSV export**: Run `python src/main.py --skip-neo4j` and check `data/processed/newsource/`
2. **Row counts**: Verify TSV files have expected number of rows
3. **Column names**: Ensure TSV columns match ontology config expectations
4. **ID formats**: Check that IDs match the `match_property` format in existing nodes
5. **Neo4j load**: Run full pipeline and verify with:

```cypher
-- Check node counts
MATCH (n:NodeType) WHERE n.sourceDatabase = 'SourceName' RETURN count(n);

-- Check relationship counts
MATCH ()-[r]->() WHERE r.source = 'SourceName' RETURN type(r), count(r);

-- Verify edges connect to existing nodes
MATCH (g:Gene)-[r:newRelType]->(d:Disease) WHERE r.source = 'SourceName'
RETURN count(r), count(DISTINCT g), count(DISTINCT d);
```

6. **Update documentation**:
   - Add source to `CLAUDE.md` data sources table
   - Add source to `README.md`
   - Update graph stats in both files

## Step 7: Document Data Gaps

If a source can't be fully integrated (e.g., missing edge types, partial coverage, API limitations), document why in `docs/data_gaps.md`. This is good scientific practice — future contributors need to know what's missing and why.

### What to Document

- **What's missing**: Which node/edge types from the source aren't loaded?
- **Why**: License restriction? No ID mapping available? API deprecated? Data quality too low?
- **Workaround**: Is another source covering the gap? (e.g., BindingDB covers CbG that DrugBank doesn't export)
- **Future path**: What would it take to close the gap?

### Example Entry

```markdown
## DrugBank — Missing CbG and CrC

**Gap**: DrugBank provides Compound-binds-Gene (CbG) and Compound-resembles-Compound
(CrC) data, but our parser only extracts Drug nodes (C).

**Reason**: DrugBank XML parsing focuses on drug metadata and cross-references.
Extracting binding targets would require parsing <targets> elements with polypeptide
sub-elements and mapping UniProt IDs to Entrez.

**Workaround**: CbG is covered by BindingDB (23,954 edges). CrC (Tanimoto chemical
similarity) has no equivalent source in the pipeline.

**To close**: Extend DrugBankParser to parse <targets> XML elements, or compute
Tanimoto similarity from molecular fingerprints (RDKit).
```

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| `--skip-download` returns empty data | Implement `_load_from_cache()` in `parse_data()` |
| IDs don't match existing nodes | Add ID mapping (UniProt→Entrez, MeSH→DOID, etc.) |
| Missing `source_label` in relationship config | Every relationship config MUST have `source_label` |
| Duplicate edges from multiple query terms | Deduplicate by unique ID or subject+object pair |
| Mixed types in ID columns (int vs string) | Coerce with `df['col'] = df['col'].astype(str)` |
| OBO parsers fail silently | Ensure `obonet` is installed in the conda env |
| Large file causes memory issues | Use chunked reading: `pd.read_csv(..., chunksize=100000)` |
| Node merge overwrites properties | Use `merge: True` carefully; only set properties you want updated |

## Quick Reference: Full Integration Checklist

- [ ] Identify source: URL, format, license, ID systems
- [ ] Decide: new node types or reference existing ones?
- [ ] Write parser in `src/parsers/` extending `BaseParser`
- [ ] Implement `download_data()`, `parse_data()`, `get_schema()`
- [ ] Support `--skip-download` (cache loading)
- [ ] Add `source_database` column to all output DataFrames
- [ ] Add ontology configs in `src/ontology_configs.py`
- [ ] Include `source_label` on every relationship config
- [ ] Register parser in `src/main.py` `_get_parsers()`
- [ ] Add post-processing hooks if ID remapping needed
- [ ] Test: `python src/main.py --skip-neo4j` and check TSVs
- [ ] Test: full pipeline run and verify Neo4j counts
- [ ] Update `CLAUDE.md` and `README.md` with new source
- [ ] Document any data gaps in `docs/data_gaps.md`
