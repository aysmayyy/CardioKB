"""
CardioKB Graph Verification Script

Connects to Neo4j and validates the knowledge graph contents:
- Node counts by label
- Relationship counts by type
- Sample queries for key edge types
- Data quality checks (orphan nodes, missing properties)
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from neo4j import GraphDatabase


def verify_graph(uri: str, username: str, password: str, database: str = "neo4j"):
    """Run all verification checks against the Neo4j graph."""
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        driver.verify_connectivity()
        print("Connected to Neo4j")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    with driver.session() as session:
        print("\n" + "=" * 70)
        print("NODE COUNTS BY LABEL")
        print("=" * 70)

        labels_result = session.run("MATCH (n) RETURN DISTINCT labels(n) AS l")
        all_labels = sorted([r['l'][0] for r in labels_result if r['l']])
        total_nodes = 0
        for label in all_labels:
            count = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt").single()['cnt']
            total_nodes += count
            print(f"  {label:<30} {count:>10,}")
        print(f"  {'TOTAL':<30} {total_nodes:>10,}")

        print("\n" + "=" * 70)
        print("RELATIONSHIP COUNTS BY TYPE")
        print("=" * 70)

        rel_result = session.run(
            "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rt"
        )
        all_rel_types = sorted([r['rt'] for r in rel_result])
        total_rels = 0
        for rel_type in all_rel_types:
            count = session.run(
                f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as cnt"
            ).single()['cnt']
            total_rels += count
            print(f"  {rel_type:<45} {count:>10,}")
        print(f"  {'TOTAL':<45} {total_rels:>10,}")

        # Sample queries
        print("\n" + "=" * 70)
        print("SAMPLE QUERIES")
        print("=" * 70)

        # Gene-Disease associations
        result = session.run(
            "MATCH (g:Gene)-[r:geneAssociatesWithDisease]->(d:Disease) "
            "RETURN g.geneSymbol as gene, d.commonName as disease "
            "LIMIT 5"
        )
        print("\n  Gene-Disease Associations (sample):")
        for record in result:
            print(f"    {record['gene']} -> {record['disease']}")

        # Clinical Trial edges
        result = session.run(
            "MATCH (t:ClinicalTrial)-[r:STUDIES_CONDITION]->(d:Disease) "
            "RETURN t.trialId as trial, d.commonName as disease "
            "LIMIT 5"
        )
        print("\n  Trial-Condition edges (sample):")
        for record in result:
            print(f"    {record['trial']} -> {record['disease']}")

        # Pharmacogenomic edges
        result = session.run(
            "MATCH (g:Gene)-[r:AFFECTS_RESPONSE_TO]->(d:Drug) "
            "RETURN g.geneSymbol as gene, d.commonName as drug, r.evidenceLevel as evidence "
            "LIMIT 5"
        )
        print("\n  Gene-Drug Pharmacogenomic edges (sample):")
        for record in result:
            print(f"    {record['gene']} -> {record['drug']} (evidence: {record['evidence']})")

        # TF-Gene interactions
        result = session.run(
            "MATCH (tf:TranscriptionFactor)-[r:transcriptionFactorInteractsWithGene]->(g:Gene) "
            "RETURN tf.TF as tf, g.geneSymbol as gene "
            "LIMIT 5"
        )
        print("\n  TF-Gene Interactions (sample):")
        for record in result:
            print(f"    {record['tf']} -> {record['gene']}")

        # Data quality checks
        print("\n" + "=" * 70)
        print("DATA QUALITY CHECKS")
        print("=" * 70)

        # Orphan nodes (nodes with no relationships)
        orphan_result = session.run(
            "MATCH (n) WHERE NOT (n)--() "
            "WITH labels(n) as lbls, count(n) as cnt "
            "RETURN lbls, cnt ORDER BY cnt DESC"
        )
        print("\n  Orphan nodes (no relationships):")
        any_orphans = False
        for record in orphan_result:
            any_orphans = True
            print(f"    {record['lbls']}: {record['cnt']:,}")
        if not any_orphans:
            print("    None found")

        # Nodes missing key properties
        for label, prop in [('Gene', 'geneSymbol'), ('Disease', 'commonName'),
                            ('Drug', 'commonName'), ('ClinicalTrial', 'trialId')]:
            count = session.run(
                f"MATCH (n:{label}) WHERE n.{prop} IS NULL RETURN count(n) as cnt"
            ).single()['cnt']
            if count > 0:
                print(f"  WARNING: {count:,} {label} nodes missing {prop}")

        print("\n" + "=" * 70)
        print("VERIFICATION COMPLETE")
        print("=" * 70)

    driver.close()


def main():
    parser = argparse.ArgumentParser(description='Verify CardioKB Neo4j Graph')
    parser.add_argument('--uri', default=os.getenv('NEO4J_URI', 'bolt://localhost:7687'))
    parser.add_argument('--username', default=os.getenv('NEO4J_USERNAME', 'neo4j'))
    parser.add_argument('--password', default=os.getenv('NEO4J_PASSWORD', ''))
    parser.add_argument('--database', default='neo4j')

    args = parser.parse_args()

    if not args.password:
        print("ERROR: Neo4j password required. Set NEO4J_PASSWORD env var or use --password")
        sys.exit(1)

    verify_graph(args.uri, args.username, args.password, args.database)


if __name__ == '__main__':
    main()
