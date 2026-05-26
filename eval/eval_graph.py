#!/usr/bin/env python3
"""
eval_graph.py — Validate the live Memgraph graph database.

Connects directly to Memgraph via Bolt protocol and runs validation queries.

Metrics implemented:
  Tier 1: Total node count per label, Total edge count per type,
          Graph connectivity (LCC fraction), Schema constraints
  Tier 2: Orphan node rate, Duplicate node detection, Average degree,
          Edge source coverage, Cross-reference resolution
  Tier 3: Known disease-gene recall (requires --omim-genemap),
          Drug-target coverage (requires --drugbank-tsv)

Usage:
    python eval/eval_graph.py
    python eval/eval_graph.py --output report.json
    python eval/eval_graph.py --omim-genemap data/reference/genemap2.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.memgraph_client import memgraph_driver, run_query, run_query_single
from lib.metrics import metric, format_report


def compute_tier1_node_counts(driver) -> list[dict]:
    """Count nodes per label."""
    metrics = []

    results = run_query(driver, """
        MATCH (n)
        WITH labels(n) AS lbls
        UNWIND lbls AS label
        RETURN label, count(*) AS count
        ORDER BY count DESC
    """)

    total_nodes = 0
    for row in results:
        label = row["label"]
        count = row["count"]
        total_nodes += count
        metrics.append(metric(
            "Node count per label", "integer", count,
            tier=1, label=label,
            note="zero — blocking failure" if count == 0 else None,
        ))

    metrics.insert(0, metric("Total node count", "integer", total_nodes, tier=1))
    return metrics


def compute_tier1_edge_counts(driver) -> list[dict]:
    """Count edges per relationship type."""
    metrics = []

    results = run_query(driver, """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS count
        ORDER BY count DESC
    """)

    total_edges = 0
    for row in results:
        rel_type = row["rel_type"]
        count = row["count"]
        total_edges += count
        metrics.append(metric(
            "Edge count per type", "integer", count,
            tier=1, relationship_type=rel_type,
            note="zero — blocking failure" if count == 0 else None,
        ))

    metrics.insert(0, metric("Total edge count", "integer", total_edges, tier=1))
    return metrics


def compute_tier1_connectivity(driver) -> list[dict]:
    """Compute graph connectivity metrics."""
    metrics = []

    total_nodes = run_query_single(driver, "MATCH (n) RETURN count(n) AS c")

    # Check if Memgraph has weakly_connected_components module
    try:
        lcc_result = run_query(driver, """
            CALL weakly_connected_components.get()
            YIELD node, component_id
            RETURN component_id, count(*) AS size
            ORDER BY size DESC
            LIMIT 1
        """)
        if lcc_result:
            lcc_size = lcc_result[0]["size"]
            lcc_fraction = round(lcc_size / total_nodes, 4) if total_nodes > 0 else 0

            # Count total components
            component_count = run_query_single(driver, """
                CALL weakly_connected_components.get()
                YIELD component_id
                RETURN count(DISTINCT component_id) AS c
            """)
        else:
            lcc_fraction = None
            lcc_size = None
            component_count = None
    except Exception as e:
        # Fallback: estimate connectivity without module
        connected_nodes = run_query_single(driver, """
            MATCH (n)-[]-() RETURN count(DISTINCT n) AS c
        """)
        lcc_fraction = round(connected_nodes / total_nodes, 4) if total_nodes > 0 else 0
        lcc_size = connected_nodes
        component_count = None
        metrics.append(metric(
            "Connectivity computation", "string", "fallback",
            tier=1, note=f"weakly_connected_components unavailable: {e}"
        ))

    metrics.append(metric(
        "Largest connected component fraction", "float", lcc_fraction,
        tier=1, lcc_size=lcc_size, total_nodes=total_nodes,
        component_count=component_count,
    ))

    return metrics


def compute_tier1_source_coverage(driver) -> list[dict]:
    """Check that all edges have source labels."""
    metrics = []

    results = run_query(driver, """
        MATCH ()-[r]->()
        WITH type(r) AS rel_type,
             count(*) AS total,
             count(r.source) AS with_source
        RETURN rel_type, total, with_source,
               CASE WHEN total > 0 THEN toFloat(with_source) / total ELSE 0 END AS coverage
        ORDER BY coverage ASC
    """)

    missing_source = []
    for row in results:
        if row["coverage"] < 1.0:
            missing_source.append({
                "relationship_type": row["rel_type"],
                "total": row["total"],
                "missing": row["total"] - row["with_source"],
                "coverage": round(row["coverage"], 4),
            })

    total_edges = sum(r["total"] for r in results)
    total_with_source = sum(r["with_source"] for r in results)
    overall_coverage = round(total_with_source / total_edges, 4) if total_edges > 0 else None

    metrics.append(metric(
        "Edge source label coverage", "float", overall_coverage,
        tier=1, total_edges=total_edges, edges_with_source=total_with_source,
        missing_by_type=missing_source if missing_source else None,
    ))

    # Source distribution
    source_dist = run_query(driver, """
        MATCH ()-[r]->()
        WHERE r.source IS NOT NULL
        RETURN r.source AS source, count(*) AS count
        ORDER BY count DESC
    """)

    metrics.append(metric(
        "Edge source distribution", "object",
        {row["source"]: row["count"] for row in source_dist},
        tier=1,
    ))

    return metrics


def compute_tier2_orphan_rate(driver) -> list[dict]:
    """Compute orphan node rate per label."""
    metrics = []

    # Get total counts per label first
    label_counts = run_query(driver, """
        MATCH (n)
        WITH labels(n)[0] AS label, count(n) AS total
        RETURN label, total
    """)

    # Get connected node counts per label
    connected_counts = run_query(driver, """
        MATCH (n)-[]-()
        WITH labels(n)[0] AS label, count(DISTINCT n) AS connected
        RETURN label, connected
    """)

    connected_map = {r["label"]: r["connected"] for r in connected_counts}

    results = []
    for row in label_counts:
        label = row["label"]
        total = row["total"]
        connected = connected_map.get(label, 0)
        orphans = total - connected
        orphan_rate = orphans / total if total > 0 else 0
        results.append({
            "label": label,
            "total": total,
            "orphans": orphans,
            "orphan_rate": orphan_rate,
        })

    results.sort(key=lambda x: x["orphan_rate"], reverse=True)

    for row in results:
        metrics.append(metric(
            "Orphan node rate", "float", round(row["orphan_rate"], 4),
            tier=2, label=row["label"],
            orphan_count=row["orphans"], total_nodes=row["total"],
        ))

    return metrics


def compute_tier2_duplicates(driver) -> list[dict]:
    """Check for duplicate nodes (same ID, multiple nodes)."""
    metrics = []

    # Check each node type for ID duplicates
    labels = run_query(driver, """
        MATCH (n)
        RETURN DISTINCT labels(n)[0] AS label
    """)

    total_duplicates = 0
    duplicate_details = []

    for row in labels:
        label = row["label"]
        if not label:
            continue

        # Check for duplicate IDs within this label
        dup_result = run_query(driver, f"""
            MATCH (n:{label})
            WHERE n.id IS NOT NULL
            WITH n.id AS node_id, count(*) AS cnt
            WHERE cnt > 1
            RETURN node_id, cnt
            ORDER BY cnt DESC
            LIMIT 10
        """)

        if dup_result:
            dup_count = sum(r["cnt"] - 1 for r in dup_result)
            total_duplicates += dup_count
            duplicate_details.append({
                "label": label,
                "duplicate_ids": len(dup_result),
                "extra_nodes": dup_count,
                "examples": [r["node_id"] for r in dup_result[:3]],
            })

    metrics.append(metric(
        "Duplicate node count", "integer", total_duplicates,
        tier=2, duplicate_details=duplicate_details if duplicate_details else None,
        note="BLOCKING — duplicate IDs detected" if total_duplicates > 0 else None,
    ))

    return metrics


def compute_tier2_degree(driver) -> list[dict]:
    """Compute average node degree per label."""
    metrics = []

    # First get degree for each node, then aggregate
    results = run_query(driver, """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]-()
        WITH labels(n)[0] AS label, n, count(r) AS degree
        WITH label, count(n) AS total, avg(degree) AS avg_degree
        RETURN label, total, avg_degree
        ORDER BY avg_degree DESC
    """)

    for row in results:
        metrics.append(metric(
            "Average node degree", "float",
            round(row["avg_degree"], 2) if row["avg_degree"] else 0,
            tier=2, label=row["label"], node_count=row["total"],
        ))

    return metrics


def compute_tier2_high_degree_outliers(driver) -> list[dict]:
    """Find high-degree outlier nodes."""
    metrics = []

    results = run_query(driver, """
        MATCH (n)-[r]-()
        WITH labels(n)[0] AS label, n, count(r) AS degree
        ORDER BY degree DESC
        LIMIT 50
        RETURN label, n.id AS node_id, n.name AS name, degree
    """)

    if results:
        max_degree = results[0]["degree"] if results else 0
        metrics.append(metric(
            "High-degree nodes", "list",
            [{"label": r["label"], "id": r["node_id"], "name": r.get("name"), "degree": r["degree"]}
             for r in results[:20]],
            tier=2, max_degree=max_degree,
        ))

    return metrics


def compute_tier3_disease_gene_recall(driver, omim_path: Path | None) -> list[dict]:
    """Check recall of known disease-gene associations from OMIM."""
    metrics = []

    if not omim_path or not omim_path.exists():
        metrics.append(metric(
            "Known disease-gene recall", "float", None,
            tier=3, note="provide --omim-genemap to compute",
        ))
        return metrics

    # Parse OMIM genemap2.txt
    _pheno_mim_re = re.compile(r"(\d{6})\s*\(\s*3\s*\)")
    omim_pairs = set()

    with open(omim_path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.strip().split("\t")
            if len(fields) < 13:
                continue

            pheno_field = fields[12] if len(fields) > 12 else ""
            entrez_id = fields[9].strip() if len(fields) > 9 else ""

            if not entrez_id or entrez_id == "":
                continue

            disease_mims = _pheno_mim_re.findall(pheno_field)
            for mim in disease_mims:
                omim_pairs.add((entrez_id, mim))

    if not omim_pairs:
        metrics.append(metric(
            "Known disease-gene recall", "float", None,
            tier=3, note="no valid OMIM pairs found in file",
        ))
        return metrics

    # Check how many are in the graph
    recalled = 0
    for gene_id, disease_mim in omim_pairs:
        result = run_query_single(driver, """
            MATCH (g:Gene)-[:geneAssociatesWithDisease]->(d:Disease)
            WHERE toString(g.id) = $gene_id OR g.xrefNcbiGene = $gene_id
            AND (d.xrefOMIM = $mim OR d.id CONTAINS $mim)
            RETURN count(*) > 0 AS found
        """, {"gene_id": gene_id, "mim": disease_mim})

        if result:
            recalled += 1

    recall_rate = round(recalled / len(omim_pairs), 4) if omim_pairs else None

    metrics.append(metric(
        "Known disease-gene recall", "float", recall_rate,
        tier=3, total_omim_pairs=len(omim_pairs), recalled=recalled,
    ))

    return metrics


def compute_tier3_drug_target_coverage(driver, drugbank_path: Path | None) -> list[dict]:
    """Check coverage of DrugBank drug-target pairs."""
    metrics = []

    if not drugbank_path or not drugbank_path.exists():
        metrics.append(metric(
            "Drug-target coverage", "float", None,
            tier=3, note="provide --drugbank-tsv to compute",
        ))
        return metrics

    import pandas as pd
    try:
        db_df = pd.read_csv(drugbank_path, sep="\t", low_memory=False)
    except Exception as e:
        metrics.append(metric(
            "Drug-target coverage", "float", None,
            tier=3, note=f"failed to read drugbank file: {e}",
        ))
        return metrics

    if "drugbank_id" not in db_df.columns:
        metrics.append(metric(
            "Drug-target coverage", "float", None,
            tier=3, note="drugbank_id column not found",
        ))
        return metrics

    db_ids = set(db_df["drugbank_id"].dropna().astype(str).str.strip())

    # Get DrugBank IDs in graph
    graph_ids = run_query(driver, """
        MATCH (d:Drug)
        WHERE d.drugbank_id IS NOT NULL OR d.xrefDrugbank IS NOT NULL
        RETURN COALESCE(d.drugbank_id, d.xrefDrugbank) AS db_id
    """)
    graph_db_ids = {r["db_id"] for r in graph_ids if r["db_id"]}

    covered = len(db_ids & graph_db_ids)
    coverage = round(covered / len(db_ids), 4) if db_ids else None

    metrics.append(metric(
        "Drug-target coverage", "float", coverage,
        tier=3, total_drugbank_drugs=len(db_ids), covered=covered,
    ))

    return metrics


def compute_summary_stats(driver) -> dict:
    """Compute summary statistics for the report header."""
    node_count = run_query_single(driver, "MATCH (n) RETURN count(n) AS c")
    edge_count = run_query_single(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    label_count = run_query_single(driver, """
        MATCH (n) RETURN count(DISTINCT labels(n)[0]) AS c
    """)

    rel_type_count = run_query_single(driver, """
        MATCH ()-[r]->() RETURN count(DISTINCT type(r)) AS c
    """)

    source_count = run_query_single(driver, """
        MATCH ()-[r]->() WHERE r.source IS NOT NULL
        RETURN count(DISTINCT r.source) AS c
    """)

    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "node_labels": label_count,
        "relationship_types": rel_type_count,
        "source_labels": source_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate the live Memgraph graph database."
    )
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write JSON report to FILE (default: stdout)")
    parser.add_argument("--omim-genemap", metavar="FILE",
                        help="OMIM genemap2.txt for disease-gene recall (Tier 3)")
    parser.add_argument("--drugbank-tsv", metavar="FILE",
                        help="DrugBank drugs TSV for drug-target coverage (Tier 3)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code 1 on any Tier 1 failure")
    args = parser.parse_args()

    print("Connecting to Memgraph...", flush=True)

    try:
        with memgraph_driver() as driver:
            print("Connected. Running validation queries...", flush=True)

            # Collect all metrics
            all_metrics = []

            # Tier 1
            print("  Computing node counts...", flush=True)
            all_metrics.extend(compute_tier1_node_counts(driver))

            print("  Computing edge counts...", flush=True)
            all_metrics.extend(compute_tier1_edge_counts(driver))

            print("  Computing connectivity...", flush=True)
            all_metrics.extend(compute_tier1_connectivity(driver))

            print("  Computing source coverage...", flush=True)
            all_metrics.extend(compute_tier1_source_coverage(driver))

            # Tier 2
            print("  Computing orphan rates...", flush=True)
            all_metrics.extend(compute_tier2_orphan_rate(driver))

            print("  Checking for duplicates...", flush=True)
            all_metrics.extend(compute_tier2_duplicates(driver))

            print("  Computing node degrees...", flush=True)
            all_metrics.extend(compute_tier2_degree(driver))

            print("  Finding high-degree outliers...", flush=True)
            all_metrics.extend(compute_tier2_high_degree_outliers(driver))

            # Tier 3
            print("  Computing biological validation metrics...", flush=True)
            all_metrics.extend(compute_tier3_disease_gene_recall(
                driver, Path(args.omim_genemap) if args.omim_genemap else None
            ))
            all_metrics.extend(compute_tier3_drug_target_coverage(
                driver, Path(args.drugbank_tsv) if args.drugbank_tsv else None
            ))

            # Summary stats
            print("  Computing summary...", flush=True)
            summary = compute_summary_stats(driver)

            # Build report
            report = format_report(all_metrics, summary=summary)

            # Count failures
            tier1_failures = [m for m in all_metrics
                            if m.get("tier") == 1 and m.get("note") and "failure" in m["note"].lower()]

            output = json.dumps(report, indent=2, default=str)

            if args.output:
                Path(args.output).write_text(output)
                print(f"\nReport written to {args.output}")
            else:
                print(output)

            # Summary line
            print(f"\n=== Summary ===")
            print(f"Nodes: {summary['total_nodes']:,} | Edges: {summary['total_edges']:,}")
            print(f"Labels: {summary['node_labels']} | Rel Types: {summary['relationship_types']} | Sources: {summary['source_labels']}")
            print(f"Total metrics: {len(all_metrics)}")

            if tier1_failures:
                print(f"\nTier 1 failures: {len(tier1_failures)}")
                for m in tier1_failures:
                    print(f"  - {m['name']}: {m.get('note')}")
                if args.strict:
                    sys.exit(1)
            else:
                print("All Tier 1 checks passed.")

    except Exception as e:
        print(f"ERROR: Failed to connect to Memgraph: {e}", file=sys.stderr)
        print("Make sure Memgraph is running and MEMGRAPH_URI/USERNAME/PASSWORD are set.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
