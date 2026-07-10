"""
CardioKB Graph Integrity Audit
===============================
Connects to Memgraph and checks:
1. Duplicate edges (same src, tgt, type, source property)
2. Node type conflicts (nodes with multiple labels)
3. Dangling edge references (property-based ID mismatches)
4. Orphan nodes (zero relationships)
5. Missing required properties (primary identifiers)
6. Predicted edge integrity (predictedTreatsDisease validation)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

load_dotenv(Path(_project_root) / ".env")


def get_driver():
    uri = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
    username = os.getenv("MEMGRAPH_USERNAME", "")
    password = os.getenv("MEMGRAPH_PASSWORD", "")
    if not password:
        print("ERROR: MEMGRAPH_PASSWORD not set")
        sys.exit(1)
    return GraphDatabase.driver(uri, auth=(username, password))


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def check_duplicate_edges(session):
    """Check for exact duplicate edges: same source, target, type, source property."""
    section("1. DUPLICATE EDGES")

    # Get all relationship types
    result = session.run("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")
    rel_types = [r["t"] for r in result]
    print(f"Checking {len(rel_types)} relationship types...\n")

    total_dupes = 0
    for rt in sorted(rel_types):
        query = f"""
        MATCH (a)-[r:`{rt}`]->(b)
        WITH a, b, type(r) AS rtype, r.source AS src, count(r) AS cnt
        WHERE cnt > 1
        RETURN labels(a)[0] AS srcLabel, labels(b)[0] AS tgtLabel,
               rtype, src, cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        result = session.run(query)
        records = list(result)
        if records:
            for rec in records:
                total_dupes += rec["cnt"] - 1
                print(f"  DUPLICATE: ({rec['srcLabel']})-[{rec['rtype']}]->({rec['tgtLabel']}) "
                      f"source={rec['src']}  count={rec['cnt']}")

    if total_dupes == 0:
        print("  PASS: No duplicate edges found.")
    else:
        print(f"\n  TOTAL EXCESS DUPLICATE EDGES: {total_dupes}")


def check_multi_label_nodes(session):
    """Find nodes with multiple labels (type conflicts)."""
    section("2. NODE TYPE CONFLICTS (multi-label nodes)")

    query = """
    MATCH (n)
    WHERE size(labels(n)) > 1
    RETURN labels(n) AS lbls, count(n) AS cnt
    ORDER BY cnt DESC
    """
    result = session.run(query)
    records = list(result)

    if not records:
        print("  PASS: No nodes with multiple labels.")
    else:
        total = 0
        for rec in records:
            total += rec["cnt"]
            print(f"  CONFLICT: Labels {rec['lbls']}  count={rec['cnt']}")
        print(f"\n  TOTAL MULTI-LABEL NODES: {total}")


def check_orphan_nodes(session):
    """Find nodes with zero relationships."""
    section("4. ORPHAN NODES (zero relationships)")

    query = """
    MATCH (n)
    WHERE NOT (n)--()
    RETURN labels(n)[0] AS label, count(n) AS cnt
    ORDER BY cnt DESC
    """
    result = session.run(query)
    records = list(result)

    if not records:
        print("  PASS: No orphan nodes.")
    else:
        total = 0
        for rec in records:
            total += rec["cnt"]
            print(f"  ORPHAN: {rec['label']}  count={rec['cnt']}")
        print(f"\n  TOTAL ORPHAN NODES: {total}")


def check_missing_properties(session):
    """Check nodes missing their primary identifier property."""
    section("5. MISSING REQUIRED PROPERTIES")

    # Map: label -> required property
    required = {
        "Gene": "geneSymbol",
        "Disease": "diseaseName",
        "Drug": "commonName",
        "Variant": "variantId",
        "ClinicalTrial": "trialId",
        "Pathway": "pathwayId",
        "BodyPart": "bodyPartName",
        "Phenotype": "phenotypeName",
        "SideEffect": "sideEffectName",
        "TranscriptionFactor": "tfSymbol",
        "BiologicalProcess": "processName",
        "MolecularFunction": "functionName",
        "CellularComponent": "componentName",
        "GeneFamily": "familyId",
        "PharmacologicClass": "classId",
        "Symptom": "symptomName",
        "DrugLabel": "labelId",
    }

    any_missing = False
    for label, prop in sorted(required.items()):
        query = f"""
        MATCH (n:`{label}`)
        WHERE n.`{prop}` IS NULL OR n.`{prop}` = ''
        RETURN count(n) AS cnt
        """
        result = session.run(query)
        cnt = result.single()["cnt"]
        if cnt > 0:
            any_missing = True
            print(f"  MISSING: {label} nodes without '{prop}': {cnt}")

            # Show a few examples
            ex_query = f"""
            MATCH (n:`{label}`)
            WHERE n.`{prop}` IS NULL OR n.`{prop}` = ''
            RETURN properties(n) AS props
            LIMIT 3
            """
            examples = list(session.run(ex_query))
            for ex in examples:
                # Truncate long property values
                props = {k: (str(v)[:80] if len(str(v)) > 80 else v)
                         for k, v in ex["props"].items()}
                print(f"           Example: {props}")

    if not any_missing:
        print("  PASS: All nodes have their required primary identifier.")


def check_predicted_edges(session):
    """Verify predictedTreatsDisease edge integrity."""
    section("6. PREDICTED EDGE INTEGRITY (predictedTreatsDisease)")

    # Total count
    result = session.run(
        "MATCH ()-[r:predictedTreatsDisease]->() RETURN count(r) AS cnt"
    )
    total = result.single()["cnt"]
    print(f"  Total predictedTreatsDisease edges: {total}")

    if total == 0:
        print("  SKIP: No predicted edges to validate.")
        return

    # Check source node is Drug
    result = session.run("""
    MATCH (a)-[r:predictedTreatsDisease]->(b)
    WHERE NOT 'Drug' IN labels(a)
    RETURN labels(a) AS lbls, count(r) AS cnt
    """)
    records = list(result)
    if records and any(r["cnt"] > 0 for r in records):
        for rec in records:
            print(f"  FAIL: Source not Drug: labels={rec['lbls']}  count={rec['cnt']}")
    else:
        print("  PASS: All source nodes are Drug.")

    # Check target node is Disease
    result = session.run("""
    MATCH (a)-[r:predictedTreatsDisease]->(b)
    WHERE NOT 'Disease' IN labels(b)
    RETURN labels(b) AS lbls, count(r) AS cnt
    """)
    records = list(result)
    if records and any(r["cnt"] > 0 for r in records):
        for rec in records:
            print(f"  FAIL: Target not Disease: labels={rec['lbls']}  count={rec['cnt']}")
    else:
        print("  PASS: All target nodes are Disease.")

    # Check confidence property
    result = session.run("""
    MATCH ()-[r:predictedTreatsDisease]->()
    WHERE r.confidence IS NULL
    RETURN count(r) AS cnt
    """)
    cnt = result.single()["cnt"]
    if cnt > 0:
        print(f"  FAIL: {cnt} edges missing 'confidence' property.")
    else:
        print("  PASS: All edges have 'confidence' property.")

    # Check source property
    result = session.run("""
    MATCH ()-[r:predictedTreatsDisease]->()
    WHERE r.source IS NULL
    RETURN count(r) AS cnt
    """)
    cnt = result.single()["cnt"]
    if cnt > 0:
        print(f"  FAIL: {cnt} edges missing 'source' property.")
    else:
        print("  PASS: All edges have 'source' property.")

    # Show source breakdown
    result = session.run("""
    MATCH ()-[r:predictedTreatsDisease]->()
    RETURN r.source AS src, count(r) AS cnt
    ORDER BY cnt DESC
    """)
    print("  Source breakdown:")
    for rec in result:
        print(f"    {rec['src']}: {rec['cnt']}")


def check_dangling_references(session):
    """Check for property-based ID references that don't match any node."""
    section("3. DANGLING EDGE REFERENCES (property ID mismatches)")

    checks = [
        # Edges with xref properties that should match node IDs
        ("drugBindsGene edges where gene doesn't exist",
         """
         MATCH (d)-[r:drugBindsGene]->(g)
         WHERE g.geneSymbol IS NULL
         RETURN count(r) AS cnt
         """),
        ("drugTreatsDisease edges where disease has no name",
         """
         MATCH (d)-[r:drugTreatsDisease]->(dis)
         WHERE dis.diseaseName IS NULL
         RETURN count(r) AS cnt
         """),
        ("geneAssociatesWithDisease edges where gene has no symbol",
         """
         MATCH (g)-[r:geneAssociatesWithDisease]->(d)
         WHERE g.geneSymbol IS NULL
         RETURN count(r) AS cnt
         """),
    ]

    any_issues = False
    for desc, query in checks:
        result = session.run(query)
        cnt = result.single()["cnt"]
        if cnt > 0:
            any_issues = True
            print(f"  ISSUE: {desc}: {cnt}")
        else:
            print(f"  PASS: {desc}: 0")

    if not any_issues:
        print("\n  All checked references are valid.")


def main():
    print("CardioKB Graph Integrity Audit")
    print(f"{'='*70}")

    driver = get_driver()

    try:
        with driver.session() as session:
            # Quick stats
            result = session.run("MATCH (n) RETURN count(n) AS nodes")
            nodes = result.single()["nodes"]
            result = session.run("MATCH ()-[r]->() RETURN count(r) AS rels")
            rels = result.single()["rels"]
            print(f"Graph: {nodes:,} nodes, {rels:,} relationships")

            check_duplicate_edges(session)
            check_multi_label_nodes(session)
            check_dangling_references(session)
            check_orphan_nodes(session)
            check_missing_properties(session)
            check_predicted_edges(session)

            section("AUDIT COMPLETE")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
