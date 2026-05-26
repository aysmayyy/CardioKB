#!/usr/bin/env python3
"""
eval_parser.py — Validate parsed TSV files from data source parsers.

Checks TSV structure, record counts, schema conformance, and data quality.

Metrics implemented:
  Tier 1: Source database extraction, TSV structural integrity,
          Extracted record counts, Filter pass rate
  Tier 2: Null/empty field rate, Identifier format validity,
          Property value constraint violations, Schema conformance
  Tier 3: Extraction timestamps

Usage:
    python eval/eval_parser.py
    python eval/eval_parser.py --output report.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from lib.metrics import metric, format_report

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROCESSED_DIR = ROOT / "data" / "processed"

# Regex patterns for identifier validation
IDENTIFIER_PATTERNS: dict[str, str] = {
    "xrefNcbiGene": r"^\d+$",
    "xrefHGNC": r"^HGNC:\d+$",
    "xrefEnsembl": r"^ENSG\d+$",
    "xrefUmlsCUI": r"^C\d{7}$",
    "xrefDiseaseOntology": r"^\d+(\.\d+)?$",
    "xrefDrugbank": r"^DB\d{5}$",
    "xrefMeSH": r"^(D|C)\d+$",
    "xrefDTXSID": r"^DTXSID\d+$",
    "xrefOMIM": r"^\d+(\.\d+)?$",
    "xrefUberon": r"^UBERON:\d+$",
}


def load_configs() -> tuple[dict, dict, dict]:
    """Load configuration files."""
    project = yaml.safe_load((CONFIG_DIR / "project.yaml").read_text())["project"]
    mappings_raw = yaml.safe_load((CONFIG_DIR / "ontology_mappings.yaml").read_text())
    mappings = mappings_raw.get("mappings", mappings_raw)
    mappings = {k: v for k, v in mappings.items() if v is not None}
    databases = yaml.safe_load((CONFIG_DIR / "databases.yaml").read_text())["databases"]
    return project, mappings, databases


def _is_direct_download(db_config: dict) -> bool:
    """True if source fetches from a live API or web download."""
    notes = (db_config or {}).get("notes", "").lower()
    return "github" not in notes


def _count_bad_rows(tsv_path: Path) -> int:
    """Count rows with mismatched field counts."""
    with open(tsv_path, "rb") as fh:
        header = fh.readline()
        expected = len(header.rstrip(b"\n").split(b"\t"))
        bad = sum(
            1 for line in fh
            if line.strip() and len(line.rstrip(b"\n").split(b"\t")) != expected
        )
    return bad


def eval_source(source_name: str, mappings: dict, databases: dict) -> list[dict]:
    """Evaluate all mappings for a single source."""
    metrics = []
    db_config = databases.get(source_name, {})

    # Direct download check
    metrics.append(metric(
        "Direct source download", "boolean",
        _is_direct_download(db_config),
        tier=1, source=source_name,
    ))

    # Get mappings for this source
    source_mappings = {
        k: v for k, v in mappings.items()
        if k.startswith(source_name + ".") and not v.get("skip", False)
    }

    for mapping_key, mapping in source_mappings.items():
        parse_config = mapping.get("parse_config", {})
        tsv_path = PROCESSED_DIR / source_name / mapping.get("source_filename", mapping.get("file", ""))

        # Tier 1: Source database extraction
        tsv_exists = tsv_path.exists()
        df = None
        if tsv_exists:
            try:
                df = pd.read_csv(tsv_path, sep="\t", low_memory=False, on_bad_lines="skip")
            except Exception as exc:
                metrics.append(metric(
                    "Source database extraction", "boolean", False,
                    tier=1, source=source_name, mapping=mapping_key,
                    note=f"read error: {exc}",
                ))
                continue

        extraction_pass = df is not None and len(df) > 0
        metrics.append(metric(
            "Source database extraction", "boolean", extraction_pass,
            tier=1, source=source_name, mapping=mapping_key,
            note="BLOCKING — extraction failed" if not extraction_pass else None,
        ))

        if df is None:
            continue

        # Tier 1: TSV structural integrity
        bad_rows = _count_bad_rows(tsv_path)
        metrics.append(metric(
            "TSV structural integrity", "boolean", bad_rows == 0,
            tier=1, source=source_name, mapping=mapping_key,
            bad_rows=bad_rows if bad_rows > 0 else None,
        ))

        # Tier 1: Extracted record counts
        metrics.append(metric(
            "Extracted record counts", "integer", len(df),
            tier=1, source=source_name, mapping=mapping_key,
        ))

        # Tier 1: Filter pass rate (when filter is configured)
        filter_col = parse_config.get("filter_column")
        filter_val = parse_config.get("filter_value")
        if filter_col and filter_val is not None and filter_col in df.columns:
            filtered = df[df[filter_col].astype(str) == str(filter_val)]
            pass_rate = round(len(filtered) / len(df), 4) if len(df) > 0 else 0
            metrics.append(metric(
                "Filter pass rate", "float", pass_rate,
                tier=1, source=source_name, mapping=mapping_key,
                passed=len(filtered), total=len(df),
            ))

        # Tier 1: Duplication rate (for node mappings)
        if mapping.get("data_type") == "node":
            iri_col = parse_config.get("iri_column_name")
            if iri_col and iri_col in df.columns and len(df) > 0:
                valid_mask = df[iri_col].notna() & (df[iri_col].astype(str).str.strip() != "")
                iri_vals = df.loc[valid_mask, iri_col].astype(str).str.strip()
                dup_count = int(iri_vals.duplicated().sum())
                dup_rate = round(dup_count / len(iri_vals), 4) if len(iri_vals) > 0 else None
                metrics.append(metric(
                    "Duplication rate", "float", dup_rate,
                    tier=1, source=source_name, mapping=mapping_key,
                    duplicate_count=dup_count, id_column=iri_col,
                ))

        # Tier 2: Null/empty field rate per property
        data_property_map = parse_config.get("data_property_map", {})
        for src_col, ont_prop in data_property_map.items():
            if src_col not in df.columns:
                continue
            null_mask = df[src_col].isna() | (df[src_col].astype(str).str.strip() == "")
            null_rate = round(float(null_mask.mean()), 4)
            if null_rate > 0.5:  # Only report if >50% null
                metrics.append(metric(
                    "Null/empty field rate", "float", null_rate,
                    tier=2, source=source_name, mapping=mapping_key,
                    column=src_col, ontology_property=ont_prop,
                ))

        # Tier 2: Identifier format validity
        for src_col, ont_prop in data_property_map.items():
            if ont_prop not in IDENTIFIER_PATTERNS or src_col not in df.columns:
                continue
            pattern = IDENTIFIER_PATTERNS[ont_prop]
            non_null = df[src_col].dropna().astype(str).str.strip()
            non_null = non_null[non_null != ""]
            if len(non_null) == 0:
                continue
            valid_rate = round(float(non_null.str.match(pattern).mean()), 4)
            if valid_rate < 1.0:  # Only report if not all valid
                metrics.append(metric(
                    "Identifier format validity", "float", valid_rate,
                    tier=2, source=source_name, mapping=mapping_key,
                    column=src_col, pattern=pattern,
                ))

        # Tier 2: Property value constraint violations
        violations = 0
        for col in df.columns:
            if df[col].dtype != object:
                continue
            non_null = df[col].dropna().astype(str).str.strip()
            non_null = non_null[non_null != ""]
            if len(non_null) == 0:
                continue
            numeric_mask = non_null.str.match(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
            if numeric_mask.mean() > 0.9:
                violations += int((~numeric_mask).sum())
        if violations > 0:
            metrics.append(metric(
                "Property value constraint violations", "integer", violations,
                tier=2, source=source_name, mapping=mapping_key,
            ))

        # Tier 2: Schema conformance
        required_cols: set[str] = set(data_property_map.keys())
        if mapping.get("data_type") == "node":
            iri_col = parse_config.get("iri_column_name")
            if iri_col:
                required_cols.add(iri_col)
        else:
            for col_key in ("subject_column_name", "object_column_name"):
                col = parse_config.get(col_key)
                if col:
                    required_cols.add(col)
        missing = sorted(required_cols - set(df.columns))
        metrics.append(metric(
            "Schema conformance", "boolean", len(missing) == 0,
            tier=2, source=source_name, mapping=mapping_key,
            missing_columns=missing if missing else None,
        ))

    # Tier 3: Extraction timestamp
    source_dir = PROCESSED_DIR / source_name
    if source_dir.exists():
        tsvs = list(source_dir.glob("*.tsv"))
        if tsvs:
            latest_mtime = max(p.stat().st_mtime for p in tsvs)
            ts = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            metrics.append(metric(
                "Extraction timestamp", "date", ts,
                tier=3, source=source_name,
            ))

    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Validate parsed TSV files from data source parsers."
    )
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write JSON report to FILE (default: stdout)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code 1 on any Tier 1 failure")
    args = parser.parse_args()

    print(f"Loading configuration...", flush=True)
    _, mappings, databases = load_configs()

    sources = sorted({k.split(".")[0] for k in mappings})
    print(f"Found {len(sources)} sources to evaluate", flush=True)

    all_metrics = []
    tier1_failures = []

    for source in sources:
        print(f"  Evaluating {source}...", flush=True)
        source_metrics = eval_source(source, mappings, databases)
        all_metrics.extend(source_metrics)

        for m in source_metrics:
            if m.get("tier") == 1 and m.get("note") and "BLOCKING" in m["note"]:
                tier1_failures.append(m)

    # Summary
    total_records = sum(m["result"] for m in all_metrics
                       if m["name"] == "Extracted record counts")
    sources_with_data = len(set(m.get("source") for m in all_metrics
                               if m["name"] == "Source database extraction" and m["result"]))

    summary = {
        "sources_evaluated": len(sources),
        "sources_with_data": sources_with_data,
        "total_records": total_records,
        "total_mappings": len([m for m in all_metrics
                              if m["name"] == "Source database extraction"]),
    }

    report = format_report(all_metrics, summary=summary)
    output = json.dumps(report, indent=2, default=str)

    if args.output:
        Path(args.output).write_text(output)
        print(f"\nReport written to {args.output}")
    else:
        print(output)

    print(f"\n=== Summary ===")
    print(f"Sources: {len(sources)} evaluated, {sources_with_data} with data")
    print(f"Records: {total_records:,} total")
    print(f"Metrics: {len(all_metrics)}")

    if tier1_failures:
        print(f"\nTier 1 failures: {len(tier1_failures)}")
        for m in tier1_failures[:10]:
            print(f"  - {m.get('source')}.{m.get('mapping', '')}: {m['name']}")
        if args.strict:
            sys.exit(1)
    else:
        print("All Tier 1 checks passed.")


if __name__ == "__main__":
    main()
