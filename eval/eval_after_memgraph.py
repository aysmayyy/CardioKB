"""
eval_after_memgraph.py — Tier 1/2/3 metrics computed from exported graph CSVs.

Metrics implemented (see docs/eval_metrics.md):
  Tier 1: Total node count per OWL class,
          Total edge count per OWL ObjectProperty,
          Domain/range constraint violation count,
          Relationship resolution rate per mapping,
          Merge match rate per source
  Tier 2: Orphan node rate,
          Internal cross-reference resolution rate,
          Exact-IRI duplicate count, Cross-reference duplicate count,
          Duplicate edge rate, Largest connected component fraction,
          Average node degree per OWL class,
          Run-to-run entity count delta (requires --baseline),
          High-degree outlier count per ObjectProperty
  Tier 3: Known disease-gene recall rate (requires --omim-genemap),
          Drug-target coverage (requires --drugbank-tsv)

Output JSON schema (one object per metric):
  name         — metric name from eval_metrics.md
  data_type    — integer | float | list[str]
  tier         — 1, 2, or 3
  result       — the computed value
  (extra keys) — node_type, edge_type, note, etc.

Usage:
    python eval/eval_after_memgraph.py
    python eval/eval_after_memgraph.py --output report.json
    python eval/eval_after_memgraph.py --baseline baseline.json --output report.json
    python eval/eval_after_memgraph.py --omim-genemap genemap2.txt
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "data" / "output"
PROCESSED_DIR = ROOT / "data" / "processed"

RDF_NS  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL_NS  = "http://www.w3.org/2002/07/owl#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
RDF_RESOURCE = f"{{{RDF_NS}}}resource"
RDF_ABOUT    = f"{{{RDF_NS}}}about"


def load_configs() -> tuple[dict, dict]:
    project = yaml.safe_load((CONFIG_DIR / "project.yaml").read_text())["project"]
    mappings_raw = yaml.safe_load((CONFIG_DIR / "ontology_mappings.yaml").read_text())
    mappings = mappings_raw.get("mappings", mappings_raw)
    mappings = {k: v for k, v in mappings.items() if v is not None}
    return project, mappings


def _local_name(iri: str) -> str:
    if "#" in iri:
        return iri.split("#")[-1]
    return iri.lstrip("#")


def parse_domain_range(base_rdf: Path) -> dict[str, dict]:
    """Return {prop_local_name: {"domain": str|None, "range": str|None}} from the ontology."""
    tree = ET.parse(base_rdf)
    domain_range: dict[str, dict] = {}
    for child in tree.getroot():
        if child.tag != f"{{{OWL_NS}}}ObjectProperty":
            continue
        about = child.get(RDF_ABOUT, "")
        local = _local_name(about)
        if not local:
            continue
        domain = None
        range_ = None
        for sub in child:
            if sub.tag == f"{{{RDFS_NS}}}domain":
                domain = _local_name(sub.get(RDF_RESOURCE, ""))
            elif sub.tag == f"{{{RDFS_NS}}}range":
                range_ = _local_name(sub.get(RDF_RESOURCE, ""))
        domain_range[local] = {"domain": domain or None, "range": range_ or None}
    return domain_range


def load_graph_csvs() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Return (nodes_by_type, edges_by_type) from nodes_*.csv and edges_*.csv."""
    nodes: dict[str, pd.DataFrame] = {}
    for p in sorted(OUTPUT_DIR.glob("nodes_*.csv")):
        node_type = p.stem[len("nodes_"):]
        nodes[node_type] = pd.read_csv(p, low_memory=False)

    edges: dict[str, pd.DataFrame] = {}
    for p in sorted(OUTPUT_DIR.glob("edges_*.csv")):
        edge_type = p.stem[len("edges_"):]
        edges[edge_type] = pd.read_csv(p, low_memory=False)

    return nodes, edges


def _metric(name: str, data_type: str, result, tier: int, **kwargs) -> dict:
    entry = {"name": name, "data_type": data_type, "tier": tier, "result": result}
    entry.update({k: v for k, v in kwargs.items() if v is not None})
    return entry


def compute_tier1_metrics(
    nodes: dict[str, pd.DataFrame],
    edges: dict[str, pd.DataFrame],
    domain_range: dict[str, dict],
    mappings: dict,
    min_yield_threshold: float = 0.10,
) -> tuple[list[dict], list[dict]]:
    metrics: list[dict] = []

    # Build property → value index for relationship resolution checks.
    prop_to_values: dict[str, set[str]] = defaultdict(set)
    for ntype, ndf in nodes.items():
        for col in ndf.columns:
            valid = ndf[col].dropna().astype(str).str.strip()
            prop_to_values[col].update(v for v in valid if v != "nan")

    # --- Total node count per OWL class ---
    for node_type, df in nodes.items():
        metrics.append(_metric(
            "Total node count per OWL class", 
            "integer", 
            len(df),
            tier=1,
            node_type=node_type,
            note="zero — blocking failure" if len(df) == 0 else None,
        ))

    # --- Total edge count per OWL ObjectProperty ---
    for edge_type, df in edges.items():
        metrics.append(_metric(
            "Total edge count per OWL ObjectProperty", "integer", len(df),
            tier=1, edge_type=edge_type,
            note="zero — blocking failure" if len(df) == 0 else None,
        ))

    # --- Domain/range constraint violation count ---
    # Build node_id → node_type index from all node CSVs.
    # Exact-type check only; subclass relationships are not resolved.
    node_id_to_type: dict[str, str] = {}
    for node_type, df in nodes.items():
        if "id" in df.columns:
            for nid in df["id"].dropna().astype(str):
                node_id_to_type[nid] = node_type

    for edge_type, edf in edges.items():
        dr = domain_range.get(edge_type, {})
        expected_domain = dr.get("domain")
        expected_range  = dr.get("range")
        if not expected_domain and not expected_range:
            continue
        if "start_id" not in edf.columns or "end_id" not in edf.columns:
            continue

        violations = 0
        if expected_domain:
            actual_domains = edf["start_id"].dropna().astype(str).map(node_id_to_type)
            violations += int((actual_domains.notna() & (actual_domains != expected_domain)).sum())
        if expected_range:
            actual_ranges = edf["end_id"].dropna().astype(str).map(node_id_to_type)
            violations += int((actual_ranges.notna() & (actual_ranges != expected_range)).sum())

        metrics.append(_metric(
            "Domain/range constraint violation count", "integer", violations,
            tier=1, edge_type=edge_type,
            expected_domain=expected_domain, expected_range=expected_range,
            note="exact-type check only; subclass relationships not resolved",
        ))

    # --- Relationship resolution rate per mapping ---
    processed_dir = ROOT / "data" / "processed"
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "relationship" or mapping.get("skip"):
            continue
        rel_type = mapping.get("relationship_type") or mapping.get("owl_relationship")
        source_name = mapping_key.split(".")[0]
        tsv_path = processed_dir / source_name / mapping.get("source_filename", "")
        if not tsv_path.exists() or rel_type not in edges:
            continue

        try:
            src_df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
        except Exception:
            continue

        parse_config = mapping.get("parse_config", {})
        filter_col = parse_config.get("filter_column")
        filter_val = parse_config.get("filter_value")
        if filter_col and filter_val is not None and filter_col in src_df.columns:
            src_df = src_df[src_df[filter_col].astype(str) == str(filter_val)]

        n_source = len(src_df)
        if n_source == 0:
            continue

        subj_col = parse_config.get("subject_column_name")
        subj_prop = parse_config.get("subject_match_property") or "id"
        obj_col = parse_config.get("object_column_name")
        obj_prop = parse_config.get("object_match_property") or "id"

        if (not subj_col or not obj_col
                or subj_col not in src_df.columns or obj_col not in src_df.columns):
            continue

        subj_series = src_df[subj_col].fillna("").astype(str).str.strip()
        obj_series = src_df[obj_col].fillna("").astype(str).str.strip()
        subj_match = subj_series.isin(prop_to_values.get(subj_prop, set())) & (subj_series != "")
        obj_match = obj_series.isin(prop_to_values.get(obj_prop, set())) & (obj_series != "")
        resolved_count = int((subj_match & obj_match).sum())
        rate = round(resolved_count / n_source, 4)

        metrics.append(_metric(
            "Relationship resolution rate per mapping", "float", rate,
            tier=1, mapping=mapping_key, edge_type=rel_type,
            source_rows=n_source, resolved_rows=resolved_count,
        ))

    # --- Edge yield vs source TSV (minimum threshold check) ---
    # Compare actual edge counts against source TSV row counts.
    # Flags as failure if yield drops below threshold.
    edge_yield_threshold = min_yield_threshold
    edge_yield_failures: list[dict] = []

    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "relationship" or mapping.get("skip"):
            continue
        rel_type = mapping.get("relationship_type") or mapping.get("owl_relationship")
        source_name = mapping_key.split(".")[0]
        tsv_path = processed_dir / source_name / mapping.get("source_filename", "")
        if not tsv_path.exists():
            continue

        try:
            src_df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
        except Exception:
            continue

        parse_config = mapping.get("parse_config", {})
        filter_col = parse_config.get("filter_column")
        filter_val = parse_config.get("filter_value")
        if filter_col and filter_val is not None and filter_col in src_df.columns:
            src_df = src_df[src_df[filter_col].astype(str) == str(filter_val)]

        n_source = len(src_df)
        if n_source == 0:
            continue

        # Get actual edge count from graph
        edge_df = edges.get(rel_type, pd.DataFrame())
        # Filter by source label if available
        source_label = mapping.get("source_label")
        if source_label and "source" in edge_df.columns:
            edge_count = len(edge_df[edge_df["source"] == source_label])
        else:
            edge_count = len(edge_df)

        yield_rate = edge_count / n_source if n_source > 0 else 0
        is_failure = yield_rate < edge_yield_threshold and n_source >= 100

        if is_failure:
            edge_yield_failures.append({
                "mapping": mapping_key,
                "edge_type": rel_type,
                "source_rows": n_source,
                "edge_count": edge_count,
                "yield_pct": round(yield_rate * 100, 2),
                "threshold_pct": round(edge_yield_threshold * 100, 2),
            })

        metrics.append(_metric(
            "Edge yield vs source TSV", "float", round(yield_rate, 4),
            tier=1, mapping=mapping_key, edge_type=rel_type,
            source_rows=n_source, edge_count=edge_count,
            threshold=edge_yield_threshold,
            note="FAILURE — below minimum threshold" if is_failure else None,
        ))

    # Summary metric for edge yield failures
    if edge_yield_failures:
        metrics.append(_metric(
            "Edge yield failures", "list",
            [f["mapping"] for f in edge_yield_failures],
            tier=1,
            threshold_pct=round(edge_yield_threshold * 100, 2),
            failure_details=edge_yield_failures,
            note=f"BLOCKING — {len(edge_yield_failures)} mappings below {edge_yield_threshold*100:.0f}% yield",
        ))

    # --- Merge match rate per source ---
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "node" or not mapping.get("merge") or mapping.get("skip"):
            continue
        node_type = mapping.get("node_type")
        source_name = mapping_key.split(".")[0]
        parse_config = mapping.get("parse_config", {})
        merge_cfg = parse_config.get("merge_column") or {}
        merge_src_col = merge_cfg.get("source_column_name")
        merge_data_prop = merge_cfg.get("data_property")

        tsv_path = processed_dir / source_name / mapping["source_filename"]
        if not tsv_path.exists() or not merge_src_col:
            continue

        try:
            src_df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
        except Exception:
            continue

        if merge_src_col not in src_df.columns:
            continue

        valid_merge = src_df[merge_src_col].notna() & (
            src_df[merge_src_col].astype(str).str.strip() != ""
        )
        n_eligible = int(valid_merge.sum())
        if n_eligible == 0:
            continue

        node_df = nodes.get(node_type)
        if node_df is not None and merge_data_prop and merge_data_prop in node_df.columns:
            existing_keys = set(
                node_df[merge_data_prop].dropna().astype(str).str.strip()
            )
            matched = src_df.loc[valid_merge, merge_src_col].astype(str).str.strip().isin(existing_keys)
            match_rate = round(float(matched.mean()), 4)
        else:
            match_rate = None

        metrics.append(_metric(
            "Merge match rate per source", "float", match_rate,
            tier=1, mapping=mapping_key, node_type=node_type,
            merge_eligible_count=n_eligible,
            note="output CSV missing merge property column" if match_rate is None else None,
        ))

    return metrics, edge_yield_failures


def compute_tier2_metrics(
    nodes: dict[str, pd.DataFrame],
    edges: dict[str, pd.DataFrame],
    baseline: dict | None,
    current_counts: dict,
) -> list[dict]:
    metrics: list[dict] = []

    # Build node connectivity: node_id → degree count (across all edge types).
    all_endpoints = []
    for edge_type, edf in edges.items():
        for col in ("start_id", "end_id"):
            if col in edf.columns:
                all_endpoints.append(edf[col].dropna().astype(str))
    node_edges: dict[str, int] = (
        pd.concat(all_endpoints).value_counts().to_dict() if all_endpoints else {}
    )

    # --- Orphan node rate ---
    for node_type, df in nodes.items():
        if "id" not in df.columns or len(df) == 0:
            continue
        orphan_count = sum(
            1 for nid in df["id"].dropna().astype(str)
            if node_edges.get(nid, 0) == 0
        )
        metrics.append(_metric(
            "Orphan node rate", "float",
            round(orphan_count / len(df), 4),
            tier=2, node_type=node_type,
            orphan_count=orphan_count, total_nodes=len(df),
        ))

    # Build xref_value → set(node_uris) index; shared by two cross-reference metrics.
    xref_to_uris: dict[str, set[str]] = defaultdict(set)
    for node_type, df in nodes.items():
        xref_cols = [c for c in df.columns if c.startswith("xref")]
        if "uri" not in df.columns or not xref_cols:
            continue
        for col in xref_cols:
            mask = (
                df[col].notna()
                & (df[col].astype(str).str.strip() != "")
                & (df[col].astype(str) != "nan")
            )
            sub = df.loc[mask, [col, "uri"]]
            for val, grp in sub.groupby(col):
                xref_to_uris[str(val).strip()].update(grp["uri"].astype(str))

    # --- Internal cross-reference resolution rate ---
    # An xref "resolves" if its value appears on at least two distinct nodes (different URIs).
    total_xref_entries = sum(len(uris) for uris in xref_to_uris.values())
    resolved_xref = sum(len(uris) for uris in xref_to_uris.values() if len(uris) > 1)
    xref_resolution_rate = round(resolved_xref / total_xref_entries, 4) if total_xref_entries > 0 else None
    metrics.append(_metric(
        "Internal cross-reference resolution rate", "float", xref_resolution_rate,
        tier=2, total_xref_entries=total_xref_entries,
    ))

    # --- Exact-IRI duplicate count ---
    total_iri_dups = 0
    for node_type, df in nodes.items():
        if "uri" in df.columns:
            dup_count = int(df["uri"].dropna().duplicated().sum())
            total_iri_dups += dup_count
    metrics.append(_metric(
        "Exact-IRI duplicate count", "integer", total_iri_dups, tier=2,
    ))

    # --- Cross-reference duplicate count ---
    # Node pairs sharing at least one xref value but having different IRIs.
    # Uses the xref_to_uris index already built above.
    xref_dup_pairs = sum(
        len(uris) * (len(uris) - 1) // 2
        for uris in xref_to_uris.values()
        if len(uris) > 1
    )
    metrics.append(_metric(
        "Cross-reference duplicate count", "integer", xref_dup_pairs, tier=2,
        note="lower-bound estimate of unresolved duplicates",
    ))

    # --- Duplicate edge rate ---
    total_edges = 0
    total_dup_edges = 0
    for edge_type, edf in edges.items():
        if "start_id" in edf.columns and "end_id" in edf.columns:
            n = len(edf)
            dup = int(edf.duplicated(subset=["start_id", "end_id"]).sum())
            total_edges += n
            total_dup_edges += dup
    dup_edge_rate = (
        round(total_dup_edges / total_edges, 4) if total_edges > 0 else None
    )
    metrics.append(_metric(
        "Duplicate edge rate", "float", dup_edge_rate,
        tier=2, duplicate_edge_count=total_dup_edges, total_edge_count=total_edges,
    ))

    # --- Largest connected component fraction ---
    # Build undirected graph from all edges.
    G = nx.Graph()
    for df in nodes.values():
        if "id" in df.columns:
            G.add_nodes_from(df["id"].dropna().astype(str))
    for edge_type, edf in edges.items():
        if "start_id" in edf.columns and "end_id" in edf.columns:
            G.add_edges_from(
                zip(edf["start_id"].dropna().astype(str), edf["end_id"].dropna().astype(str))
            )

    total_nodes = G.number_of_nodes()
    if total_nodes > 0:
        components = list(nx.connected_components(G))
        largest_cc = max(len(c) for c in components)
        lcc_fraction = round(largest_cc / total_nodes, 4)
        n_components = len(components)
    else:
        lcc_fraction = None
        n_components = None

    metrics.append(_metric(
        "Largest connected component fraction", "float", lcc_fraction,
        tier=2, total_nodes=total_nodes, disconnected_component_count=n_components,
    ))

    # --- Average node degree per OWL class ---
    for node_type, df in nodes.items():
        if "id" not in df.columns or len(df) == 0:
            continue
        degrees = [node_edges.get(str(nid), 0) for nid in df["id"].dropna().astype(str)]
        avg_degree = round(float(np.mean(degrees)), 4) if degrees else None
        metrics.append(_metric(
            "Average node degree per OWL class", "float", avg_degree,
            tier=2, node_type=node_type,
        ))

    # --- Run-to-run entity count delta ---
    if baseline:
        prev_counts = baseline.get("entity_counts", {})
        per_type_deltas = {k: current_counts[k] - prev_counts.get(k, 0) for k in current_counts}
        max_abs_delta = max(abs(v) for v in per_type_deltas.values()) if per_type_deltas else 0
        metrics.append(_metric(
            "Run-to-run entity count delta", "object", per_type_deltas,
            tier=2, max_abs_delta=max_abs_delta,
        ))
    else:
        metrics.append(_metric(
            "Run-to-run entity count delta", "object", None,
            tier=2, note="no baseline provided; pass --baseline to compare runs",
        ))

    # --- High-degree outlier count per ObjectProperty (Tier 3) ---
    for edge_type, edf in edges.items():
        if "start_id" not in edf.columns and "end_id" not in edf.columns:
            continue
        degree_counter: Counter = Counter()
        for col in ("start_id", "end_id"):
            if col in edf.columns:
                degree_counter.update(edf[col].dropna().astype(str))
        if not degree_counter:
            continue
        degrees_arr = np.array(list(degree_counter.values()))
        threshold = float(np.percentile(degrees_arr, 99))
        outlier_count = int((degrees_arr > threshold).sum())
        metrics.append(_metric(
            "High-degree outlier count per ObjectProperty", "integer", outlier_count,
            tier=3, edge_type=edge_type,
            p99_degree_threshold=round(threshold, 2),
        ))

    return metrics


def compute_merge_rate_analysis(
    nodes: dict[str, pd.DataFrame],
    mappings: dict,
) -> tuple[list[dict], dict]:
    """
    Compute merge rate analysis: raw records parsed vs unique IDs after deduplication.

    For each source, compares:
    - raw_records: total rows in the TSV
    - unique_ids: unique values in the ID column (after internal deduplication)
    - merge_rate: unique_ids / raw_records * 100 (100% = no duplicates)

    Low merge rates indicate duplicate records that got merged.

    Returns:
        metrics: list of metric dicts
        summary: dict with per-source breakdown for the report
    """
    metrics: list[dict] = []
    summary: dict[str, dict] = {}

    # Group node mappings by source
    source_node_mappings: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "node" or mapping.get("skip"):
            continue
        source_name = mapping_key.split(".")[0]
        source_node_mappings[source_name].append((mapping_key, mapping))

    merge_rates: list[float] = []

    for source_name, source_mappings in sorted(source_node_mappings.items()):
        source_raw_count = 0
        source_unique_ids = 0
        source_node_types: set[str] = set()
        per_file_stats: list[dict] = []

        for mapping_key, mapping in source_mappings:
            tsv_path = PROCESSED_DIR / source_name / mapping.get("source_filename", "")
            if not tsv_path.exists():
                continue

            try:
                df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
                raw_count = len(df)
                source_raw_count += raw_count

                node_type = mapping.get("owl_class") or mapping.get("node_type")
                if node_type:
                    source_node_types.add(node_type)

                # Get ID column from mapping
                id_col = mapping.get("id_column")
                if not id_col and "parse_config" in mapping:
                    id_col = mapping["parse_config"].get("iri_column_name")

                unique_count = raw_count  # default if no ID column
                if id_col and id_col in df.columns:
                    unique_ids = df[id_col].dropna().astype(str).str.strip()
                    unique_ids = unique_ids[unique_ids != ""]
                    unique_count = unique_ids.nunique()

                source_unique_ids += unique_count

                per_file_stats.append({
                    "file": mapping.get("source_filename", ""),
                    "raw": raw_count,
                    "unique": unique_count,
                    "id_column": id_col,
                })
            except Exception:
                continue

        if source_raw_count == 0:
            continue

        # Merge rate: unique / raw * 100 (100% = no duplicates, lower = more duplicates merged)
        merge_rate = round((source_unique_ids / source_raw_count) * 100, 2)
        merge_rates.append(merge_rate)

        # Also get final graph node count for this source's node types
        graph_node_count = sum(len(nodes.get(nt, pd.DataFrame())) for nt in source_node_types)

        summary[source_name] = {
            "raw_records": source_raw_count,
            "unique_ids": source_unique_ids,
            "merge_rate_pct": merge_rate,
            "node_types": sorted(source_node_types),
            "graph_nodes": graph_node_count,
            "files": per_file_stats,
        }

        metrics.append(_metric(
            "Merge rate per source", "float", merge_rate,
            tier=1, source=source_name,
            raw_records=source_raw_count,
            unique_ids=source_unique_ids,
            node_types=sorted(source_node_types),
        ))

    # Flag sources with unusually low merge rates (below 50% = high duplication)
    if merge_rates:
        median_rate = float(np.median(merge_rates))
        low_threshold = min(median_rate * 0.5, 50.0)

        flagged_sources = []
        for source_name, data in summary.items():
            rate = data.get("merge_rate_pct")
            if rate is not None and rate < low_threshold:
                flagged_sources.append({
                    "source": source_name,
                    "merge_rate_pct": rate,
                    "raw_records": data["raw_records"],
                    "unique_ids": data["unique_ids"],
                    "duplicates": data["raw_records"] - data["unique_ids"],
                })

        metrics.append(_metric(
            "Low merge rate sources", "list",
            [f["source"] for f in flagged_sources],
            tier=2,
            threshold_pct=round(low_threshold, 2),
            median_rate_pct=round(median_rate, 2),
            flagged_details=flagged_sources if flagged_sources else None,
            note="potential duplicate node issues - high internal duplication" if flagged_sources else "no issues detected",
        ))

    return metrics, summary


def compute_cross_source_merge_analysis(
    nodes: dict[str, pd.DataFrame],
    mappings: dict,
) -> tuple[list[dict], dict]:
    """
    Analyze cross-source merging for node types with multiple contributing sources.

    For each node type contributed by multiple sources, compares:
    - sum_unique_per_source: total unique IDs if sources were loaded separately
    - final_graph_nodes: actual unique nodes in graph after merging
    - cross_merge_rate: % of potential duplicates that were successfully merged

    Also checks for overlap using cross-reference columns (xrefMeSH, xrefDrugbank, etc.)
    when sources use different primary ID schemes.

    Returns:
        metrics: list of metric dicts
        summary: dict with per-node-type breakdown
    """
    metrics: list[dict] = []
    summary: dict[str, dict] = {}

    # Common cross-reference columns to check for overlap
    XREF_COLUMNS = ["xrefMeSH", "xrefDrugbank", "drugbank_id", "mesh_id", "xrefNcbiGene", "symbol", "gene_symbol"]

    # Group node mappings by node type
    node_type_sources: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
    for mapping_key, mapping in mappings.items():
        if mapping.get("data_type") != "node" or mapping.get("skip"):
            continue
        node_type = mapping.get("owl_class") or mapping.get("node_type")
        source_name = mapping_key.split(".")[0]
        if node_type:
            node_type_sources[node_type].append((source_name, mapping_key, mapping))

    # Only analyze node types with multiple sources
    multi_source_types = {nt: sources for nt, sources in node_type_sources.items() if len(sources) > 1}

    for node_type, sources in sorted(multi_source_types.items()):
        source_data: list[dict] = []
        all_ids_per_source: dict[str, set[str]] = {}
        all_xrefs_per_source: dict[str, dict[str, set[str]]] = {}  # source -> {xref_col -> set of values}
        source_dfs: dict[str, pd.DataFrame] = {}

        for source_name, mapping_key, mapping in sources:
            tsv_path = PROCESSED_DIR / source_name / mapping.get("source_filename", "")
            if not tsv_path.exists():
                continue

            try:
                df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
                source_dfs[source_name] = df

                # Get ID column
                id_col = mapping.get("id_column")
                if not id_col and "parse_config" in mapping:
                    id_col = mapping["parse_config"].get("iri_column_name")

                if id_col and id_col in df.columns:
                    ids = set(df[id_col].dropna().astype(str).str.strip())
                    ids = {i for i in ids if i and i != "nan"}
                else:
                    ids = set()

                all_ids_per_source[source_name] = ids

                # Collect cross-reference values
                xrefs: dict[str, set[str]] = {}
                for xref_col in XREF_COLUMNS:
                    # Check both exact and mapped column names
                    prop_map = mapping.get("property_map", {})
                    actual_col = None
                    for src_col, mapped_prop in prop_map.items():
                        if mapped_prop == xref_col or src_col == xref_col:
                            actual_col = src_col
                            break
                    if actual_col is None and xref_col in df.columns:
                        actual_col = xref_col

                    if actual_col and actual_col in df.columns:
                        vals = set(df[actual_col].dropna().astype(str).str.strip())
                        vals = {v for v in vals if v and v != "nan"}
                        if vals:
                            xrefs[xref_col] = vals
                all_xrefs_per_source[source_name] = xrefs

                source_data.append({
                    "source": source_name,
                    "mapping": mapping_key,
                    "raw_records": len(df),
                    "unique_ids": len(ids),
                    "id_column": id_col,
                    "xref_columns": list(xrefs.keys()),
                })
            except Exception:
                continue

        if len(source_data) < 2:
            continue

        # Calculate overlap between sources using primary IDs
        source_names = list(all_ids_per_source.keys())
        overlaps: list[dict] = []
        total_overlap_ids: set[str] = set()

        for i, src1 in enumerate(source_names):
            for src2 in source_names[i + 1:]:
                ids1 = all_ids_per_source[src1]
                ids2 = all_ids_per_source[src2]
                overlap = ids1 & ids2
                if overlap:
                    overlaps.append({
                        "sources": [src1, src2],
                        "overlap_count": len(overlap),
                        "overlap_type": "primary_id",
                        "pct_of_smaller": round(len(overlap) / min(len(ids1), len(ids2)) * 100, 2) if min(len(ids1), len(ids2)) > 0 else 0,
                    })
                    total_overlap_ids.update(overlap)

        # Also check overlap via cross-reference columns
        xref_overlaps: list[dict] = []
        for i, src1 in enumerate(source_names):
            for src2 in source_names[i + 1:]:
                xrefs1 = all_xrefs_per_source.get(src1, {})
                xrefs2 = all_xrefs_per_source.get(src2, {})
                # Find common xref columns
                common_xref_cols = set(xrefs1.keys()) & set(xrefs2.keys())
                for xref_col in common_xref_cols:
                    vals1 = xrefs1[xref_col]
                    vals2 = xrefs2[xref_col]
                    xref_overlap = vals1 & vals2
                    if xref_overlap:
                        xref_overlaps.append({
                            "sources": [src1, src2],
                            "xref_column": xref_col,
                            "overlap_count": len(xref_overlap),
                            "pct_of_smaller": round(len(xref_overlap) / min(len(vals1), len(vals2)) * 100, 2) if min(len(vals1), len(vals2)) > 0 else 0,
                        })

        # Calculate metrics
        sum_unique_per_source = sum(len(ids) for ids in all_ids_per_source.values())
        final_graph_nodes = len(nodes.get(node_type, pd.DataFrame()))

        # Union of all IDs (what we'd expect if IDs were standardized)
        union_all_ids = set()
        for ids in all_ids_per_source.values():
            union_all_ids.update(ids)

        # Estimate potential duplicates from xref overlaps if no primary ID overlap
        estimated_xref_overlap = 0
        if not overlaps and xref_overlaps:
            # Use max xref overlap as estimate
            estimated_xref_overlap = max(o["overlap_count"] for o in xref_overlaps) if xref_overlaps else 0

        # Cross-source merge rate: how much deduplication happened
        potential_duplicates = sum_unique_per_source - len(union_all_ids)
        if potential_duplicates == 0 and estimated_xref_overlap > 0:
            # Sources use different IDs but have xref overlap
            potential_duplicates = estimated_xref_overlap

        # Check how many nodes remain vs expected
        expected_if_merged = sum_unique_per_source - potential_duplicates
        actual_duplicates_remaining = max(0, final_graph_nodes - expected_if_merged)

        if potential_duplicates > 0:
            merged_count = potential_duplicates - actual_duplicates_remaining
            cross_merge_rate = round((merged_count / potential_duplicates) * 100, 2)
        else:
            cross_merge_rate = 100.0

        # Flag if merge rate is low OR if there are xref overlaps but graph has more nodes than expected
        is_flagged = (cross_merge_rate < 90.0 and potential_duplicates > 10) or \
                     (xref_overlaps and final_graph_nodes > expected_if_merged + 10)

        summary[node_type] = {
            "sources": [s["source"] for s in source_data],
            "source_details": source_data,
            "sum_unique_per_source": sum_unique_per_source,
            "union_all_ids": len(union_all_ids),
            "final_graph_nodes": final_graph_nodes,
            "potential_duplicates": potential_duplicates,
            "estimated_xref_overlap": estimated_xref_overlap,
            "cross_merge_rate_pct": cross_merge_rate,
            "overlaps_by_primary_id": overlaps,
            "overlaps_by_xref": xref_overlaps,
            "flagged": is_flagged,
        }

        metrics.append(_metric(
            "Cross-source merge rate", "float", cross_merge_rate,
            tier=1, node_type=node_type,
            sources=[s["source"] for s in source_data],
            sum_unique_per_source=sum_unique_per_source,
            final_graph_nodes=final_graph_nodes,
            potential_duplicates=potential_duplicates,
            xref_overlaps=len(xref_overlaps),
            note="potential duplicate nodes" if is_flagged else None,
        ))

    # Summary metric for flagged types
    flagged_types = [nt for nt, data in summary.items() if data.get("flagged")]
    metrics.append(_metric(
        "Cross-source merge issues", "list", flagged_types,
        tier=2,
        note="node types with low cross-source merge rates (<90%)" if flagged_types else "all multi-source node types merged correctly",
    ))

    return metrics, summary


def compute_tier3_bio_metrics(
    nodes: dict[str, pd.DataFrame],
    edges: dict[str, pd.DataFrame],
    omim_genemap_path: Path | None,
    drugbank_tsv_path: Path | None,
) -> list[dict]:
    metrics: list[dict] = []

    # --- Known disease-gene recall rate ---
    if omim_genemap_path and omim_genemap_path.exists():
        # genemap2.txt: tab-separated, MIM type = 3 are phenotype entries with genes.
        # Columns: Chromosome, Genomic Position Start, ..., MIM Number, Gene Symbols, ...
        omim_df = pd.read_csv(
            omim_genemap_path, sep="\t", comment="#",
            header=None, low_memory=False,
        )
        # Column 12 = Phenotype, Column 5 = Gene Symbols (Entrez-based)
        # Use OMIM's standard column layout; MIM type 3 = confirmed gene-phenotype entries.
        gene_ids_in_graph: set[str] = set()
        if "Gene" in nodes and "xrefNcbiGene" in nodes["Gene"].columns:
            gene_ids_in_graph = set(
                nodes["Gene"]["xrefNcbiGene"].dropna().astype(str).str.strip()
            )
        disease_ids_in_graph: set[str] = set()
        if "Disease" in nodes and "xrefOMIM" in nodes["Disease"].columns:
            disease_ids_in_graph = set(
                nodes["Disease"]["xrefOMIM"].dropna().astype(str).str.strip()
            )

        _pheno_mim_re = re.compile(r"(\d{6})\s*\(\s*3\s*\)")
        total = 0
        recalled = 0
        for _, row in omim_df.iterrows():
            try:
                pheno_field = str(row.iloc[12]) if len(row) > 12 else ""
                disease_mims = _pheno_mim_re.findall(pheno_field)
                if not disease_mims:
                    continue
                entrez_id = str(row.iloc[9]).strip() if len(row) > 9 else ""
                if not entrez_id or entrez_id == "nan":
                    continue
                for mim in disease_mims:
                    total += 1
                    if entrez_id in gene_ids_in_graph and mim in disease_ids_in_graph:
                        recalled += 1
            except Exception:
                continue
        recall_rate = round(recalled / total, 4) if total > 0 else None
        metrics.append(_metric(
            "Known disease-gene recall rate", "float", recall_rate,
            tier=3, total_omim_entries=total, recalled=recalled,
            note="matched by Entrez Gene ID and OMIM phenotype MIM number (type 3)",
        ))
    else:
        metrics.append(_metric(
            "Known disease-gene recall rate", "float", None,
            tier=3, note="provide --omim-genemap to compute",
        ))

    # --- Drug-target coverage ---
    if drugbank_tsv_path and drugbank_tsv_path.exists():
        db_df = pd.read_csv(drugbank_tsv_path, sep="\t", low_memory=False)
        if "drugbank_id" in db_df.columns:
            db_ids = set(db_df["drugbank_id"].dropna().astype(str).str.strip())
            graph_db_ids: set[str] = set()
            if "Drug" in nodes and "xrefDrugbank" in nodes["Drug"].columns:
                graph_db_ids = set(
                    nodes["Drug"]["xrefDrugbank"].dropna().astype(str).str.strip()
                )
            covered = len(db_ids & graph_db_ids)
            coverage = round(covered / len(db_ids), 4) if db_ids else None
            metrics.append(_metric(
                "Drug-target coverage", "float", coverage,
                tier=3, total_drugbank_drugs=len(db_ids), covered=covered,
            ))
    else:
        metrics.append(_metric(
            "Drug-target coverage", "float", None,
            tier=3, note="provide --drugbank-tsv to compute",
        ))

    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compute after-Memgraph-export metrics from nodes_*.csv and edges_*.csv."
    )
    ap.add_argument("--output", metavar="FILE", help="Write JSON to FILE (default: stdout)")
    ap.add_argument(
        "--baseline", metavar="FILE",
        help="Previous run JSON report for run-to-run delta comparison",
    )
    ap.add_argument(
        "--omim-genemap", metavar="FILE",
        help="OMIM genemap2.txt for disease-gene recall rate (Tier 3)",
    )
    ap.add_argument(
        "--drugbank-tsv", metavar="FILE",
        help="DrugBank drugs TSV for drug-target coverage (Tier 3)",
    )
    ap.add_argument(
        "--min-yield", type=float, default=0.10, metavar="FRACTION",
        help="Minimum edge yield threshold as fraction of source TSV rows (default: 0.10 = 10%%)",
    )
    ap.add_argument(
        "--fail-on-low-yield", action="store_true",
        help="Exit with error code 1 if any mapping falls below --min-yield threshold",
    )
    args = ap.parse_args()

    project, mappings = load_configs()
    base_rdf = ROOT / project["ontology"]["base_file"]

    print(f"Loading graph CSVs from {OUTPUT_DIR}", flush=True)
    nodes, edges = load_graph_csvs()

    print(f"Parsing domain/range from {base_rdf}", flush=True)
    domain_range = parse_domain_range(base_rdf) if base_rdf.exists() else {}

    baseline = None
    if args.baseline and Path(args.baseline).exists():
        baseline = json.loads(Path(args.baseline).read_text())

    all_metrics: list[dict] = []
    tier1_metrics, edge_yield_failures = compute_tier1_metrics(
        nodes, edges, domain_range, mappings, min_yield_threshold=args.min_yield
    )
    all_metrics.extend(tier1_metrics)
    current_counts = {
        **{f"nodes_{t}": len(df) for t, df in nodes.items()},
        **{f"edges_{t}": len(df) for t, df in edges.items()},
    }
    all_metrics.extend(compute_tier2_metrics(nodes, edges, baseline, current_counts))
    all_metrics.extend(compute_tier3_bio_metrics(
        nodes, edges,
        Path(args.omim_genemap) if args.omim_genemap else None,
        Path(args.drugbank_tsv) if args.drugbank_tsv else None,
    ))

    # Compute merge rate analysis (within-source)
    print("Computing within-source merge rate analysis...", flush=True)
    merge_metrics, merge_summary = compute_merge_rate_analysis(nodes, mappings)
    all_metrics.extend(merge_metrics)

    # Compute cross-source merge analysis
    print("Computing cross-source merge analysis...", flush=True)
    cross_merge_metrics, cross_merge_summary = compute_cross_source_merge_analysis(nodes, mappings)
    all_metrics.extend(cross_merge_metrics)

    report = {
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "entity_counts": current_counts,
        "merge_rate_analysis": merge_summary,
        "cross_source_merge_analysis": cross_merge_summary,
        "metrics": all_metrics,
    }
    output = json.dumps(report, indent=2, default=str)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Exit with error if there are edge yield failures and --fail-on-low-yield is set
    if edge_yield_failures:
        print(f"\nWARNING: {len(edge_yield_failures)} mapping(s) below {args.min_yield*100:.0f}% yield threshold:", file=sys.stderr)
        for f in edge_yield_failures:
            print(f"  - {f['mapping']}: {f['yield_pct']}% ({f['edge_count']}/{f['source_rows']} rows)", file=sys.stderr)
        if args.fail_on_low_yield:
            print("\nFAILED: --fail-on-low-yield is set. Exiting with error.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
