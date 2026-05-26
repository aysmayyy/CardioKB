#!/usr/bin/env python3
"""
eval_download.py — Validate raw data downloads from source databases.

Checks that source files exist, are recent, and meet minimum size thresholds.

Metrics implemented:
  Tier 1: Source file exists, File size sanity, Download freshness
  Tier 2: File count per source, Compression ratio
  Tier 3: Source version detection, Download timestamps

Usage:
    python eval/eval_download.py
    python eval/eval_download.py --output report.json
    python eval/eval_download.py --max-age-days 30
"""

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from lib.metrics import metric, format_report

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw"

# Minimum expected file sizes (bytes) - files smaller than this are suspicious
MIN_FILE_SIZES = {
    "default": 1000,  # 1KB minimum
    "ncbigene": 50_000_000,  # ~50MB for gene_info
    "string": 100_000_000,  # ~100MB for protein links
    "clinvar": 500_000_000,  # ~500MB for variant summary
    "bgee": 1_000_000_000,  # ~1GB for expression data
}

# Sources that use API and don't have persistent raw files
API_SOURCES = {"clinpgx", "dorothea", "collectri", "opentargets"}

# Expected file patterns per source
EXPECTED_FILES = {
    "ncbigene": ["Homo_sapiens.gene_info.gz", "gene_info.gz", "*.gene_info*"],
    "string": ["9606.protein.links.*.txt.gz", "*.protein.links*"],
    "clinvar": ["variant_summary.txt.gz", "variant_summary*"],
    "drugbank": ["full database.xml", "drugbank*.xml", "*.xml"],
    "reactome": ["NCBI2Reactome_All_Levels.txt", "*Reactome*"],
    "hpo": ["phenotype.hpoa", "genes_to_phenotype.txt", "*.hpoa"],
    "sider": ["meddra_all_se.tsv.gz", "*.tsv.gz"],
    "ctd": ["CTD_chem_gene_ixns.tsv.gz", "*.tsv.gz"],
}


def load_databases_config() -> dict:
    """Load databases.yaml configuration."""
    config_path = CONFIG_DIR / "databases.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text()).get("databases", {})
    return {}


def get_source_dirs() -> list[Path]:
    """Get all source directories in data/raw/."""
    if not RAW_DIR.exists():
        return []
    return sorted([d for d in RAW_DIR.iterdir() if d.is_dir()])


def get_files_in_dir(source_dir: Path) -> list[Path]:
    """Get all files in a source directory (recursive)."""
    files = []
    for f in source_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            files.append(f)
    return files


def check_file_freshness(file_path: Path, max_age_days: int) -> tuple[bool, datetime]:
    """Check if file is within acceptable age. Returns (is_fresh, mtime)."""
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
    return mtime >= cutoff, mtime


def get_file_size_with_compression(file_path: Path) -> tuple[int, int | None]:
    """Get file size and uncompressed size if gzipped. Returns (size, uncompressed_size)."""
    size = file_path.stat().st_size
    uncompressed = None

    if file_path.suffix == ".gz":
        try:
            with gzip.open(file_path, 'rb') as f:
                f.seek(0, 2)
                uncompressed = f.tell()
        except Exception:
            pass

    return size, uncompressed


def eval_source(source_name: str, source_dir: Path, max_age_days: int,
                databases_config: dict) -> list[dict]:
    """Evaluate a single source directory."""
    metrics = []

    # Skip API-only sources
    if source_name in API_SOURCES:
        metrics.append(metric(
            "Source type", "string", "API",
            tier=1, source=source_name,
            note="API source - no persistent raw files expected",
        ))
        return metrics

    files = get_files_in_dir(source_dir)

    # Tier 1: Source files exist
    has_files = len(files) > 0
    metrics.append(metric(
        "Source files exist", "boolean", has_files,
        tier=1, source=source_name,
        file_count=len(files),
        note="BLOCKING — no files found" if not has_files else None,
    ))

    if not has_files:
        return metrics

    # Get total size and find largest/newest files
    total_size = sum(f.stat().st_size for f in files)
    largest_file = max(files, key=lambda f: f.stat().st_size)
    newest_file = max(files, key=lambda f: f.stat().st_mtime)

    # Tier 1: File size sanity
    min_size = MIN_FILE_SIZES.get(source_name, MIN_FILE_SIZES["default"])
    size_ok = total_size >= min_size
    metrics.append(metric(
        "File size sanity", "boolean", size_ok,
        tier=1, source=source_name,
        total_bytes=total_size,
        min_expected=min_size,
        largest_file=largest_file.name,
        note=f"BLOCKING — total size {total_size:,} bytes below minimum {min_size:,}" if not size_ok else None,
    ))

    # Tier 1: Download freshness
    is_fresh, newest_mtime = check_file_freshness(newest_file, max_age_days)
    metrics.append(metric(
        "Download freshness", "boolean", is_fresh,
        tier=1, source=source_name,
        newest_file=newest_file.name,
        newest_mtime=newest_mtime.isoformat(),
        max_age_days=max_age_days,
        note=f"WARNING — files older than {max_age_days} days" if not is_fresh else None,
    ))

    # Tier 2: File count
    metrics.append(metric(
        "File count", "integer", len(files),
        tier=2, source=source_name,
        files=[f.name for f in sorted(files)[:10]],  # List first 10
    ))

    # Tier 2: Compression analysis for .gz files
    gz_files = [f for f in files if f.suffix == ".gz"]
    if gz_files:
        compressed_total = sum(f.stat().st_size for f in gz_files)
        # Sample one file for ratio estimation
        sample_file = max(gz_files, key=lambda f: f.stat().st_size)
        comp_size, uncomp_size = get_file_size_with_compression(sample_file)
        if uncomp_size and comp_size > 0:
            ratio = round(uncomp_size / comp_size, 2)
            metrics.append(metric(
                "Compression ratio", "float", ratio,
                tier=2, source=source_name,
                sample_file=sample_file.name,
                compressed_bytes=comp_size,
                uncompressed_bytes=uncomp_size,
            ))

    # Tier 3: File timestamps
    file_times = []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        file_times.append({
            "file": f.name,
            "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
            "size_mb": round(f.stat().st_size / 1_000_000, 2),
        })
    metrics.append(metric(
        "File timestamps", "list", file_times,
        tier=3, source=source_name,
    ))

    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Validate raw data downloads from source databases."
    )
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write JSON report to FILE (default: stdout)")
    parser.add_argument("--max-age-days", type=int, default=90,
                        help="Maximum age in days for freshness check (default: 90)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code 1 on any Tier 1 failure")
    args = parser.parse_args()

    print(f"Scanning {RAW_DIR}...", flush=True)

    databases_config = load_databases_config()
    source_dirs = get_source_dirs()

    if not source_dirs:
        print(f"WARNING: No source directories found in {RAW_DIR}", file=sys.stderr)

    all_metrics = []
    tier1_failures = []

    for source_dir in source_dirs:
        source_name = source_dir.name
        print(f"  Checking {source_name}...", flush=True)

        source_metrics = eval_source(source_name, source_dir, args.max_age_days,
                                     databases_config)
        all_metrics.extend(source_metrics)

        # Track failures
        for m in source_metrics:
            if m.get("tier") == 1 and m.get("note") and "BLOCKING" in m["note"]:
                tier1_failures.append(m)

    # Summary stats
    sources_checked = len(source_dirs)
    sources_with_files = sum(1 for d in source_dirs
                            if any(get_files_in_dir(d)))
    total_files = sum(len(get_files_in_dir(d)) for d in source_dirs)
    total_size = sum(sum(f.stat().st_size for f in get_files_in_dir(d))
                    for d in source_dirs)

    summary = {
        "sources_checked": sources_checked,
        "sources_with_files": sources_with_files,
        "total_files": total_files,
        "total_size_gb": round(total_size / 1_000_000_000, 2),
        "api_sources_skipped": len(API_SOURCES),
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
    print(f"Sources: {sources_checked} checked, {sources_with_files} with files")
    print(f"Total: {total_files} files, {summary['total_size_gb']} GB")
    print(f"Metrics: {len(all_metrics)}")

    if tier1_failures:
        print(f"\nTier 1 failures: {len(tier1_failures)}")
        for m in tier1_failures:
            print(f"  - {m.get('source')}: {m['name']} - {m.get('note')}")
        if args.strict:
            sys.exit(1)
    else:
        print("All Tier 1 checks passed.")


if __name__ == "__main__":
    main()
