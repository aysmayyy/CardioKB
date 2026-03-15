---
name: database-parsing
description: Guide for parsing a new biomedical database and integrating it into CardioKB. Covers identifying data sources, writing parsers extending BaseParser, creating ontology configs, pipeline integration, and testing. Use when adding a new data source, building a new parser, or integrating external biomedical data into the knowledge graph.
---

# How to Parse a New Biomedical Database for CardioKB

## Step 1: Determine Access Type

- **File-based** (FTP/HTTP download, XML, SQL dump): Download the full file and parse ALL rows. No disease filtering — load everything.
- **API-based** (REST API with query parameters): Read terms from `ontology/disease_filter.txt` via `src/utils.py` and use them to scope queries. Deduplicate results across query terms.

## Step 2: Write the Parser

Create `src/parsers/<name>_parser.py` (or `src/parsers/hetionet_components/` for Hetionet-derived sources). Extend `BaseParser` and implement exactly three methods:

- **`download_data()`** — Download raw data. Use `self.download_file(url, filename)` and `self.extract_gzip(path)` from BaseParser. Never rewrite download/read logic. For API parsers, cache JSON responses to `self.source_dir` so `--skip-download` works.
- **`parse_data()`** — Parse downloaded files into a `Dict[str, pd.DataFrame]`. Use `self.read_tsv()` / `self.read_csv()` from BaseParser for file I/O. Each DataFrame becomes one TSV in `data/processed/`. For API parsers, load from cached files if `download_data()` was skipped.
- **`get_schema()`** — Return a `Dict[str, Dict[str, str]]` describing columns for each output DataFrame.

## Step 3: Add Ontology Configs

Add entries in `src/ontology_configs.py` for every DataFrame your parser produces. Node configs need `data_type`, `node_type`, `source_filename`, `parse_config` (with `iri_column_name` and `data_property_map`), and `merge: True` if the node type already exists. Relationship configs additionally require:
- `relationship_type`, `source_label` (sets `r.source` — mandatory), and `parse_config` with `subject_node_type`, `subject_column_name`, `subject_match_property`, `object_node_type`, `object_column_name`, `object_match_property`.

**ID matching is validated automatically.** After Neo4j loads, the pipeline runs `_validate_and_fix_mappings()` which checks every relationship config's subject and object ID columns against existing Neo4j nodes. You just need to specify the correct `subject_match_property` / `object_match_property` in your ontology config — the pipeline handles the rest:

- Match rate >= 95%: logged as `[OK]`
- Match rate 70-95%: logged as `[WARN]` — review if IDs need remapping
- Match rate < 70%: logged as `[LOW]` — the pipeline automatically calls `suggest_mapping()` to find better ID properties, then `create_missing_nodes()` for unmatched IDs with >= 10 edges, and re-loads those relationships

To pre-check ID match rates before running the full pipeline:
```bash
# Validate a specific column against Neo4j
python src/id_mapping.py --validate data/processed/<source>/<file>.tsv \
  --id-col <column> --node <NodeLabel> --prop <nodeProperty>

# Find best ID property for a column
python src/id_mapping.py --suggest data/processed/<source>/<file>.tsv \
  --id-col <column> --node <NodeLabel>

# Preview what nodes would be created for unmatched IDs
python src/id_mapping.py --create-missing data/processed/<source>/<file>.tsv \
  --id-col <column> --node <NodeLabel> --id-prop <property> --min-edges 10 --dry-run
```

## Step 4: Register in main.py

Import and instantiate the parser in `_get_parsers()` in `src/main.py`. For credential-gated sources, read env vars and skip with a warning if missing.

## Step 5: Verify TSV Output

Run `python src/main.py --skip-neo4j` and check `data/processed/<source>/`. Confirm row counts are reasonable and column names match the ontology config expectations.

## Step 6: Load into Neo4j and Verify

Run the full pipeline (`python src/main.py`) and verify with Cypher:
```cypher
MATCH ()-[r]->() WHERE r.source = 'SourceName' RETURN type(r), count(r);
```
Check the ID Mapping Validation report in the pipeline logs — any `[LOW]` entries need attention. Then update `CLAUDE.md` and `README.md` with the new source and updated graph stats.
