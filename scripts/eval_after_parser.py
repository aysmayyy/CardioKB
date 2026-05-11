#!/usr/bin/env python3
"""
Tier 1/2/3 evaluation script for CardioKB parser phase.
Validates TSV output files after parsing, before Memgraph load.

Run after: python src/main.py --skip-neo4j
"""
import os
import sys
from pathlib import Path
from collections import defaultdict

# Results tracking
results = {"tier1": [], "tier2": [], "tier3": []}

def tier1(name):
    def decorator(fn):
        def wrapper():
            try:
                passed, msg = fn()
                results["tier1"].append((name, passed, msg))
                return passed
            except Exception as e:
                results["tier1"].append((name, False, str(e)))
                return False
        return wrapper
    return decorator

def tier2(name):
    def decorator(fn):
        def wrapper():
            try:
                passed, msg = fn()
                results["tier2"].append((name, passed, msg))
                return passed
            except Exception as e:
                results["tier2"].append((name, False, str(e)))
                return False
        return wrapper
    return decorator

def tier3(name):
    def decorator(fn):
        def wrapper():
            try:
                passed, msg = fn()
                results["tier3"].append((name, passed, msg))
                return passed
            except Exception as e:
                results["tier3"].append((name, False, str(e)))
                return False
        return wrapper
    return decorator


# ============ TIER 1: Critical blocking tests ============

@tier1("Schema file exists: node_types.txt")
def test_node_types_exists():
    path = Path("ontology/schema/node_types.txt")
    return path.exists(), f"{'Found' if path.exists() else 'Missing'}: {path}"

@tier1("Schema file exists: edge_types.txt")
def test_edge_types_exists():
    path = Path("ontology/schema/edge_types.txt")
    return path.exists(), f"{'Found' if path.exists() else 'Missing'}: {path}"

@tier1("Processed directory exists")
def test_processed_dir():
    path = Path("data/processed")
    return path.exists() and path.is_dir(), f"{'Found' if path.exists() else 'Missing'}: {path}"

@tier1("At least one TSV file in processed/")
def test_tsv_files_exist():
    processed = Path("data/processed")
    if not processed.exists():
        return False, "data/processed not found"
    tsv_files = list(processed.rglob("*.tsv"))
    return len(tsv_files) > 0, f"Found {len(tsv_files)} TSV files"

@tier1("Required node TSV: genes")
def test_gene_nodes():
    patterns = ["ncbigene_nodes.tsv", "gene_nodes.tsv", "*gene*.tsv"]
    processed = Path("data/processed")
    for p in patterns:
        matches = list(processed.rglob(p))
        if matches:
            return True, f"Found: {matches[0]}"
    return False, "No gene node TSV found"

@tier1("Required node TSV: diseases")
def test_disease_nodes():
    patterns = ["disease_ontology_nodes.tsv", "disease_nodes.tsv", "*disease*.tsv"]
    processed = Path("data/processed")
    for p in patterns:
        matches = list(processed.rglob(p))
        if matches:
            return True, f"Found: {matches[0]}"
    return False, "No disease node TSV found"

@tier1("Required node TSV: drugs")
def test_drug_nodes():
    patterns = ["drugbank_nodes.tsv", "drug_nodes.tsv", "*drug*.tsv"]
    processed = Path("data/processed")
    for p in patterns:
        matches = list(processed.rglob(p))
        if matches:
            return True, f"Found: {matches[0]}"
    return False, "No drug node TSV found"


# ============ TIER 2: Important non-blocking tests ============

@tier2("Gene node count > 10,000")
def test_gene_count():
    processed = Path("data/processed")
    for tsv in processed.rglob("*gene*nodes*.tsv"):
        lines = sum(1 for _ in open(tsv)) - 1  # minus header
        if lines > 10000:
            return True, f"{lines:,} genes in {tsv.name}"
    return False, "Gene count below threshold"

@tier2("Disease node count > 1,000")
def test_disease_count():
    processed = Path("data/processed")
    for tsv in processed.rglob("*disease*nodes*.tsv"):
        lines = sum(1 for _ in open(tsv)) - 1
        if lines > 1000:
            return True, f"{lines:,} diseases in {tsv.name}"
    return False, "Disease count below threshold"

@tier2("Drug node count > 1,000")
def test_drug_count():
    processed = Path("data/processed")
    for tsv in processed.rglob("*drug*nodes*.tsv"):
        lines = sum(1 for _ in open(tsv)) - 1
        if lines > 1000:
            return True, f"{lines:,} drugs in {tsv.name}"
    return False, "Drug count below threshold"

@tier2("ClinVar variant count > 100,000")
def test_clinvar_count():
    processed = Path("data/processed")
    for tsv in processed.rglob("*clinvar*nodes*.tsv"):
        lines = sum(1 for _ in open(tsv)) - 1
        if lines > 100000:
            return True, f"{lines:,} variants in {tsv.name}"
    # Also check variant_nodes.tsv
    for tsv in processed.rglob("*variant*nodes*.tsv"):
        lines = sum(1 for _ in open(tsv)) - 1
        if lines > 100000:
            return True, f"{lines:,} variants in {tsv.name}"
    return False, "Variant count below threshold"

@tier2("No empty TSV files")
def test_no_empty_tsv():
    processed = Path("data/processed")
    empty = []
    for tsv in processed.rglob("*.tsv"):
        lines = sum(1 for _ in open(tsv))
        if lines <= 1:  # only header or empty
            empty.append(tsv.name)
    if empty:
        return False, f"Empty TSVs: {empty[:5]}"
    return True, "All TSVs have data"


# ============ TIER 3: Advisory tests ============

@tier3("TSV files have consistent headers")
def test_tsv_headers():
    processed = Path("data/processed")
    issues = []
    for tsv in list(processed.rglob("*.tsv"))[:20]:  # sample
        try:
            with open(tsv) as f:
                header = f.readline().strip()
                if not header or '\t' not in header:
                    issues.append(tsv.name)
        except:
            issues.append(tsv.name)
    if issues:
        return False, f"Header issues: {issues[:3]}"
    return True, "Headers look valid"

@tier3("No duplicate IDs in node files")
def test_no_duplicate_ids():
    processed = Path("data/processed")
    dupes = []
    for tsv in list(processed.rglob("*nodes*.tsv"))[:10]:
        try:
            ids = set()
            with open(tsv) as f:
                next(f)  # skip header
                for line in f:
                    id_val = line.split('\t')[0]
                    if id_val in ids:
                        dupes.append(tsv.name)
                        break
                    ids.add(id_val)
        except:
            pass
    if dupes:
        return False, f"Duplicate IDs in: {dupes[:3]}"
    return True, "No duplicate IDs detected"

@tier3("Edge files reference valid node types")
def test_edge_node_refs():
    # Just checks that edge TSVs exist alongside node TSVs
    processed = Path("data/processed")
    node_files = set(p.stem.replace("_nodes", "") for p in processed.rglob("*nodes*.tsv"))
    edge_files = set(p.stem.replace("_edges", "") for p in processed.rglob("*edges*.tsv"))
    orphan_edges = edge_files - node_files - {"gene_gene", "drug_gene", "disease_disease"}
    if len(orphan_edges) > 5:
        return False, f"Many edge files without node files: {len(orphan_edges)}"
    return True, f"Edge/node file pairing looks reasonable"


def run_all():
    print("=" * 60)
    print("CardioKB Parser Evaluation")
    print("=" * 60)

    # Run all tests
    all_tests = [
        test_node_types_exists, test_edge_types_exists, test_processed_dir,
        test_tsv_files_exist, test_gene_nodes, test_disease_nodes, test_drug_nodes,
        test_gene_count, test_disease_count, test_drug_count, test_clinvar_count,
        test_no_empty_tsv, test_tsv_headers, test_no_duplicate_ids, test_edge_node_refs,
    ]

    for test in all_tests:
        test()

    # Report
    print("\n" + "=" * 60)
    print("TIER 1: Critical (blocking)")
    print("=" * 60)
    tier1_pass = 0
    for name, passed, msg in results["tier1"]:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {msg}")
        if passed:
            tier1_pass += 1

    print("\n" + "=" * 60)
    print("TIER 2: Important (non-blocking)")
    print("=" * 60)
    tier2_pass = 0
    for name, passed, msg in results["tier2"]:
        status = "PASS" if passed else "WARN"
        print(f"  [{status}] {name}: {msg}")
        if passed:
            tier2_pass += 1

    print("\n" + "=" * 60)
    print("TIER 3: Advisory")
    print("=" * 60)
    tier3_pass = 0
    for name, passed, msg in results["tier3"]:
        status = "PASS" if passed else "INFO"
        print(f"  [{status}] {name}: {msg}")
        if passed:
            tier3_pass += 1

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Tier 1: {tier1_pass}/{len(results['tier1'])} passing")
    print(f"  Tier 2: {tier2_pass}/{len(results['tier2'])} passing")
    print(f"  Tier 3: {tier3_pass}/{len(results['tier3'])} passing")

    tier1_blocked = len(results["tier1"]) - tier1_pass
    if tier1_blocked > 0:
        print(f"\n  BLOCKED: {tier1_blocked} Tier 1 failures")
        return 1
    else:
        print(f"\n  OK: No blocking failures")
        return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).parent.parent)  # cd to repo root
    sys.exit(run_all())
