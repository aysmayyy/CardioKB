from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()
uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
pw = os.getenv('NEO4J_PASSWORD', '')
driver = GraphDatabase.driver(uri, auth=('neo4j', pw))

with driver.session() as s:
    # 1. All relationship types with source breakdown
    r = s.run("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, r.source AS source, count(*) AS cnt
        ORDER BY rel_type, cnt DESC
    """)
    print("=== ALL RELATIONSHIPS BY TYPE AND SOURCE ===")
    for rec in r:
        print(f"  {rec['rel_type']} | {rec['source']} | {rec['cnt']:,}")

    # 2. Find relationships with NULL source
    r = s.run("""
        MATCH ()-[r]->() WHERE r.source IS NULL
        RETURN type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    print("\n=== RELATIONSHIPS WITH NULL SOURCE ===")
    for rec in r:
        print(f"  {rec['rel_type']}: {rec['cnt']:,}")

    # 3. Check STUDIES_CONDITION source=None details
    r = s.run("""
        MATCH (t)-[r:STUDIES_CONDITION]->(d) WHERE r.source IS NULL
        RETURN t.trialId AS trial, d.commonName AS disease, labels(t) AS t_labels, labels(d) AS d_labels
        LIMIT 20
    """)
    print("\n=== STUDIES_CONDITION WITH NULL SOURCE (sample) ===")
    for rec in r:
        print(f"  {rec['trial']} -> {rec['disease']} | {rec['t_labels']} -> {rec['d_labels']}")

    # 4. Check if Gene nodes have xrefUniProt property
    r = s.run("MATCH (g:Gene) WHERE g.xrefUniProt IS NOT NULL RETURN count(g) AS cnt")
    print(f"\n=== Gene nodes with xrefUniProt: {r.single()['cnt']:,} ===")

    # 5. Node counts by label
    r = s.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC")
    print("\n=== NODE COUNTS ===")
    for rec in r:
        print(f"  {rec['label']}: {rec['cnt']:,}")

    # 6. Total counts
    r = s.run("MATCH (n) RETURN count(n) AS cnt")
    print(f"\nTotal nodes: {r.single()['cnt']:,}")
    r = s.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
    print(f"Total relationships: {r.single()['cnt']:,}")

    # 7. Check BindingDB relationships details
    r = s.run("""
        MATCH (d:Drug)-[r:chemicalBindsGene]->(g:Gene)
        WHERE r.source = 'BindingDB'
        RETURN count(r) AS cnt,
               count(DISTINCT d) AS drugs,
               count(DISTINCT g) AS genes
    """)
    rec = r.single()
    print(f"\n=== BindingDB: {rec['cnt']:,} rels, {rec['drugs']:,} unique drugs, {rec['genes']:,} unique genes ===")

    # 8. Check GWAS relationships
    r = s.run("""
        MATCH ()-[r:geneAssociatesWithDisease]->()
        WHERE r.source = 'GWAS Catalog'
        RETURN count(r) AS cnt
    """)
    print(f"\n=== GWAS Catalog geneAssociatesWithDisease: {r.single()['cnt']:,} ===")

    # 9. Check for any relationship types with 0 count from specific sources
    r = s.run("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, r.source AS source, count(*) AS cnt
        ORDER BY cnt ASC
        LIMIT 30
    """)
    print("\n=== LOWEST COUNT RELATIONSHIPS ===")
    for rec in r:
        print(f"  {rec['rel_type']} | {rec['source']} | {rec['cnt']:,}")

driver.close()
