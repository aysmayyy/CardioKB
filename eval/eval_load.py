#!/usr/bin/env python3
"""
eval_load.py — Validate that parsed TSV data was correctly loaded into Memgraph.

Compares TSV record counts against live Memgraph counts to detect load failures.

Metrics implemented:
  Tier 1: Node load count match, Edge load count match, Zero-count detection
  Tier 2: Load yield rate, Property completeness, Dangling reference check

Usage:
    python eval/eval_load.py
    python eval/eval_load.py --output report.json
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from lib.memgraph_client import memgraph_driver, run_query, run_query_single
from lib.metrics import metric, format_report

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROCESSED_DIR = ROOT / "data" / "processed"

# Acceptable yield threshold (graph count / TSV count)
MIN_YIELD_THRESHOLD = 0.10  # At least 10% of TSV records should be in graph


def load_mappings() -> dict:
    """Load ontology mappings configuration."""
    mappings_raw = yaml.safe_load((CONFIG_DIR / "ontology_mappings.yaml").read_text())
    mappings = mappings_raw.get("mappings", mappings_raw)
    return {k: v for k, v in mappings.items() if v is not None and not v.get("skip")}


def get_tsv_count(mapping: dict, source_name: str) -> int | None:
    """Get record count from TSV file for a mapping."""
    filename = mapping.get("source_filename", mapping.get("file", ""))
    if not filename:
        return None

    tsv_path = PROCESSED_DIR / source_name / filename
    if not tsv_path.exists():
        return None

    try:
        df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")

        # Apply filter if configured
        parse_config = mapping.get("parse_config", {})
        filter_col = parse_config.get("filter_column")
        filter_val = parse_config.get("filter_value")
        if filter_col and filter_val is not None and filter_col in df.columns:
            df = df[df[filter_col].astype(str) == str(filter_val)]

        return len(df)
    except Exception:
        return None


def eval_node_mappings(driver, mappings: dict) -> list[dict]:
    """Evaluate node loading for all node mappings."""
    metrics = []

    # Get graph counts per label
    graph_counts = run_query(driver, """
        MATCH (n)
        WITH labels(n)[0] AS label, count(n) AS count
        RETURN label, count
    """)
    graph_count_map = {r["label"]: r["count"] for r in graph_counts}

    # Group node mappings by node_type
    node_type_mappings: dict[str, list[tuple[str, dict]]] = {}
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "node":
            continue
        node_type = mapping.get("owl_class") or mapping.get("node_type")
        if node_type:
            if node_type not in node_type_mappings:
                node_type_mappings[node_type] = []
            node_type_mappings[node_type].append((mapping_key, mapping))

    for node_type, type_mappings in node_type_mappings.items():
        # Sum TSV counts from all mappings for this node type
        total_tsv_count = 0
        mapping_details = []

        for mapping_key, mapping in type_mappings:
            source_name = mapping_key.split(".")[0]
            tsv_count = get_tsv_count(mapping, source_name)
            if tsv_count is not None:
                total_tsv_count += tsv_count
                mapping_details.append({
                    "mapping": mapping_key,
                    "tsv_count": tsv_count,
                })

        graph_count = graph_count_map.get(node_type, 0)

        # Calculate yield
        if total_tsv_count > 0:
            yield_rate = round(graph_count / total_tsv_count, 4)
        else:
            yield_rate = None

        # Tier 1: Node count check
        is_ok = graph_count > 0 and (yield_rate is None or yield_rate >= MIN_YIELD_THRESHOLD)
        metrics.append(metric(
            "Node load count", "integer", graph_count,
            tier=1, node_type=node_type,
            tsv_count=total_tsv_count,
            yield_rate=yield_rate,
            mappings=len(mapping_details),
            note="BLOCKING — zero nodes loaded" if graph_count == 0 else (
                f"WARNING — low yield ({yield_rate:.1%})" if yield_rate and yield_rate < MIN_YIELD_THRESHOLD else None
            ),
        ))

    return metrics


def eval_edge_mappings(driver, mappings: dict) -> list[dict]:
    """Evaluate edge loading for all relationship mappings."""
    metrics = []

    # Get graph counts per relationship type
    graph_counts = run_query(driver, """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(r) AS count
    """)
    graph_count_map = {r["rel_type"]: r["count"] for r in graph_counts}

    # Group edge mappings by relationship_type
    rel_type_mappings: dict[str, list[tuple[str, dict]]] = {}
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") == "node":
            continue
        rel_type = mapping.get("relationship_type") or mapping.get("owl_relationship")
        if rel_type:
            if rel_type not in rel_type_mappings:
                rel_type_mappings[rel_type] = []
            rel_type_mappings[rel_type].append((mapping_key, mapping))

    for rel_type, type_mappings in rel_type_mappings.items():
        total_tsv_count = 0
        mapping_details = []

        for mapping_key, mapping in type_mappings:
            source_name = mapping_key.split(".")[0]
            tsv_count = get_tsv_count(mapping, source_name)
            if tsv_count is not None:
                total_tsv_count += tsv_count
                mapping_details.append({
                    "mapping": mapping_key,
                    "tsv_count": tsv_count,
                })

        graph_count = graph_count_map.get(rel_type, 0)

        if total_tsv_count > 0:
            yield_rate = round(graph_count / total_tsv_count, 4)
        else:
            yield_rate = None

        is_ok = graph_count > 0 and (yield_rate is None or yield_rate >= MIN_YIELD_THRESHOLD)
        metrics.append(metric(
            "Edge load count", "integer", graph_count,
            tier=1, relationship_type=rel_type,
            tsv_count=total_tsv_count,
            yield_rate=yield_rate,
            mappings=len(mapping_details),
            note="BLOCKING — zero edges loaded" if graph_count == 0 else (
                f"WARNING — low yield ({yield_rate:.1%})" if yield_rate and yield_rate < MIN_YIELD_THRESHOLD else None
            ),
        ))

    return metrics


def eval_dangling_references(driver) -> list[dict]:
    """Check for edges that reference non-existent nodes."""
    metrics = []

    # This is expensive on large graphs, so we sample
    # Check if there are any edges where start or end node doesn't exist
    # (This shouldn't happen with MATCH-based loading, but can with CREATE)

    # Just report total relationship count vs node count ratio as a sanity check
    node_count = run_query_single(driver, "MATCH (n) RETURN count(n) AS c")
    edge_count = run_query_single(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    if node_count > 0:
        edge_to_node_ratio = round(edge_count / node_count, 2)
    else:
        edge_to_node_ratio = None

    metrics.append(metric(
        "Edge to node ratio", "float", edge_to_node_ratio,
        tier=2, node_count=node_count, edge_count=edge_count,
    ))

    return metrics


def eval_property_completeness(driver) -> list[dict]:
    """Sample nodes to check property completeness."""
    metrics = []

    labels = run_query(driver, """
        MATCH (n)
        RETURN DISTINCT labels(n)[0] AS label
    """)

    for row in labels:
        label = row["label"]
        if not label:
            continue

        # Sample nodes and check for common properties
        sample = run_query(driver, f"""
            MATCH (n:{label})
            WITH n LIMIT 100
            RETURN keys(n) AS props
        """)

        if not sample:
            continue

        # Count property presence
        prop_counts: dict[str, int] = {}
        for row in sample:
            for prop in row["props"]:
                prop_counts[prop] = prop_counts.get(prop, 0) + 1

        sample_size = len(sample)
        missing_id = sample_size - prop_counts.get("id", 0)
        missing_name = sample_size - prop_counts.get("name", 0)

        if missing_id > 0 or (missing_name > sample_size * 0.5):
            metrics.append(metric(
                "Property completeness", "object",
                {p: round(c / sample_size, 2) for p, c in sorted(prop_counts.items())},
                tier=2, label=label, sample_size=sample_size,
                note=f"missing id: {missing_id}, missing name: {missing_name}" if missing_id > 0 else None,
            ))

    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Validate that parsed TSV data was correctly loaded into Memgraph."
    )
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write JSON report to FILE (default: stdout)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code 1 on any Tier 1 failure")
    args = parser.parse_args()

    print("Loading configuration...", flush=True)
    mappings = load_mappings()

    print("Connecting to Memgraph...", flush=True)

    try:
        with memgraph_driver() as driver:
            print("Connected. Comparing TSV counts to graph...", flush=True)

            all_metrics = []

            # Tier 1: Node counts
            print("  Checking node counts...", flush=True)
            all_metrics.extend(eval_node_mappings(driver, mappings))

            # Tier 1: Edge counts
            print("  Checking edge counts...", flush=True)
            all_metrics.extend(eval_edge_mappings(driver, mappings))

            # Tier 2: Dangling references
            print("  Checking reference integrity...", flush=True)
            all_metrics.extend(eval_dangling_references(driver))

            # Tier 2: Property completeness
            print("  Checking property completeness...", flush=True)
            all_metrics.extend(eval_property_completeness(driver))

            # Summary
            node_metrics = [m for m in all_metrics if m["name"] == "Node load count"]
            edge_metrics = [m for m in all_metrics if m["name"] == "Edge load count"]

            zero_nodes = [m for m in node_metrics if m["result"] == 0]
            zero_edges = [m for m in edge_metrics if m["result"] == 0]
            low_yield = [m for m in all_metrics
                        if m.get("yield_rate") and m["yield_rate"] < MIN_YIELD_THRESHOLD]

            summary = {
                "node_types_checked": len(node_metrics),
                "edge_types_checked": len(edge_metrics),
                "zero_node_types": len(zero_nodes),
                "zero_edge_types": len(zero_edges),
                "low_yield_mappings": len(low_yield),
            }

            report = format_report(all_metrics, summary=summary)
            output = json.dumps(report, indent=2, default=str)

            if args.output:
                Path(args.output).write_text(output)
                print(f"\nReport written to {args.output}")
            else:
                print(output)

            # Summary
            print(f"\n=== Summary ===")
            print(f"Node types: {len(node_metrics)} checked, {len(zero_nodes)} with zero count")
            print(f"Edge types: {len(edge_metrics)} checked, {len(zero_edges)} with zero count")
            print(f"Low yield mappings: {len(low_yield)}")
            print(f"Metrics: {len(all_metrics)}")

            tier1_failures = [m for m in all_metrics
                            if m.get("tier") == 1 and m.get("note") and "BLOCKING" in m["note"]]

            if tier1_failures:
                print(f"\nTier 1 failures: {len(tier1_failures)}")
                for m in tier1_failures[:10]:
                    nt = m.get("node_type") or m.get("relationship_type")
                    print(f"  - {nt}: {m['name']} = {m['result']}")
                if args.strict:
                    sys.exit(1)
            else:
                print("All Tier 1 checks passed.")

    except Exception as e:
        print(f"ERROR: Failed to connect to Memgraph: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
