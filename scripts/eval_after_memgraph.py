#!/usr/bin/env python3
"""
Tier 1/2/3 evaluation script for CardioKB Memgraph phase.
Validates loaded graph after Memgraph import, including merge rate checking.

Run after: python src/main.py (full pipeline)
"""
import os
import sys
from pathlib import Path
from collections import defaultdict

# Load .env
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

from neo4j import GraphDatabase

# Connect to Memgraph
driver = GraphDatabase.driver(
    os.environ.get('MEMGRAPH_URI', 'bolt://localhost:7687'),
    auth=(os.environ.get('MEMGRAPH_USERNAME', ''), os.environ.get('MEMGRAPH_PASSWORD', ''))
)

def q(cypher, **params):
    with driver.session() as s:
        return [dict(r) for r in s.run(cypher, **params)]

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

@tier1("Memgraph connection")
def test_connection():
    try:
        result = q("RETURN 1 AS n")
        return result[0]['n'] == 1, "Connected to Memgraph"
    except Exception as e:
        return False, str(e)

@tier1("Node count > 100,000")
def test_node_count():
    result = q("MATCH (n) RETURN count(n) AS cnt")[0]['cnt']
    return result > 100000, f"{result:,} nodes"

@tier1("Relationship count > 100,000")
def test_rel_count():
    result = q("MATCH ()-[r]->() RETURN count(r) AS cnt")[0]['cnt']
    return result > 100000, f"{result:,} relationships"

@tier1("Gene nodes exist")
def test_gene_nodes():
    result = q("MATCH (g:Gene) RETURN count(g) AS cnt")[0]['cnt']
    return result > 10000, f"{result:,} Gene nodes"

@tier1("Disease nodes exist")
def test_disease_nodes():
    result = q("MATCH (d:Disease) RETURN count(d) AS cnt")[0]['cnt']
    return result > 1000, f"{result:,} Disease nodes"

@tier1("Drug nodes exist")
def test_drug_nodes():
    result = q("MATCH (d:Drug) RETURN count(d) AS cnt")[0]['cnt']
    return result > 1000, f"{result:,} Drug nodes"

@tier1("At least 15 node types")
def test_node_types():
    result = q("MATCH (n) RETURN DISTINCT labels(n) AS l")
    types = set()
    for r in result:
        for label in r['l']:
            if not label.startswith('_'):
                types.add(label)
    return len(types) >= 15, f"{len(types)} node types: {sorted(types)[:5]}..."

@tier1("At least 20 relationship types")
def test_rel_types():
    result = q("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")
    types = {r['t'] for r in result}
    return len(types) >= 20, f"{len(types)} relationship types"

@tier1("All relationships have source label")
def test_source_labels():
    # Check that relationships have r.source property
    result = q("""
        MATCH ()-[r]->()
        WHERE r.source IS NULL
        RETURN count(r) AS cnt
        LIMIT 1
    """)[0]['cnt']
    return result == 0, f"{result} relationships missing source label"


# ============ TIER 2: Important non-blocking tests ============

@tier2("Source label distribution")
def test_source_distribution():
    result = q("""
        MATCH ()-[r]->()
        WHERE r.source IS NOT NULL
        RETURN r.source AS src, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    sources = {r['src']: r['cnt'] for r in result}
    return len(sources) >= 15, f"{len(sources)} sources: {list(sources.keys())[:5]}..."

@tier2("ClinVar variants > 1M")
def test_clinvar():
    result = q("MATCH (v:Variant) RETURN count(v) AS cnt")[0]['cnt']
    return result > 1000000, f"{result:,} Variant nodes"

@tier2("Gene-Disease edges exist")
def test_gene_disease():
    result = q("""
        MATCH (g:Gene)-[r:geneAssociatesWithDisease]->(d:Disease)
        RETURN count(r) AS cnt
    """)[0]['cnt']
    return result > 10000, f"{result:,} gene-disease edges"

@tier2("Drug-Gene edges exist")
def test_drug_gene():
    result = q("""
        MATCH (d:Drug)-[r]->(g:Gene)
        RETURN count(r) AS cnt
    """)[0]['cnt']
    return result > 10000, f"{result:,} drug-gene edges"

@tier2("Clinical trials exist")
def test_clinical_trials():
    result = q("MATCH (t:ClinicalTrial) RETURN count(t) AS cnt")[0]['cnt']
    return result > 10000, f"{result:,} ClinicalTrial nodes"


# ============ MERGE RATE CHECKING (Tier 2) ============

@tier2("Gene merge rate check")
def test_gene_merge_rate():
    """Check that Gene nodes are properly merged by geneSymbol."""
    # Count genes with same symbol (should be 0 duplicates)
    result = q("""
        MATCH (g:Gene)
        WITH g.geneSymbol AS sym, count(*) AS cnt
        WHERE cnt > 1
        RETURN count(*) AS dupe_symbols, sum(cnt) AS total_dupes
    """)
    if result:
        dupe_symbols = result[0].get('dupe_symbols', 0)
        if dupe_symbols > 0:
            return False, f"{dupe_symbols} gene symbols with duplicates"
    return True, "No duplicate gene symbols"

@tier2("Disease merge rate check")
def test_disease_merge_rate():
    """Check that Disease nodes are properly merged by DOID."""
    result = q("""
        MATCH (d:Disease)
        WITH d.xrefDiseaseOntology AS doid, count(*) AS cnt
        WHERE cnt > 1 AND doid IS NOT NULL
        RETURN count(*) AS dupe_doids, sum(cnt) AS total_dupes
    """)
    if result:
        dupe_doids = result[0].get('dupe_doids', 0)
        if dupe_doids > 0:
            return False, f"{dupe_doids} DOIDs with duplicates"
    return True, "No duplicate DOIDs"

@tier2("Drug merge rate check")
def test_drug_merge_rate():
    """Check that Drug nodes are properly merged by DrugBank ID."""
    result = q("""
        MATCH (d:Drug)
        WITH d.xrefDrugbank AS dbid, count(*) AS cnt
        WHERE cnt > 1 AND dbid IS NOT NULL
        RETURN count(*) AS dupe_dbids, sum(cnt) AS total_dupes
    """)
    if result:
        dupe_dbids = result[0].get('dupe_dbids', 0)
        if dupe_dbids > 10:  # allow some tolerance for CTD-only drugs
            return False, f"{dupe_dbids} DrugBank IDs with duplicates"
    return True, "Drug merge rate acceptable"

@tier2("Variant merge rate check")
def test_variant_merge_rate():
    """Check that Variant nodes are properly merged by variantId."""
    result = q("""
        MATCH (v:Variant)
        WITH v.variantId AS vid, count(*) AS cnt
        WHERE cnt > 1 AND vid IS NOT NULL
        RETURN count(*) AS dupe_vids
        LIMIT 100
    """)
    if result:
        dupe_vids = result[0].get('dupe_vids', 0)
        if dupe_vids > 0:
            return False, f"{dupe_vids} variant IDs with duplicates"
    return True, "No duplicate variant IDs"

@tier2("Cross-database Drug merge (DrugBank + CTD)")
def test_cross_db_drug_merge():
    """
    Check merge rate between DrugBank and CTD Drug nodes.
    CTD drugs should merge with existing DrugBank drugs where possible.
    """
    # Count drugs from each source
    drugbank_count = q("""
        MATCH (d:Drug)
        WHERE d.xrefDrugbank IS NOT NULL
        RETURN count(d) AS cnt
    """)[0]['cnt']

    # Count drugs that have CTD data but no DrugBank ID (CTD-only)
    ctd_only = q("""
        MATCH (d:Drug)-[r]->()
        WHERE r.source = 'CTD' AND d.xrefDrugbank IS NULL
        RETURN count(DISTINCT d) AS cnt
    """)[0]['cnt']

    total_drugs = q("MATCH (d:Drug) RETURN count(d) AS cnt")[0]['cnt']

    # Expected: total ≈ drugbank + ctd_only (not drugbank + all_ctd)
    merge_rate = 1.0 - (ctd_only / max(total_drugs, 1))

    return merge_rate > 0.5, f"Drug merge rate: {merge_rate:.1%} ({ctd_only:,} CTD-only of {total_drugs:,} total)"

@tier2("Cross-database Gene merge (multiple sources)")
def test_cross_db_gene_merge():
    """
    Check that genes from different sources merge properly.
    Genes should merge on geneSymbol across NCBI, STRING, Reactome, etc.
    """
    # Count genes that participate in multiple relationship types (indicates successful merge)
    multi_source_genes = q("""
        MATCH (g:Gene)-[r]->()
        WITH g, collect(DISTINCT r.source) AS sources
        WHERE size(sources) > 2
        RETURN count(g) AS cnt
    """)[0]['cnt']

    total_genes = q("MATCH (g:Gene) RETURN count(g) AS cnt")[0]['cnt']

    # Most genes should have relationships from multiple sources
    merge_rate = multi_source_genes / max(total_genes, 1)

    return merge_rate > 0.1, f"{multi_source_genes:,} genes with 3+ sources ({merge_rate:.1%})"


# ============ TIER 3: Advisory tests ============

@tier3("Disease connectivity")
def test_disease_connectivity():
    """Check that diseases have connections."""
    result = q("""
        MATCH (d:Disease)
        OPTIONAL MATCH (d)-[r]-()
        WITH d, count(r) AS rels
        WHERE rels = 0
        RETURN count(d) AS orphans
    """)[0]['orphans']
    total = q("MATCH (d:Disease) RETURN count(d) AS cnt")[0]['cnt']
    pct = (total - result) / max(total, 1) * 100
    return pct > 50, f"{pct:.1f}% diseases connected ({result} orphans)"

@tier3("Specificity scores computed")
def test_specificity():
    result = q("""
        MATCH (n)
        WHERE n.specificityScore IS NOT NULL
        RETURN count(n) AS cnt
    """)[0]['cnt']
    total = q("MATCH (n) RETURN count(n) AS cnt")[0]['cnt']
    pct = result / max(total, 1) * 100
    return pct > 90, f"{pct:.1f}% nodes have specificityScore"

@tier3("No orphaned node types")
def test_no_orphans():
    result = q("""
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN labels(n)[0] AS label, count(n) AS cnt
        ORDER BY cnt DESC
    """)
    orphan_types = [(r['label'], r['cnt']) for r in result if r['label'] and not r['label'].startswith('_')]
    if orphan_types:
        top = orphan_types[:3]
        return False, f"Orphaned types: {top}"
    return True, "No orphaned node types"

@tier3("Edge type distribution reasonable")
def test_edge_distribution():
    result = q("""
        MATCH ()-[r]->()
        RETURN type(r) AS t, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    types = [(r['t'], r['cnt']) for r in result]
    if len(types) < 20:
        return False, f"Only {len(types)} edge types"
    # Check that no single type dominates excessively
    total = sum(cnt for _, cnt in types)
    top_pct = types[0][1] / total * 100 if total > 0 else 0
    return top_pct < 50, f"Top edge type ({types[0][0]}) is {top_pct:.1f}% of total"

@tier3("Merge rate summary across all node types")
def test_overall_merge_quality():
    """Overall assessment of merge quality across node types."""
    issues = []

    # Check each major node type for potential duplication issues
    checks = [
        ("Gene", "geneSymbol"),
        ("Disease", "xrefDiseaseOntology"),
        ("Drug", "commonName"),
        ("Pathway", "pathwayName"),
        ("Phenotype", "xrefHPO"),
    ]

    for label, prop in checks:
        result = q(f"""
            MATCH (n:{label})
            WHERE n.{prop} IS NOT NULL
            WITH n.{prop} AS val, count(*) AS cnt
            WHERE cnt > 1
            RETURN count(*) AS dupes
        """)
        dupes = result[0]['dupes'] if result else 0
        if dupes > 10:
            issues.append(f"{label}: {dupes} duplicates")

    if issues:
        return False, f"Merge issues: {'; '.join(issues[:3])}"
    return True, "Merge quality looks good across all node types"


def run_all():
    print("=" * 60)
    print("CardioKB Memgraph Evaluation")
    print("=" * 60)

    # Run all tests
    all_tests = [
        # Tier 1
        test_connection, test_node_count, test_rel_count,
        test_gene_nodes, test_disease_nodes, test_drug_nodes,
        test_node_types, test_rel_types, test_source_labels,
        # Tier 2
        test_source_distribution, test_clinvar, test_gene_disease,
        test_drug_gene, test_clinical_trials,
        test_gene_merge_rate, test_disease_merge_rate,
        test_drug_merge_rate, test_variant_merge_rate,
        test_cross_db_drug_merge, test_cross_db_gene_merge,
        # Tier 3
        test_disease_connectivity, test_specificity, test_no_orphans,
        test_edge_distribution, test_overall_merge_quality,
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
    print("TIER 2: Important (non-blocking) + Merge Rate Checks")
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
    print(f"  Tier 2: {tier2_pass}/{len(results['tier2'])} passing (includes merge rate checks)")
    print(f"  Tier 3: {tier3_pass}/{len(results['tier3'])} passing")

    tier1_blocked = len(results["tier1"]) - tier1_pass
    if tier1_blocked > 0:
        print(f"\n  BLOCKED: {tier1_blocked} Tier 1 failures")
        driver.close()
        return 1
    else:
        print(f"\n  OK: No blocking failures")
        driver.close()
        return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).parent.parent)  # cd to repo root
    sys.exit(run_all())
