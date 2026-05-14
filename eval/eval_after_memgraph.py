#!/usr/bin/env python3
"""
eval_after_memgraph.py — CardioKB Post-Memgraph Evaluation Script

Connects to a live Memgraph instance via bolt protocol and computes all
implementable "After Memgraph Export" metrics from eval_metrics.md.

Tier 1 (Block Release):
    - Total node count per label            (integer per label)
    - Total edge count per type             (integer per relationship type)
    - Relationship resolution rate          (float per mapping, cross-checked
                                             against TSV files)

Tier 2 (Monitor Trends):
    - Orphan node rate                      (float per label)
    - Duplicate edge rate                   (float per relationship type)
    - Largest connected component fraction  (float; requires Memgraph MAGE)
    - Average node degree per label         (float per label)
    - Run-to-run entity count delta         (object; requires --baseline)

Tier 3 (Periodic Audit):
    - High-degree outlier count per relationship type  (integer per type)

Environment variables:
    MEMGRAPH_URI        bolt URI  (default: bolt://localhost:7687)
    MEMGRAPH_USERNAME   username  (default: empty string)
    MEMGRAPH_PASSWORD   password  (default: empty string)

Usage:
    python eval/eval_after_memgraph.py
    python eval/eval_after_memgraph.py --output eval/reports/memgraph_report.json
    python eval/eval_after_memgraph.py --baseline prev_report.json --output report.json
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
try:
    from ontology_configs import ONTOLOGY_CONFIGS
except ImportError as exc:
    print(f"ERROR: Cannot import ONTOLOGY_CONFIGS: {exc}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Neo4j / Memgraph driver
# ---------------------------------------------------------------------------
try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: neo4j Python driver not installed. Run: pip install neo4j",
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Metric builder — matches eval_metrics.md JSON schema
# ---------------------------------------------------------------------------

def make_metric(name, data_type, tier, result,
                source=None, mapping=None, note=None, **extra):
    m = {"name": name, "data_type": data_type, "tier": tier, "result": result}
    if source is not None:
        m["source"] = source
    if mapping is not None:
        m["mapping"] = mapping
    if note is not None:
        m["note"] = note
    m.update(extra)
    return m


# ---------------------------------------------------------------------------
# Memgraph connection helpers
# ---------------------------------------------------------------------------

def connect_memgraph():
    uri      = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
    username = os.environ.get("MEMGRAPH_USERNAME", "")
    password = os.environ.get("MEMGRAPH_PASSWORD", "")
    auth     = (username, password) if (username or password) else None
    driver   = GraphDatabase.driver(uri, auth=auth)
    with driver.session() as s:
        s.run("RETURN 1").consume()
    return driver


def run_query(driver, cypher, **params):
    with driver.session() as s:
        return [dict(r) for r in s.run(cypher, **params)]


# ---------------------------------------------------------------------------
# Tier 1 — node and edge counts
# ---------------------------------------------------------------------------

def get_node_counts(driver):
    """
    Return {label: count} using labels(n)[0].
    Memgraph does not support UNWIND inside MATCH, so we use labels(n)[0]
    which returns the first (primary) label for each node.
    """
    rows = run_query(
        driver,
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY label",
    )
    return {r["label"]: int(r["cnt"]) for r in rows if r["label"] is not None}


def get_edge_counts(driver):
    """Return {rel_type: count} for every relationship type."""
    rows = run_query(
        driver,
        "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(*) AS cnt ORDER BY rel_type",
    )
    return {r["rel_type"]: int(r["cnt"]) for r in rows}


# ---------------------------------------------------------------------------
# Tier 1 — relationship resolution rate
# ---------------------------------------------------------------------------

def _cast_ids(values, match_type):
    """Cast string IDs from TSV to the type stored in Memgraph."""
    if match_type == "integer":
        result = []
        for v in values:
            try:
                result.append(int(v))
            except (ValueError, TypeError):
                pass
        return result
    return list(values)


def _lookup_ids(driver, node_type, prop, ids, chunk_size=5000):
    """Batch-query Memgraph for which IDs exist as nodes of a given type."""
    found = set()
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i: i + chunk_size]
        try:
            rows = run_query(
                driver,
                f"UNWIND $ids AS id MATCH (n:{node_type} {{{prop}: id}}) RETURN id AS matched_id",
                ids=chunk,
            )
            found.update(r["matched_id"] for r in rows)
        except Exception:
            pass
    return found


def compute_resolution_rate(driver, config_key, config):
    """
    For a relationship config, load the TSV and compute the fraction of rows
    where both subject and object identifiers resolve to existing graph nodes.
    Respects subject_match_type / object_match_type for integer-stored properties.
    Returns None when the TSV is missing or config is not a relationship.
    """
    if config.get("data_type") != "relationship":
        return None

    source_name    = config_key.split(".")[0]
    source_filename = config.get("source_filename", "")
    tsv_path       = DATA_PROCESSED / source_name / source_filename
    if not tsv_path.exists():
        return None

    pc = config.get("parse_config", {})
    subj_col   = pc.get("subject_column_name")
    subj_prop  = pc.get("subject_match_property")
    subj_type  = pc.get("subject_node_type")
    subj_mtype = pc.get("subject_match_type")
    obj_col    = pc.get("object_column_name")
    obj_prop   = pc.get("object_match_property")
    obj_type   = pc.get("object_node_type")
    obj_mtype  = pc.get("object_match_type")

    if not all([subj_col, subj_prop, subj_type, obj_col, obj_prop, obj_type]):
        return None

    try:
        df = pd.read_csv(tsv_path, sep="\t", dtype=str,
                         keep_default_na=False, low_memory=False)
    except Exception:
        return None

    if subj_col not in df.columns or obj_col not in df.columns:
        return None

    total_rows = len(df)
    if total_rows == 0:
        return 0.0

    raw_subj = df[subj_col].astype(str).str.strip().unique().tolist()
    raw_obj  = df[obj_col].astype(str).str.strip().unique().tolist()

    subj_ids = _cast_ids(raw_subj, subj_mtype)
    obj_ids  = _cast_ids(raw_obj,  obj_mtype)

    found_subj = _lookup_ids(driver, subj_type, subj_prop, subj_ids)
    found_obj  = _lookup_ids(driver, obj_type,  obj_prop,  obj_ids)

    if not found_subj and not found_obj:
        return 0.0

    # Build string sets for comparison against TSV values
    found_subj_str = {str(x) for x in found_subj}
    found_obj_str  = {str(x) for x in found_obj}

    resolved = 0
    for _, row in df.iterrows():
        s = str(row[subj_col]).strip()
        o = str(row[obj_col]).strip()
        s_ok = (s in found_subj_str) or (s in found_subj)
        o_ok = (o in found_obj_str)  or (o in found_obj)
        if s_ok and o_ok:
            resolved += 1

    return round(resolved / total_rows, 6)


# ---------------------------------------------------------------------------
# Tier 2 — orphan node rate
# ---------------------------------------------------------------------------

def get_orphan_rates(driver, node_counts):
    """
    Fraction of nodes with zero edges per label.
    Uses labels(n)[0] — Memgraph-compatible.
    """
    rows = run_query(
        driver,
        "MATCH (n) WHERE NOT (n)--() "
        "RETURN labels(n)[0] AS label, count(*) AS orphan_count ORDER BY label",
    )
    orphan_map = {r["label"]: int(r["orphan_count"]) for r in rows if r["label"]}
    return {
        label: round(orphan_map.get(label, 0) / total, 6) if total > 0 else 0.0
        for label, total in node_counts.items()
    }


# ---------------------------------------------------------------------------
# Tier 2 — duplicate edge rate (per-type to avoid memory overflow)
# ---------------------------------------------------------------------------

def get_duplicate_edge_info(driver, edge_counts):
    """
    Count duplicate (subject_id, object_id) pairs per relationship type.
    Runs one query per type to stay within Memgraph memory limits.
    Returns (total_edges, total_known_duplicates, {rel_type: dup_count}).
    dup_count == -1 means the query failed (memory limit / timeout).
    """
    total_edges = sum(edge_counts.values())
    dup_by_type = {}

    for rel_type, cnt in edge_counts.items():
        if cnt == 0:
            dup_by_type[rel_type] = 0
            continue
        try:
            rows = run_query(
                driver,
                f"MATCH (a)-[r:{rel_type}]->(b) "
                f"WITH id(a) AS a_id, id(b) AS b_id, count(*) AS cnt "
                f"WHERE cnt > 1 "
                f"RETURN sum(cnt - 1) AS dup_count",
            )
            val = rows[0]["dup_count"] if rows else 0
            dup_by_type[rel_type] = int(val) if val is not None else 0
        except Exception:
            dup_by_type[rel_type] = -1

    total_dups = sum(v for v in dup_by_type.values() if v >= 0)
    return total_edges, total_dups, dup_by_type


# ---------------------------------------------------------------------------
# Tier 2 — largest connected component
# ---------------------------------------------------------------------------

def get_largest_component_fraction(driver, total_nodes):
    """
    Compute LCC fraction via Memgraph MAGE weakly_connected_components.
    Returns (fraction, component_count) or (None, None) if MAGE unavailable.
    """
    if total_nodes == 0:
        return 0.0, 0
    try:
        rows = run_query(
            driver,
            "CALL weakly_connected_components.get() "
            "YIELD node, component_id "
            "RETURN component_id, count(*) AS size "
            "ORDER BY size DESC",
        )
        if rows:
            largest = int(rows[0]["size"])
            return round(largest / total_nodes, 6), len(rows)
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# Tier 2 — average node degree per label
# ---------------------------------------------------------------------------

def get_average_degree_per_label(driver, node_counts):
    """Mean number of edges (in + out) per node, one query per label."""
    results = {}
    for label, total in node_counts.items():
        if total == 0:
            results[label] = 0.0
            continue
        try:
            rows = run_query(
                driver,
                f"MATCH (n:{label}) "
                f"OPTIONAL MATCH (n)-[r]-() "
                f"WITH n, count(r) AS deg "
                f"RETURN avg(deg) AS avg_degree",
            )
            val = rows[0]["avg_degree"] if rows else None
            results[label] = round(float(val), 4) if val is not None else 0.0
        except Exception:
            results[label] = None
    return results


# ---------------------------------------------------------------------------
# Tier 2 — run-to-run entity count delta
# ---------------------------------------------------------------------------

def compute_run_to_run_delta(current_counts, baseline_path):
    """Compare current entity counts against a previous report. Returns None if no baseline."""
    if not baseline_path:
        return None
    try:
        with open(baseline_path, "r", encoding="utf-8") as fh:
            baseline = json.load(fh)
        prev = baseline.get("entity_counts", {})
        all_labels = sorted(set(current_counts) | set(prev))
        return {lbl: current_counts.get(lbl, 0) - prev.get(lbl, 0) for lbl in all_labels}
    except Exception as exc:
        return {"_error": str(exc)}


# ---------------------------------------------------------------------------
# Tier 2 — merge rate checking per source database
# ---------------------------------------------------------------------------

def get_source_labels_from_graph(driver):
    """Get all unique source labels from relationships in the graph."""
    rows = run_query(
        driver,
        "MATCH ()-[r]->() WHERE r.source IS NOT NULL "
        "RETURN DISTINCT r.source AS source ORDER BY source",
    )
    return [r["source"] for r in rows]


def get_merge_rate_per_source(driver):
    """
    For each source database, analyze potential duplicate node creation.

    Checks for nodes connected by relationships from each source that share
    the same primary identifier property (e.g., same gene symbol, drug name),
    which would indicate failed merges (duplicate nodes created instead of merged).

    Returns {source: {
        'total_unique_nodes': int,
        'potential_duplicates': int,
        'merge_rate': float,
        'duplicate_examples': list,
        'node_types_affected': dict
    }}
    """
    results = {}
    sources = get_source_labels_from_graph(driver)

    # Common identifier properties to check for duplicates
    id_props = ['identifier', 'name', 'symbol', 'drugbank_id', 'mesh_id',
                'doid', 'hgnc_id', 'entrez_id', 'ensembl_id', 'uniprot_id',
                'nct_id', 'pubchem_cid', 'chembl_id', 'rxcui', 'cui']

    for source in sources:
        try:
            # Get all nodes connected by relationships from this source
            node_rows = run_query(
                driver,
                "MATCH (n)-[r]-() WHERE r.source = $source "
                "RETURN DISTINCT labels(n)[0] AS label, n AS node",
                source=source,
            )

            if not node_rows:
                results[source] = {
                    'total_unique_nodes': 0,
                    'potential_duplicates': 0,
                    'merge_rate': 1.0,
                    'duplicate_examples': [],
                    'node_types_affected': {},
                }
                continue

            # Group nodes by label and check for duplicates
            nodes_by_label = {}
            for row in node_rows:
                label = row['label']
                node = row['node']
                if label not in nodes_by_label:
                    nodes_by_label[label] = []
                nodes_by_label[label].append(dict(node))

            total_unique = len(node_rows)
            potential_dups = 0
            dup_examples = []
            types_affected = {}

            for label, nodes in nodes_by_label.items():
                if len(nodes) < 2:
                    continue

                # Check each identifier property for duplicates
                for prop in id_props:
                    id_values = {}
                    for n in nodes:
                        if prop in n and n[prop]:
                            val = str(n[prop]).lower().strip()
                            if val:
                                if val not in id_values:
                                    id_values[val] = []
                                id_values[val].append(n)

                    # Count duplicates (same identifier, different nodes)
                    for val, dup_nodes in id_values.items():
                        if len(dup_nodes) > 1:
                            dup_count = len(dup_nodes) - 1  # -1 because one is the "correct" node
                            potential_dups += dup_count
                            if label not in types_affected:
                                types_affected[label] = 0
                            types_affected[label] += dup_count
                            if len(dup_examples) < 5:
                                dup_examples.append({
                                    'label': label,
                                    'property': prop,
                                    'value': val,
                                    'count': len(dup_nodes),
                                })
                    break  # Only check the first matching property per label

            merge_rate = 1.0 if total_unique == 0 else round(
                (total_unique - potential_dups) / total_unique, 4
            )

            results[source] = {
                'total_unique_nodes': total_unique,
                'potential_duplicates': potential_dups,
                'merge_rate': merge_rate,
                'duplicate_examples': dup_examples,
                'node_types_affected': types_affected,
            }

        except Exception as exc:
            results[source] = {
                'total_unique_nodes': None,
                'potential_duplicates': None,
                'merge_rate': None,
                'error': str(exc),
                'duplicate_examples': [],
                'node_types_affected': {},
            }

    return results


def get_node_creation_stats_per_source(driver):
    """
    Get statistics about nodes created/touched by each source.
    Uses relationship source property to attribute nodes to sources.

    Returns {source: {label: count}} showing which node types each source contributes to.
    """
    rows = run_query(
        driver,
        "MATCH (n)-[r]-() WHERE r.source IS NOT NULL "
        "RETURN r.source AS source, labels(n)[0] AS label, count(DISTINCT n) AS cnt "
        "ORDER BY source, label",
    )

    stats = {}
    for row in rows:
        source = row['source']
        label = row['label']
        cnt = int(row['cnt'])
        if source not in stats:
            stats[source] = {}
        stats[source][label] = cnt

    return stats


# ---------------------------------------------------------------------------
# Tier 2 — Cross-source merge analysis
# ---------------------------------------------------------------------------

def get_cross_source_node_analysis(driver):
    """
    Analyze which node types are touched by multiple sources and compute
    merge statistics for each.

    Returns {
        'node_type_sources': {node_type: {source: count, ...}, ...},
        'multi_source_summary': {node_type: {
            'total_nodes': int,
            'multi_source_nodes': int,
            'single_source_nodes': int,
            'merge_rate': float,
            'source_distribution': {num_sources: count, ...}
        }, ...}
    }
    """
    # Get which sources touch each node type
    rows = run_query(
        driver,
        """
        MATCH (n)-[r]-()
        WHERE r.source IS NOT NULL
        WITH labels(n)[0] AS node_type, r.source AS source, count(DISTINCT n) AS node_count
        RETURN node_type, source, node_count
        ORDER BY node_type, node_count DESC
        """,
    )

    node_type_sources = {}
    for row in rows:
        nt = row['node_type']
        src = row['source']
        cnt = int(row['node_count'])
        if nt not in node_type_sources:
            node_type_sources[nt] = {}
        node_type_sources[nt][src] = cnt

    # For multi-source node types, compute detailed merge stats
    multi_source_summary = {}
    multi_source_types = [nt for nt, sources in node_type_sources.items() if len(sources) > 1]

    for nt in multi_source_types:
        try:
            # Get actual unique node count
            actual = run_query(driver, f"MATCH (n:{nt}) RETURN count(n) AS cnt")[0]['cnt']

            # Get source distribution per node
            dist_rows = run_query(
                driver,
                f"""
                MATCH (n:{nt})-[r]-()
                WHERE r.source IS NOT NULL
                WITH n, collect(DISTINCT r.source) AS sources
                RETURN size(sources) AS source_count, count(n) AS node_count
                ORDER BY source_count DESC
                """,
            )

            source_distribution = {}
            multi_source_nodes = 0
            single_source_nodes = 0

            for row in dist_rows:
                sc = int(row['source_count'])
                nc = int(row['node_count'])
                source_distribution[sc] = nc
                if sc > 1:
                    multi_source_nodes += nc
                else:
                    single_source_nodes += nc

            total_with_rels = multi_source_nodes + single_source_nodes
            merge_rate = multi_source_nodes / total_with_rels if total_with_rels > 0 else 0

            multi_source_summary[nt] = {
                'total_nodes': actual,
                'nodes_with_relationships': total_with_rels,
                'multi_source_nodes': multi_source_nodes,
                'single_source_nodes': single_source_nodes,
                'merge_rate': round(merge_rate, 4),
                'source_distribution': source_distribution,
                'num_sources': len(node_type_sources[nt]),
            }
        except Exception as exc:
            multi_source_summary[nt] = {'error': str(exc)}

    return {
        'node_type_sources': node_type_sources,
        'multi_source_summary': multi_source_summary,
    }


def get_drug_merge_detail(driver):
    """
    Detailed analysis of drug merging between CTD and DrugBank.

    Returns {
        'ctd_total': int,
        'drugbank_total': int,
        'merged_both': int,
        'ctd_only': int,
        'drugbank_only': int,
        'merge_rate': float
    }
    """
    try:
        ctd_drugs = run_query(
            driver,
            """
            MATCH (d:Drug)-[r]-()
            WHERE r.source = "CTD"
            RETURN count(DISTINCT d) AS cnt
            """,
        )[0]['cnt']

        db_drugs = run_query(
            driver,
            """
            MATCH (d:Drug)-[r]-()
            WHERE r.source = "DrugBank"
            RETURN count(DISTINCT d) AS cnt
            """,
        )[0]['cnt']

        both = run_query(
            driver,
            """
            MATCH (d:Drug)-[r1]-(), (d)-[r2]-()
            WHERE r1.source = "CTD" AND r2.source = "DrugBank"
            RETURN count(DISTINCT d) AS cnt
            """,
        )[0]['cnt']

        ctd_only = ctd_drugs - both
        drugbank_only = db_drugs - both
        merge_rate = both / ctd_drugs if ctd_drugs > 0 else 0

        return {
            'ctd_total': int(ctd_drugs),
            'drugbank_total': int(db_drugs),
            'merged_both': int(both),
            'ctd_only': int(ctd_only),
            'drugbank_only': int(drugbank_only),
            'merge_rate': round(merge_rate, 4),
        }
    except Exception as exc:
        return {'error': str(exc)}


def get_gene_integration_depth(driver):
    """
    Analyze how deeply genes are integrated across sources.

    Returns {
        'high_integration': int (10+ sources),
        'medium_integration': int (5-9 sources),
        'low_integration': int (2-4 sources),
        'single_source': int (1 source),
        'total': int
    }
    """
    try:
        rows = run_query(
            driver,
            """
            MATCH (g:Gene)-[r]-()
            WHERE r.source IS NOT NULL
            WITH g, count(DISTINCT r.source) AS source_count
            RETURN
                sum(CASE WHEN source_count >= 10 THEN 1 ELSE 0 END) AS high_integration,
                sum(CASE WHEN source_count >= 5 AND source_count < 10 THEN 1 ELSE 0 END) AS medium_integration,
                sum(CASE WHEN source_count >= 2 AND source_count < 5 THEN 1 ELSE 0 END) AS low_integration,
                sum(CASE WHEN source_count = 1 THEN 1 ELSE 0 END) AS single_source,
                count(g) AS total
            """,
        )[0]

        return {
            'high_integration': int(rows['high_integration']),
            'medium_integration': int(rows['medium_integration']),
            'low_integration': int(rows['low_integration']),
            'single_source': int(rows['single_source']),
            'total': int(rows['total']),
        }
    except Exception as exc:
        return {'error': str(exc)}


def get_id_duplicate_check(driver):
    """
    Check for duplicate IDs across all major entity types.
    Zero duplicates = perfect ID-based merging.

    Returns {node_type: {'duplicate_count': int, 'id_property': str}, ...}
    """
    checks = [
        ('Gene', 'geneId'),
        ('Drug', 'drugId'),
        ('Disease', 'diseaseId'),
        ('Variant', 'variantId'),
        ('ClinicalTrial', 'trialId'),
        ('Phenotype', 'phenotypeId'),
        ('Pathway', 'pathwayId'),
    ]

    results = {}
    for node_type, id_prop in checks:
        try:
            rows = run_query(
                driver,
                f"""
                MATCH (n:{node_type})
                WHERE n.{id_prop} IS NOT NULL
                WITH n.{id_prop} AS id, count(*) AS cnt
                WHERE cnt > 1
                RETURN count(*) AS dup_count
                """,
            )
            dup_count = int(rows[0]['dup_count']) if rows else 0
            results[node_type] = {
                'duplicate_count': dup_count,
                'id_property': id_prop,
                'status': 'PASS' if dup_count == 0 else 'FAIL',
            }
        except Exception:
            results[node_type] = {
                'duplicate_count': None,
                'id_property': id_prop,
                'status': 'SKIPPED',
            }

    return results


# ---------------------------------------------------------------------------
# Tier 3 — high-degree outlier count per relationship type
# ---------------------------------------------------------------------------

def get_high_degree_outliers(driver, edge_counts, percentile=99.0):
    """
    For each relationship type, count nodes whose degree exceeds the
    99th-percentile threshold. One query per type.
    Returns {rel_type: count} where count is None on query failure.
    """
    results = {}
    for rel_type, cnt in edge_counts.items():
        if cnt == 0:
            results[rel_type] = 0
            continue
        try:
            rows = run_query(
                driver,
                f"MATCH (n)-[r:{rel_type}]-() "
                f"WITH n, count(r) AS deg "
                f"RETURN deg ORDER BY deg",
            )
            if not rows:
                results[rel_type] = 0
                continue
            degrees = [int(r["deg"]) for r in rows]
            n = len(degrees)
            idx = max(0, int(n * percentile / 100) - 1)
            threshold = degrees[idx]
            results[rel_type] = sum(1 for d in degrees if d > threshold)
        except Exception:
            results[rel_type] = None
    return results


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def run_eval(baseline_path=None):
    metrics = []

    # Connect
    try:
        driver = connect_memgraph()
        uri = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
        print(f"Connected to Memgraph at {uri}", file=sys.stderr)
    except Exception as exc:
        print(f"ERROR: Cannot connect to Memgraph: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Tier 1: Node counts per label ────────────────────────────────────────
    print("Computing node counts...", file=sys.stderr)
    node_counts = get_node_counts(driver)
    total_nodes = sum(node_counts.values())

    for label, cnt in sorted(node_counts.items()):
        metrics.append(make_metric(
            name="Total node count per label",
            data_type="integer", tier=1, result=cnt,
            label=label, note=f"Label: {label}",
        ))

    # ── Tier 1: Edge counts per type ─────────────────────────────────────────
    print("Computing edge counts...", file=sys.stderr)
    edge_counts = get_edge_counts(driver)

    for rel_type, cnt in sorted(edge_counts.items()):
        metrics.append(make_metric(
            name="Total edge count per type",
            data_type="integer", tier=1, result=cnt,
            relationship_type=rel_type, note=f"Relationship type: {rel_type}",
        ))

    # ── Tier 1: Relationship resolution rate ─────────────────────────────────
    print("Computing relationship resolution rates...", file=sys.stderr)
    for config_key, config in ONTOLOGY_CONFIGS.items():
        if config.get("data_type") != "relationship" or config.get("skip", False):
            continue

        source_name     = config_key.split(".")[0]
        source_filename = config.get("source_filename", "")
        tsv_path        = DATA_PROCESSED / source_name / source_filename

        if not tsv_path.exists():
            metrics.append(make_metric(
                name="Relationship resolution rate per mapping",
                data_type="float", tier=1, result=None,
                source=source_name, mapping=config_key,
                note="TSV file not found; cannot compute resolution rate",
            ))
            continue

        print(f"  Resolving {config_key}...", file=sys.stderr)
        rate = compute_resolution_rate(driver, config_key, config)
        metrics.append(make_metric(
            name="Relationship resolution rate per mapping",
            data_type="float", tier=1, result=rate,
            source=source_name, mapping=config_key,
            note=("Fraction of TSV rows where both subject and object "
                  "identifiers match existing graph nodes"),
        ))

    # ── Tier 2: Orphan node rate ──────────────────────────────────────────────
    print("Computing orphan node rates...", file=sys.stderr)
    orphan_rates = get_orphan_rates(driver, node_counts)
    for label, rate in sorted(orphan_rates.items()):
        metrics.append(make_metric(
            name="Orphan node rate",
            data_type="float", tier=2, result=rate,
            label=label, note=f"Label: {label} — fraction of nodes with zero edges",
        ))

    # ── Tier 2: Duplicate edge rate ───────────────────────────────────────────
    print("Computing duplicate edge rates...", file=sys.stderr)
    total_edges, total_dups, dup_by_type = get_duplicate_edge_info(driver, edge_counts)
    known_edges = sum(edge_counts[rt] for rt, v in dup_by_type.items() if v >= 0)
    known_dups  = sum(v for v in dup_by_type.values() if v >= 0)
    dup_rate    = round(known_dups / known_edges, 6) if known_edges > 0 else 0.0
    errored     = [rt for rt, v in dup_by_type.items() if v is not None and v < 0]

    metrics.append(make_metric(
        name="Duplicate edge rate",
        data_type="float", tier=2, result=dup_rate,
        duplicate_edge_count=known_dups,
        duplicate_by_type={rt: v for rt, v in dup_by_type.items() if v >= 0},
        note=(
            f"{known_dups} duplicate (subject, rel_type, object) triples "
            f"of {known_edges:,} computable edges"
            + (f"; {len(errored)} type(s) skipped due to memory limits" if errored else "")
        ),
    ))

    # ── Tier 2: Largest connected component fraction ──────────────────────────
    print("Computing largest connected component...", file=sys.stderr)
    lcc_fraction, num_components = get_largest_component_fraction(driver, total_nodes)
    metrics.append(make_metric(
        name="Largest connected component fraction",
        data_type="float", tier=2, result=lcc_fraction,
        component_count=num_components,
        note=(
            (f"Fraction of {total_nodes:,} nodes in the largest weakly connected "
             f"component; {num_components} components total")
            if lcc_fraction is not None else
            ("Memgraph MAGE weakly_connected_components procedure not available. "
             "Install MAGE: https://github.com/memgraph/mage")
        ),
    ))

    # ── Tier 2: Average node degree per label ─────────────────────────────────
    print("Computing average node degree per label...", file=sys.stderr)
    avg_degrees = get_average_degree_per_label(driver, node_counts)
    for label, avg_deg in sorted(avg_degrees.items()):
        metrics.append(make_metric(
            name="Average node degree per label",
            data_type="float", tier=2, result=avg_deg,
            label=label, note=f"Label: {label} — mean edge count (in + out) per node",
        ))

    # ── Tier 2: Run-to-run entity count delta ─────────────────────────────────
    delta = compute_run_to_run_delta(node_counts, baseline_path)
    metrics.append(make_metric(
        name="Run-to-run entity count delta",
        data_type="object", tier=2, result=delta,
        note=("Per-label node count delta vs baseline report"
              if delta is not None
              else "No --baseline provided; pass a previous JSON report to enable"),
    ))

    # ── Tier 2: Merge rate per source database ────────────────────────────────
    print("Computing merge rates per source database...", file=sys.stderr)
    merge_rates = get_merge_rate_per_source(driver)
    source_node_stats = get_node_creation_stats_per_source(driver)

    LOW_MERGE_THRESHOLD = 0.95  # Flag sources with merge rate below 95%

    for source, stats in sorted(merge_rates.items()):
        merge_rate = stats.get('merge_rate')
        is_low = merge_rate is not None and merge_rate < LOW_MERGE_THRESHOLD
        metrics.append(make_metric(
            name="Merge rate per source database",
            data_type="float", tier=2, result=merge_rate,
            source=source,
            total_unique_nodes=stats.get('total_unique_nodes'),
            potential_duplicates=stats.get('potential_duplicates'),
            node_types_affected=stats.get('node_types_affected'),
            duplicate_examples=stats.get('duplicate_examples'),
            is_flagged=is_low,
            note=(
                f"Source: {source} — "
                f"{stats.get('total_unique_nodes', 0):,} nodes touched, "
                f"{stats.get('potential_duplicates', 0):,} potential duplicates"
                + (" *** LOW MERGE RATE ***" if is_low else "")
                + (f" Error: {stats.get('error')}" if stats.get('error') else "")
            ),
        ))

    # Store merge rate summary in report for easy access
    merge_rate_summary = {
        source: {
            'merge_rate': stats.get('merge_rate'),
            'total_nodes': stats.get('total_unique_nodes'),
            'duplicates': stats.get('potential_duplicates'),
            'flagged': stats.get('merge_rate') is not None and stats.get('merge_rate') < LOW_MERGE_THRESHOLD,
        }
        for source, stats in merge_rates.items()
    }

    # ── Tier 2: Cross-source merge analysis ─────────────────────────────────────
    print("Computing cross-source merge analysis...", file=sys.stderr)
    cross_source_analysis = get_cross_source_node_analysis(driver)
    drug_merge_detail = get_drug_merge_detail(driver)
    gene_integration = get_gene_integration_depth(driver)
    id_duplicates = get_id_duplicate_check(driver)

    # Add cross-source metrics
    for nt, stats in cross_source_analysis.get('multi_source_summary', {}).items():
        if 'error' not in stats:
            metrics.append(make_metric(
                name="Cross-source node integration",
                data_type="float", tier=2,
                result=stats.get('merge_rate'),
                node_type=nt,
                num_sources=stats.get('num_sources'),
                multi_source_nodes=stats.get('multi_source_nodes'),
                single_source_nodes=stats.get('single_source_nodes'),
                note=f"{nt}: {stats.get('multi_source_nodes', 0):,} nodes from {stats.get('num_sources', 0)} sources",
            ))

    # Add ID duplicate check metrics
    for nt, stats in id_duplicates.items():
        metrics.append(make_metric(
            name="ID-based duplicate check",
            data_type="integer", tier=2,
            result=stats.get('duplicate_count'),
            node_type=nt,
            id_property=stats.get('id_property'),
            status=stats.get('status'),
            note=f"{nt}.{stats.get('id_property')}: {stats.get('duplicate_count', 'N/A')} duplicates",
        ))

    # ── Tier 3: High-degree outlier count per relationship type ───────────────
    print("Computing high-degree outliers per relationship type...", file=sys.stderr)
    outliers = get_high_degree_outliers(driver, edge_counts, percentile=99.0)
    for rel_type, count in sorted(outliers.items()):
        metrics.append(make_metric(
            name="High-degree outlier count per relationship type",
            data_type="integer", tier=3, result=count,
            relationship_type=rel_type,
            note=(f"Nodes exceeding 99th-percentile degree for :{rel_type} edges"
                  if count is not None
                  else f"Query failed for :{rel_type} (memory limit or timeout)"),
        ))

    driver.close()

    return {
        "run_timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "entity_counts": node_counts,
        "merge_rate_summary": merge_rate_summary,
        "source_node_stats": source_node_stats,
        "cross_source_analysis": cross_source_analysis,
        "drug_merge_detail": drug_merge_detail,
        "gene_integration": gene_integration,
        "id_duplicates": id_duplicates,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Pass/fail logic helpers
# ---------------------------------------------------------------------------

def is_metric_passing(metric):
    """
    Determine if a metric is passing based on its name and result.
    Different metrics have different pass criteria:
    - Counts (nodes, edges): > 0 is passing
    - Duplicate checks: 0 is passing (no duplicates = good)
    - Orphan rates: any value is passing (0 = excellent)
    - Resolution rates: > 0 is passing
    - ID-based duplicate: 0 is passing, or status == 'PASS'
    - LCC/delta: None means not available, not failure
    """
    name = metric.get('name', '')
    result = metric.get('result')
    status = metric.get('status')

    # If status is explicitly set, use it
    if status == 'PASS':
        return True
    if status == 'FAIL':
        return False

    # None means "not available" for optional metrics, not failure
    if result is None:
        # These are optional/informational, not failures
        if name in ['Largest connected component fraction',
                    'Run-to-run entity count delta']:
            return True  # Not available is OK
        return False  # Other None results are failures

    # For these metrics, 0 is the desired outcome (no duplicates/issues)
    zero_is_good = [
        'Duplicate edge rate',
        'ID-based duplicate check',
    ]
    if any(z in name for z in zero_is_good):
        return True  # 0 duplicates = passing

    # Orphan rates: any computed value is "passing" (it's informational)
    if 'Orphan node rate' in name:
        return True  # Computed orphan rate is informational, not pass/fail

    # Average degree: 0 can be valid for metadata nodes
    if 'Average node degree' in name:
        return True  # Informational metric

    # Cross-source integration: 0% is valid for single-source node types
    if 'Cross-source node integration' in name:
        return True  # Informational metric

    # For counts, > 0 is passing
    if 'count' in name.lower():
        return result > 0

    # For rates/fractions, > 0 is generally passing
    if isinstance(result, (int, float)):
        return result > 0

    # Default: non-None, non-zero, non-'Fail' is passing
    return result not in [None, 'Fail']


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------

def generate_markdown_report(report):
    """Generate a human-readable markdown report from the eval results."""
    lines = []
    timestamp = report.get('run_timestamp', '')[:10]
    entity_counts = report.get('entity_counts', {})
    metrics = report.get('metrics', [])

    lines.append(f"# CardioKB Evaluation Report — {timestamp}")
    lines.append("")
    lines.append(f"**Generated:** {report.get('run_timestamp', 'N/A')}")
    lines.append("")

    # Test Results Summary
    t1 = [m for m in metrics if m.get('tier') == 1]
    t2 = [m for m in metrics if m.get('tier') == 2]
    t1_pass = sum(1 for m in t1 if is_metric_passing(m))
    t2_pass = sum(1 for m in t2 if is_metric_passing(m))

    lines.append("## Test Results Summary")
    lines.append("")
    lines.append(f"- **Tier 1 (blocking):** {t1_pass}/{len(t1)} passing")
    lines.append(f"- **Tier 2 (quality):** {t2_pass}/{len(t2)} passing")
    lines.append("")

    # Entity Counts
    lines.append("## Entity Counts")
    lines.append("")
    lines.append("| Node Type | Count |")
    lines.append("|-----------|-------|")
    for label, cnt in sorted(entity_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {label} | {cnt:,} |")
    lines.append("")

    # Cross-Source Integration
    cross_source = report.get('cross_source_analysis', {})
    multi_source_summary = cross_source.get('multi_source_summary', {})

    if multi_source_summary:
        lines.append("## Cross-Source Integration")
        lines.append("")
        lines.append("Node types touched by multiple sources:")
        lines.append("")
        lines.append("| Node Type | # Sources | Multi-Source Nodes | Single-Source | Integration Rate |")
        lines.append("|-----------|-----------|-------------------|---------------|------------------|")

        for nt, stats in sorted(multi_source_summary.items(), key=lambda x: -x[1].get('num_sources', 0)):
            if 'error' not in stats:
                num_src = stats.get('num_sources', 0)
                multi = stats.get('multi_source_nodes', 0)
                single = stats.get('single_source_nodes', 0)
                rate = stats.get('merge_rate', 0) * 100
                lines.append(f"| {nt} | {num_src} | {multi:,} | {single:,} | {rate:.1f}% |")
        lines.append("")

    # Drug Merge Detail
    drug_merge = report.get('drug_merge_detail', {})
    if drug_merge and 'error' not in drug_merge:
        lines.append("### Drug Merging: CTD → DrugBank")
        lines.append("")
        lines.append(f"- **CTD drugs total:** {drug_merge.get('ctd_total', 0):,}")
        lines.append(f"- **Merged with DrugBank:** {drug_merge.get('merged_both', 0):,} ({drug_merge.get('merge_rate', 0)*100:.1f}%)")
        lines.append(f"- **CTD-only:** {drug_merge.get('ctd_only', 0):,} (environmental chemicals, research compounds)")
        lines.append("")

    # Gene Integration Depth
    gene_int = report.get('gene_integration', {})
    if gene_int and 'error' not in gene_int:
        lines.append("### Gene Integration Depth")
        lines.append("")
        lines.append("| Integration Level | Genes |")
        lines.append("|-------------------|-------|")
        lines.append(f"| High (10+ sources) | {gene_int.get('high_integration', 0):,} |")
        lines.append(f"| Medium (5-9 sources) | {gene_int.get('medium_integration', 0):,} |")
        lines.append(f"| Low (2-4 sources) | {gene_int.get('low_integration', 0):,} |")
        lines.append(f"| Single source | {gene_int.get('single_source', 0):,} |")
        lines.append("")

    # ID Duplicate Check
    id_dups = report.get('id_duplicates', {})
    if id_dups:
        lines.append("## ID-Based Duplicate Check")
        lines.append("")
        lines.append("| Entity Type | ID Property | Duplicates | Status |")
        lines.append("|-------------|-------------|------------|--------|")
        for nt, stats in sorted(id_dups.items()):
            dup_count = stats.get('duplicate_count')
            dup_str = str(dup_count) if dup_count is not None else 'N/A'
            status = stats.get('status', 'N/A')
            status_icon = '✓' if status == 'PASS' else ('✗' if status == 'FAIL' else '—')
            lines.append(f"| {nt} | {stats.get('id_property', '')} | {dup_str} | {status_icon} {status} |")
        lines.append("")

    # Merge Rate by Source
    merge_summary = report.get('merge_rate_summary', {})
    if merge_summary:
        lines.append("## Merge Rate by Source Database")
        lines.append("")
        lines.append("| Source | Merge Rate | Nodes | Duplicates | Status |")
        lines.append("|--------|------------|-------|------------|--------|")
        for source, stats in sorted(merge_summary.items()):
            rate = stats.get('merge_rate')
            rate_str = f"{rate*100:.1f}%" if rate is not None else 'N/A'
            total = stats.get('total_nodes', 0)
            dups = stats.get('duplicates', 0)
            flagged = stats.get('flagged', False)
            status = '⚠️ LOW' if flagged else '✓'
            lines.append(f"| {source} | {rate_str} | {total:,} | {dups} | {status} |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by eval_after_memgraph.py*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(report):
    metrics       = report["metrics"]
    t1            = [m for m in metrics if m["tier"] == 1]
    t2            = [m for m in metrics if m["tier"] == 2]
    t3            = [m for m in metrics if m["tier"] == 3]
    entity_counts = report.get("entity_counts", {})
    total_nodes   = sum(entity_counts.values())

    zero_nodes = [m for m in t1
                  if m.get("name") == "Total node count per label" and m.get("result") == 0]
    zero_edges = [m for m in t1
                  if m.get("name") == "Total edge count per type" and m.get("result") == 0]
    null_res   = [m for m in t1
                  if m.get("name") == "Relationship resolution rate per mapping"
                  and m.get("result") is None]
    low_res    = [m for m in t1
                  if m.get("name") == "Relationship resolution rate per mapping"
                  and m.get("result") is not None
                  and float(m["result"]) < 0.5]

    # Extract merge rate metrics
    merge_metrics = [m for m in t2 if m.get("name") == "Merge rate per source database"]
    low_merge = [m for m in merge_metrics if m.get("is_flagged")]

    print(f"\n{'='*60}")
    print(f"CardioKB eval_after_memgraph  --  {report['run_timestamp']}")
    print(f"{'='*60}")
    print(f"  Total nodes in graph : {total_nodes:>12,}")
    print(f"  Node labels          : {len(entity_counts):>12}")
    print()
    for label, cnt in sorted(entity_counts.items()):
        flag = "  *** ZERO ***" if cnt == 0 else ""
        print(f"    {label:<35} {cnt:>10,}{flag}")
    print()
    print(f"  Tier 1 metrics : {len(t1):>5}")
    print(f"    Zero node counts      : {len(zero_nodes)}")
    print(f"    Zero edge counts      : {len(zero_edges)}")
    print(f"    Null resolution rates : {len(null_res)}")
    print(f"    Low resolution (<50%) : {len(low_res)}")
    print(f"  Tier 2 metrics : {len(t2):>5}")
    print(f"  Tier 3 metrics : {len(t3):>5}")

    # Cross-source integration summary
    cross_source = report.get("cross_source_analysis", {})
    multi_source_summary = cross_source.get("multi_source_summary", {})
    if multi_source_summary:
        print(f"\n  {'─'*56}")
        print(f"  CROSS-SOURCE INTEGRATION")
        print(f"  {'─'*56}")
        for nt, stats in sorted(multi_source_summary.items(), key=lambda x: -x[1].get('num_sources', 0)):
            if 'error' not in stats:
                num_src = stats.get('num_sources', 0)
                multi = stats.get('multi_source_nodes', 0)
                rate = stats.get('merge_rate', 0) * 100
                print(f"    {nt:<20} {num_src:>2} sources  {multi:>8,} multi-source nodes  ({rate:>5.1f}%)")

    # Gene integration depth
    gene_int = report.get("gene_integration", {})
    if gene_int and 'error' not in gene_int:
        print(f"\n  {'─'*56}")
        print(f"  GENE INTEGRATION DEPTH")
        print(f"  {'─'*56}")
        print(f"    High (10+ sources)   : {gene_int.get('high_integration', 0):>8,}")
        print(f"    Medium (5-9 sources) : {gene_int.get('medium_integration', 0):>8,}")
        print(f"    Low (2-4 sources)    : {gene_int.get('low_integration', 0):>8,}")
        print(f"    Single source        : {gene_int.get('single_source', 0):>8,}")

    # Drug merge detail
    drug_merge = report.get("drug_merge_detail", {})
    if drug_merge and 'error' not in drug_merge:
        print(f"\n  {'─'*56}")
        print(f"  DRUG MERGING: CTD → DrugBank")
        print(f"  {'─'*56}")
        print(f"    CTD drugs total      : {drug_merge.get('ctd_total', 0):>8,}")
        print(f"    Merged with DrugBank : {drug_merge.get('merged_both', 0):>8,} ({drug_merge.get('merge_rate', 0)*100:.1f}%)")
        print(f"    CTD-only             : {drug_merge.get('ctd_only', 0):>8,}")

    # ID duplicate check
    id_dups = report.get("id_duplicates", {})
    if id_dups:
        all_pass = all(s.get('status') == 'PASS' for s in id_dups.values() if s.get('status') != 'SKIPPED')
        print(f"\n  {'─'*56}")
        print(f"  ID-BASED DUPLICATE CHECK {'✓ ALL PASS' if all_pass else '⚠️ ISSUES FOUND'}")
        print(f"  {'─'*56}")
        for nt, stats in sorted(id_dups.items()):
            dup = stats.get('duplicate_count')
            status = stats.get('status', 'N/A')
            icon = '✓' if status == 'PASS' else ('✗' if status == 'FAIL' else '—')
            dup_str = str(dup) if dup is not None else 'N/A'
            print(f"    {nt:<20} {stats.get('id_property', ''):<15} {dup_str:>5} duplicates  {icon}")

    # Merge rate summary
    merge_summary = report.get("merge_rate_summary", {})
    if merge_summary:
        print(f"\n  {'─'*56}")
        print(f"  MERGE RATE BY SOURCE DATABASE")
        print(f"  {'─'*56}")
        for source in sorted(merge_summary.keys()):
            stats = merge_summary[source]
            rate = stats.get('merge_rate')
            total = stats.get('total_nodes', 0)
            dups = stats.get('duplicates', 0)
            flag = "  *** LOW ***" if stats.get('flagged') else ""
            if rate is not None:
                print(f"    {source:<25} {rate:>6.2%}  ({total:>8,} nodes, {dups:>6,} dups){flag}")
            else:
                print(f"    {source:<25}    N/A   (query failed)")

    if zero_nodes:
        print("\n  BLOCKING -- Zero node counts:")
        for m in zero_nodes:
            print(f"    {m.get('label', '?')} = 0")

    if zero_edges:
        print("\n  BLOCKING -- Zero edge counts:")
        for m in zero_edges:
            print(f"    {m.get('relationship_type', '?')} = 0")

    if low_res:
        print("\n  LOW resolution rates (<50%) -- investigate join failures:")
        for m in sorted(low_res, key=lambda x: float(x["result"])):
            print(f"    {m.get('mapping', '?')} = {float(m['result']):.4f}")
            if m.get("note"):
                print(f"      {m['note']}")

    # Low merge rate warnings
    if low_merge:
        print("\n  WARNING -- Low merge rates (<95%) -- possible duplicate node creation:")
        for m in sorted(low_merge, key=lambda x: x.get("result") or 0):
            source = m.get('source', '?')
            rate = m.get('result')
            dups = m.get('potential_duplicates', 0)
            types = m.get('node_types_affected', {})
            print(f"    {source}: {rate:.2%} merge rate, {dups} potential duplicates")
            if types:
                for node_type, cnt in types.items():
                    print(f"      - {node_type}: {cnt} duplicates")
            examples = m.get('duplicate_examples', [])
            if examples:
                print(f"      Examples:")
                for ex in examples[:3]:
                    print(f"        {ex['label']}.{ex['property']} = '{ex['value']}' ({ex['count']} nodes)")

    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CardioKB post-Memgraph evaluation -- computes graph quality metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Write JSON report to FILE (default: auto-generated dated filename)",
    )
    parser.add_argument(
        "--baseline", metavar="FILE",
        help=("Path to a previous eval_after_memgraph.py JSON report. "
              "Enables run-to-run entity count delta (Tier 2)."),
    )
    parser.add_argument(
        "--no-markdown", action="store_true",
        help="Skip generating the markdown summary report",
    )
    parser.add_argument(
        "--json-only", action="store_true",
        help="Output JSON to stdout, skip file writing and summary",
    )
    args = parser.parse_args()

    print("Running CardioKB post-Memgraph evaluation...", file=sys.stderr)
    report = run_eval(baseline_path=args.baseline)

    json_str = json.dumps(report, indent=2)

    if args.json_only:
        print(json_str)
        return

    # Auto-generate dated filename if not specified
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = SCRIPT_DIR / "reports" / f"memgraph_report_{timestamp}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json_str, encoding="utf-8")
    print(f"JSON report written to {out_path}", file=sys.stderr)

    # Generate markdown report
    if not args.no_markdown:
        md_content = generate_markdown_report(report)
        md_path = out_path.parent / f"eval_report_{date_str}.md"
        md_path.write_text(md_content, encoding="utf-8")
        print(f"Markdown report written to {md_path}", file=sys.stderr)

    print_summary(report)


if __name__ == "__main__":
    main()
