# CardioKB Evaluation Scripts

Two standalone evaluation scripts for the CardioKB knowledge graph pipeline.
Run them after the corresponding pipeline stage completes.

## Scripts

| Script | Run After | Key Inputs |
|--------|-----------|-----------|
| `eval_after_parser.py` | All parsers complete | `data/processed/<source>/*.tsv` |
| `eval_after_memgraph.py` | Memgraph data loaded | Live Memgraph + TSV files |

---

## 1. `eval_after_parser.py`

Reads `src/ontology_configs.py` to discover all expected TSV files and computes
post-parser quality metrics.

### Metrics

| Tier | Metric | Description |
|------|--------|-------------|
| 1 | Source database extraction | Pass/Fail per TSV file |
| 1 | TSV structural integrity | All rows have expected column count (RFC-4180 aware) |
| 1 | Extracted record counts | Row count per TSV |
| 1 | Filter pass rate | Fraction of rows matching filter_column/filter_value |
| 1 | Duplication rate per ontology | Fraction of duplicate primary identifiers |
| 2 | Null/empty field rate per property | Missing values per column |
| 2 | Identifier format validity rate | Regex check on ID columns (Ensembl, DrugBank, HPO, etc.) |
| 2 | Property value constraint violations | Non-numeric values in numeric columns |
| 2 | Source schema conformance | All configured columns present and non-empty |
| 3 | Extraction timestamp per source | File mtime from data/processed/ |

### Usage

```bash
# Print JSON to stdout
python eval/eval_after_parser.py

# Write JSON report to file
python eval/eval_after_parser.py --output eval/reports/parser_report.json
```

### Interpreting Results

- **Tier 1 "Fail" on Source database extraction** with `skip=True` note → expected;
  that source is disabled in the build.
- **Tier 1 "Fail" on Source database extraction** without `skip=True` → parser did
  not run or failed; investigate.
- **Identifier validity rate = 0.0** → check whether the column uses a different ID
  format than the configured regex (e.g., ClinPGx variants use rsIDs, not integers).
- **High null rate** on optional fields (xrefMeSH, xrefOMIM) → normal; these are
  sparsely populated cross-references.

---

## 2. `eval_after_memgraph.py`

Connects to a live Memgraph instance and computes graph-level quality metrics.

### Metrics

| Tier | Metric | Description |
|------|--------|-------------|
| 1 | Total node count per label | Count per node type; zero = blocking failure |
| 1 | Total edge count per type | Count per relationship type; zero = blocking failure |
| 1 | Relationship resolution rate | Fraction of TSV rows where both endpoints exist in graph |
| 2 | Orphan node rate | Fraction of nodes with zero edges per label |
| 2 | Duplicate edge rate | Fraction of duplicate (subject, rel_type, object) triples |
| 2 | Largest connected component fraction | Requires Memgraph MAGE |
| 2 | Average node degree per label | Mean edge count per node type |
| 2 | Run-to-run entity count delta | Requires `--baseline` flag |
| 3 | High-degree outlier count | Nodes exceeding 99th-percentile degree per rel type |

### Usage

```bash
# Basic run (stdout)
python eval/eval_after_memgraph.py

# Write report to file
python eval/eval_after_memgraph.py --output eval/reports/memgraph_report.json

# With baseline for run-to-run delta (Tier 2)
python eval/eval_after_memgraph.py \
    --baseline eval/reports/prev_memgraph_report.json \
    --output eval/reports/memgraph_report.json
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMGRAPH_URI` | `bolt://localhost:7687` | Memgraph bolt endpoint |
| `MEMGRAPH_USERNAME` | `` | Username (empty = no auth) |
| `MEMGRAPH_PASSWORD` | `` | Password (empty = no auth) |

### Interpreting Results

- **Resolution rate < 0.5** → silent join failure; check that subject/object node
  types were loaded before relationships, and that match property names are correct.
- **Resolution rate = 0.0** → complete join failure; the subject or object node type
  has no matching nodes.
- **Largest connected component = null** → Memgraph MAGE not installed; install from
  https://github.com/memgraph/mage to enable this metric.
- **Duplicate edge rate > 0** → deduplication failure in the loader; investigate
  the `source` property and MERGE logic in `src/memgraph_loader.py`.

---

## Output JSON Schema

Both scripts produce a JSON object matching the `eval_metrics.md` schema:

```json
{
  "run_timestamp": "2026-05-06T20:44:00+00:00",
  "metrics": [
    {
      "name": "Source database extraction",
      "data_type": "binary",
      "tier": 1,
      "result": "Pass",
      "source": "drugbank",
      "mapping": "drugbank.drugs",
      "note": "Expected: data/processed/drugbank/drugs.tsv"
    }
  ]
}
```

`eval_after_memgraph.py` additionally includes:

```json
{
  "entity_counts": {
    "Gene": 194559,
    "Drug": 24429,
    ...
  }
}
```

This `entity_counts` object is consumed by the `--baseline` flag of a subsequent run
to compute the Tier 2 run-to-run entity count delta.

---

## Dependencies

Both scripts require only packages already in CardioKB's `requirements.txt`:

- `pandas` — TSV loading
- `neo4j` — Memgraph bolt driver (memgraph script only)

No dependency on `config/project.yaml`, `config/databases.yaml`, or
`config/ontology_mappings.yaml` — CardioKB uses `src/ontology_configs.py` directly.
