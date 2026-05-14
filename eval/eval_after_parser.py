#!/usr/bin/env python3
"""
eval_after_parser.py — CardioKB Post-Parser Evaluation Script

Reads ontology configs from src/ontology_configs.py to discover expected TSV files
and computes all implementable "After Parser" metrics from eval_metrics.md.

Tier 1 (Block Release):
    - Source database extraction    (binary Pass/Fail per TSV)
    - TSV structural integrity      (binary Pass/Fail per TSV)
    - Extracted record counts       (integer per TSV)
    - Filter pass rate              (float, only for configs with filter_column)
    - Duplication rate per ontology (float per TSV)

Tier 2 (Monitor Trends):
    - Null/empty field rate per property            (object: {property -> rate})
    - Identifier format validity rate per namespace  (object: {property -> rate})
    - Property value constraint violations           (integer per TSV)
    - Source schema conformance                      (binary Pass/Fail per TSV)

Tier 3 (Periodic Audit):
    - Extraction timestamp per source               (date, from file mtime)

Usage:
    python eval/eval_after_parser.py
    python eval/eval_after_parser.py --output eval/reports/parser_report.json
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — allow running from any working directory
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
try:
    from ontology_configs import ONTOLOGY_CONFIGS
except ImportError as exc:
    print(f"ERROR: Cannot import ONTOLOGY_CONFIGS from src/ontology_configs.py: {exc}",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Identifier regex patterns keyed by graph property name or raw column name
# ---------------------------------------------------------------------------
IDENTIFIER_PATTERNS: Dict[str, re.Pattern] = {
    # Gene identifiers
    "xrefNcbiGene":         re.compile(r"^\d+$"),
    "GeneID":               re.compile(r"^\d+$"),
    "gene_id":              re.compile(r"^\d+$"),
    "geneSymbol":           re.compile(r"^[A-Za-z][A-Za-z0-9\-\.]+$"),
    "Symbol":               re.compile(r"^[A-Za-z][A-Za-z0-9\-\.]+$"),
    "xrefEnsembl":          re.compile(r"^ENSG\d{11}$"),
    "ensembl_id":           re.compile(r"^ENSG\d{11}$"),
    "xrefHGNC":             re.compile(r"^HGNC:\d+$"),
    # Drug identifiers
    "xrefDrugbank":         re.compile(r"^DB\d{5}$"),
    "drugbank_id":          re.compile(r"^DB\d{5}$"),
    "xrefCasRN":            re.compile(r"^\d+-\d+-\d+$"),
    "xrefDTXSID":           re.compile(r"^DTXSID\d+$"),
    # Disease identifiers
    "xrefDiseaseOntology":  re.compile(r"^DOID:\d+$"),
    "doid":                 re.compile(r"^DOID:\d+$"),
    "disease_id":           re.compile(r"^DOID:\d+$"),
    "xrefUmlsCUI":          re.compile(r"^C\d{7}$"),
    "xrefOMIM":             re.compile(r"^\d{6}$"),
    # Phenotype / HPO
    "hpo_id":               re.compile(r"^HP:\d{7}$"),
    # Variant
    "variantId":            re.compile(r"^\d+$"),
    "variant_id":           re.compile(r"^\d+$"),
    # Pathway (Reactome)
    "pathwayId":            re.compile(r"^R-HSA-\d+$"),
    # Clinical trial
    "trialId":              re.compile(r"^NCT\d{8}$"),
    "trial_id":             re.compile(r"^NCT\d{8}$"),
    # Gene family (HGNC)
    "familyId":             re.compile(r"^\d+$"),
}

# Properties expected to hold numeric values (for constraint violation checks)
NUMERIC_PROPERTIES: set = {
    "xrefNcbiGene", "GeneID", "gene_id", "variantId", "variant_id",
    "positionStart", "positionStop", "position", "numberSubmitters",
    "evidenceCount", "score", "morScore", "combined_score",
}

# ---------------------------------------------------------------------------
# Helper: build a metric dict matching the eval_metrics.md JSON schema
# ---------------------------------------------------------------------------

def make_metric(
    name: str,
    data_type: str,
    tier: int,
    result: Any,
    source: Optional[str] = None,
    mapping: Optional[str] = None,
    note: Optional[str] = None,
    **extra,
) -> Dict:
    m: Dict[str, Any] = {
        "name": name,
        "data_type": data_type,
        "tier": tier,
        "result": result,
    }
    if source is not None:
        m["source"] = source
    if mapping is not None:
        m["mapping"] = mapping
    if note is not None:
        m["note"] = note
    m.update(extra)
    return m


# ---------------------------------------------------------------------------
# Derive TSV path from config key + source_filename
# ---------------------------------------------------------------------------

def get_tsv_path(config_key: str, source_filename: str) -> Path:
    source_name = config_key.split(".")[0]
    return DATA_PROCESSED / source_name / source_filename


# ---------------------------------------------------------------------------
# Safe TSV loader (all columns as str so we don't coerce values)
# ---------------------------------------------------------------------------

def load_tsv_safe(path: Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(
            path, sep="\t", dtype=str,
            keep_default_na=False, low_memory=False,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 1 helpers
# ---------------------------------------------------------------------------

def check_tsv_structural_integrity(path: Path, expected_cols: int) -> Tuple[bool, str]:
    """
    Verify every row in the TSV has exactly expected_cols tab-delimited fields.
    Uses csv.reader to correctly handle RFC-4180 quoted fields that may contain
    embedded newlines or tab characters (e.g., MeSH definition fields).
    Returns (ok, detail_note).
    """
    bad_rows: List[int] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
            for rowno, fields in enumerate(reader, start=1):
                if len(fields) != expected_cols:
                    bad_rows.append(rowno)
                    if len(bad_rows) >= 5:
                        break
        if bad_rows:
            return False, f"Bad field count on rows: {bad_rows} (expected {expected_cols} cols)"
        return True, f"All rows have {expected_cols} columns"
    except Exception as exc:
        return False, f"Read error: {exc}"


def compute_filter_pass_rate(
    df: pd.DataFrame, parse_config: Dict
) -> Optional[float]:
    """
    Fraction of rows where filter_column == filter_value.
    Returns None when no filter is configured.
    """
    filter_col = parse_config.get("filter_column")
    filter_val = parse_config.get("filter_value")
    if not filter_col or filter_val is None:
        return None
    if filter_col not in df.columns:
        return None
    total = len(df)
    if total == 0:
        return 0.0
    passing = int((df[filter_col].astype(str) == str(filter_val)).sum())
    return round(passing / total, 6)


def compute_duplication_rate(df: pd.DataFrame, parse_config: Dict) -> float:
    """
    Fraction of rows sharing the same primary identifier.
    For nodes: uses iri_column_name.
    For relationships: uses (subject_column, object_column) pair.
    """
    iri_col = parse_config.get("iri_column_name")
    subj_col = parse_config.get("subject_column_name")
    obj_col = parse_config.get("object_column_name")

    if iri_col and iri_col in df.columns:
        id_series = df[iri_col].astype(str)
    elif subj_col and obj_col and subj_col in df.columns and obj_col in df.columns:
        id_series = df[subj_col].astype(str) + "|||" + df[obj_col].astype(str)
    else:
        return 0.0

    total = len(id_series)
    if total == 0:
        return 0.0
    duplicates = total - id_series.nunique()
    return round(duplicates / total, 6)


# ---------------------------------------------------------------------------
# Tier 2 helpers
# ---------------------------------------------------------------------------

def compute_null_rates(df: pd.DataFrame, parse_config: Dict) -> Dict[str, float]:
    """Null/empty field rate per data property column."""
    prop_map = parse_config.get("data_property_map", {})
    rates: Dict[str, float] = {}
    total = len(df)
    for col, prop in prop_map.items():
        if col in df.columns and total > 0:
            null_count = int(df[col].eq("").sum() + df[col].isna().sum())
            rates[prop] = round(null_count / total, 6)
    return rates


def compute_identifier_validity(
    df: pd.DataFrame, parse_config: Dict
) -> Dict[str, float]:
    """
    Identifier format validity rate for the primary ID columns.
    Checks iri_column_name (nodes) and subject/object columns (relationships).
    Only reports columns where a known regex pattern exists.
    """
    prop_map = parse_config.get("data_property_map", {})
    results: Dict[str, float] = {}
    total = len(df)
    if total == 0:
        return results

    def _check(col: str, prop_name: str, label: str) -> None:
        pattern = IDENTIFIER_PATTERNS.get(prop_name) or IDENTIFIER_PATTERNS.get(col)
        if pattern is None or col not in df.columns:
            return
        non_empty = df[col][df[col].astype(str).str.strip() != ""]
        if len(non_empty) == 0:
            return
        valid = int(non_empty.astype(str).str.fullmatch(pattern).sum())
        results[label] = round(valid / len(non_empty), 6)

    # Node IRI column
    iri_col = parse_config.get("iri_column_name")
    if iri_col:
        prop_name = prop_map.get(iri_col, iri_col)
        _check(iri_col, prop_name, prop_name)

    # Relationship subject/object columns
    subj_col = parse_config.get("subject_column_name")
    subj_prop = parse_config.get("subject_match_property", subj_col or "")
    if subj_col:
        _check(subj_col, subj_prop, f"subject:{subj_prop}")

    obj_col = parse_config.get("object_column_name")
    obj_prop = parse_config.get("object_match_property", obj_col or "")
    if obj_col:
        _check(obj_col, obj_prop, f"object:{obj_prop}")

    return results


def compute_constraint_violations(df: pd.DataFrame, parse_config: Dict) -> int:
    """
    Count values in numeric-typed property columns that cannot be parsed as numbers.
    Skips empty/null values (those are counted separately by null_rates).
    """
    prop_map = parse_config.get("data_property_map", {})
    violations = 0
    for col, prop in prop_map.items():
        if (prop in NUMERIC_PROPERTIES or col in NUMERIC_PROPERTIES) and col in df.columns:
            non_empty = df[col][df[col].astype(str).str.strip() != ""]
            if len(non_empty) > 0:
                coerced = pd.to_numeric(non_empty, errors="coerce")
                violations += int(coerced.isna().sum())
    return violations


def check_schema_conformance(df: pd.DataFrame, parse_config: Dict) -> Tuple[bool, str]:
    """
    Verify that all columns referenced in parse_config are present in the TSV
    and that primary ID columns are not entirely empty.
    """
    required: set = set()

    iri_col = parse_config.get("iri_column_name")
    if iri_col:
        required.add(iri_col)

    subj_col = parse_config.get("subject_column_name")
    if subj_col:
        required.add(subj_col)

    obj_col = parse_config.get("object_column_name")
    if obj_col:
        required.add(obj_col)

    prop_map = parse_config.get("data_property_map", {})
    required.update(prop_map.keys())

    missing = required - set(df.columns)
    if missing:
        return False, f"Missing columns: {sorted(missing)}"

    # Check primary ID columns are not all-empty
    for col in [iri_col, subj_col, obj_col]:
        if col and col in df.columns:
            if df[col].astype(str).str.strip().eq("").all():
                return False, f"Column '{col}' is entirely empty"

    return True, "OK"


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_eval() -> Dict:
    metrics: List[Dict] = []

    # Track latest mtime per source for Tier 3 timestamps
    source_latest_mtime: Dict[str, float] = {}

    for config_key, config in ONTOLOGY_CONFIGS.items():
        source_name = config_key.split(".")[0]
        source_filename: str = config.get("source_filename", "")
        parse_config: Dict = config.get("parse_config", {})
        is_skipped: bool = config.get("skip", False)

        tsv_path = get_tsv_path(config_key, source_filename)
        tsv_exists = tsv_path.exists()

        skip_note = " [marked skip=True in build]" if is_skipped else ""

        # ── Tier 1: Source database extraction ──────────────────────────────
        metrics.append(make_metric(
            name="Source database extraction",
            data_type="binary",
            tier=1,
            result="Pass" if tsv_exists else "Fail",
            source=source_name,
            mapping=config_key,
            note=f"Expected: {tsv_path}{skip_note}",
        ))

        if not tsv_exists:
            continue  # No further checks possible without the file

        # Update mtime tracking for Tier 3
        mtime = os.path.getmtime(tsv_path)
        if source_name not in source_latest_mtime or mtime > source_latest_mtime[source_name]:
            source_latest_mtime[source_name] = mtime

        # Load the TSV
        df = load_tsv_safe(tsv_path)
        if df is None:
            metrics.append(make_metric(
                name="TSV structural integrity",
                data_type="binary",
                tier=1,
                result="Fail",
                source=source_name,
                mapping=config_key,
                note="pandas failed to read the file",
            ))
            continue

        num_cols = len(df.columns)

        # ── Tier 1: TSV structural integrity ────────────────────────────────
        ok, detail = check_tsv_structural_integrity(tsv_path, num_cols)
        metrics.append(make_metric(
            name="TSV structural integrity",
            data_type="binary",
            tier=1,
            result="Pass" if ok else "Fail",
            source=source_name,
            mapping=config_key,
            note=detail,
        ))

        # ── Tier 1: Extracted record counts ─────────────────────────────────
        metrics.append(make_metric(
            name="Extracted record counts",
            data_type="integer",
            tier=1,
            result=len(df),
            source=source_name,
            mapping=config_key,
        ))

        # ── Tier 1: Filter pass rate ─────────────────────────────────────────
        filter_rate = compute_filter_pass_rate(df, parse_config)
        if filter_rate is not None:
            metrics.append(make_metric(
                name="Filter pass rate",
                data_type="float",
                tier=1,
                result=filter_rate,
                source=source_name,
                mapping=config_key,
                note=(
                    f"filter_column='{parse_config.get('filter_column')}' "
                    f"filter_value='{parse_config.get('filter_value')}'"
                ),
            ))

        # ── Tier 1: Duplication rate per ontology ────────────────────────────
        dup_rate = compute_duplication_rate(df, parse_config)
        metrics.append(make_metric(
            name="Duplication rate per ontology",
            data_type="float",
            tier=1,
            result=dup_rate,
            source=source_name,
            mapping=config_key,
        ))

        # ── Tier 2: Null/empty field rate per property ───────────────────────
        null_rates = compute_null_rates(df, parse_config)
        if null_rates:
            metrics.append(make_metric(
                name="Null/empty field rate per property",
                data_type="object",
                tier=2,
                result=null_rates,
                source=source_name,
                mapping=config_key,
            ))

        # ── Tier 2: Identifier format validity rate per namespace ─────────────
        id_validity = compute_identifier_validity(df, parse_config)
        if id_validity:
            metrics.append(make_metric(
                name="Identifier format validity rate per namespace",
                data_type="object",
                tier=2,
                result=id_validity,
                source=source_name,
                mapping=config_key,
            ))

        # ── Tier 2: Property value constraint violations ──────────────────────
        violations = compute_constraint_violations(df, parse_config)
        metrics.append(make_metric(
            name="Property value constraint violations",
            data_type="integer",
            tier=2,
            result=violations,
            source=source_name,
            mapping=config_key,
        ))

        # ── Tier 2: Source schema conformance ────────────────────────────────
        conforms, conform_note = check_schema_conformance(df, parse_config)
        metrics.append(make_metric(
            name="Source schema conformance",
            data_type="binary",
            tier=2,
            result="Pass" if conforms else "Fail",
            source=source_name,
            mapping=config_key,
            note=conform_note,
        ))

    # ── Tier 3: Extraction timestamp per source ──────────────────────────────
    for source_name, mtime in sorted(source_latest_mtime.items()):
        ts = datetime.datetime.fromtimestamp(
            mtime, tz=datetime.timezone.utc
        ).isoformat()
        metrics.append(make_metric(
            name="Extraction timestamp per source",
            data_type="date",
            tier=3,
            result=ts,
            source=source_name,
            note="Derived from latest TSV file modification time in data/processed/<source>/",
        ))

    return {
        "run_timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(report: Dict) -> None:
    metrics = report["metrics"]
    t1 = [m for m in metrics if m["tier"] == 1]
    t2 = [m for m in metrics if m["tier"] == 2]
    t3 = [m for m in metrics if m["tier"] == 3]

    # Real Tier 1 failures:
    #   - binary Pass/Fail metrics that returned "Fail"
    #   - extracted record counts that are zero (blocking)
    #   - filter pass rate = 0.0 (all rows filtered out — likely over-filtering)
    # NOTE: duplication_rate = 0.0 is GOOD (no duplicates) and is NOT a failure.
    t1_fail_binary = [
        m for m in t1
        if m.get("result") == "Fail"
    ]
    t1_zero_counts = [
        m for m in t1
        if m.get("name") == "Extracted record counts" and m.get("result") == 0
    ]
    t1_zero_filter = [
        m for m in t1
        if m.get("name") == "Filter pass rate" and m.get("result") == 0.0
    ]
    t1_all_failures = t1_fail_binary + t1_zero_counts + t1_zero_filter

    # Separate skipped-source failures (skip=True in build) from real failures
    skipped_fail = [m for m in t1_fail_binary if "skip=True" in (m.get("note") or "")]
    real_fail = [m for m in t1_all_failures if m not in skipped_fail]

    print(f"\n{'='*60}")
    print(f"CardioKB eval_after_parser  —  {report['run_timestamp']}")
    print(f"{'='*60}")
    print(f"  Tier 1 metrics : {len(t1):>5}")
    print(f"    Real failures        : {len(real_fail)}")
    print(f"    Skipped-source Fails : {len(skipped_fail)}  (skip=True, no TSV expected)")
    print(f"    Zero record counts   : {len(t1_zero_counts)}")
    print(f"    Zero filter rates    : {len(t1_zero_filter)}")
    print(f"  Tier 2 metrics : {len(t2):>5}")
    print(f"  Tier 3 metrics : {len(t3):>5}")

    if real_fail:
        print("\nTier 1 REAL FAILURES (investigate):")
        for m in real_fail:
            print(f"  [{m['name']}] {m.get('mapping', m.get('source', ''))}  →  {m['result']}")
            if m.get("note"):
                print(f"    note: {m['note']}")

    # Show schema conformance failures
    t2_schema_fail = [
        m for m in t2
        if m.get("name") == "Source schema conformance" and m.get("result") == "Fail"
    ]
    if t2_schema_fail:
        print("\nTier 2 Schema Conformance FAILURES:")
        for m in t2_schema_fail:
            print(f"  {m.get('mapping', '?')}  →  {m.get('note', '')}")

    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CardioKB post-parser evaluation — computes TSV quality metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Write JSON report to FILE (default: stdout)",
    )
    args = parser.parse_args()

    print("Running CardioKB post-parser evaluation...", file=sys.stderr)
    report = run_eval()

    json_str = json.dumps(report, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str, encoding="utf-8")
        print(f"Report written to {out_path}", file=sys.stderr)
        print_summary(report)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
