#!/usr/bin/env python3
"""
Comprehensive Memgraph reload script.

1. Clears all existing data
2. Creates indexes on all identifier properties
3. Loads all nodes from node CSVs
4. Loads all edges from fixed edge CSVs (pre-resolved IDs)

Prerequisites:
- Run fix_edge_csvs.py first to generate fixed_*.csv files
- Memgraph running on bolt://localhost:7687
"""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys
from typing import Dict, List, Set
import time

OUT = Path(__file__).parent.parent / "data" / "output"

# Connection settings
MEMGRAPH_URI = "bolt://localhost:7687"
MEMGRAPH_USER = ""
MEMGRAPH_PASS = ""

print("=" * 70)
print("CardioKB Memgraph Reload")
print("=" * 70)
sys.stdout.flush()

try:
    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))
    with driver.session() as session:
        result = session.run("RETURN 1")
        result.single()
    print(f"Connected to Memgraph at {MEMGRAPH_URI}")
except Exception as e:
    print(f"ERROR: Cannot connect to Memgraph at {MEMGRAPH_URI}")
    print(f"  {e}")
    print("\nMake sure Memgraph is running:")
    print("  docker run -p 7687:7687 -p 3000:3000 memgraph/memgraph-platform")
    sys.exit(1)

# ============================================================================
# Step 1: Clear all existing data
# ============================================================================
print("\n[Step 1/4] Clearing existing data...")
sys.stdout.flush()

with driver.session() as session:
    # Get current counts
    nodes_before = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
    edges_before = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    print(f"  Before: {nodes_before:,} nodes, {edges_before:,} relationships")

    # Delete all (in batches for large graphs)
    if nodes_before > 0 or edges_before > 0:
        print("  Deleting all nodes and relationships...")
        session.run("MATCH (n) DETACH DELETE n")
        print("  Done.")

# ============================================================================
# Step 2: Create indexes on all identifier properties
# ============================================================================
print("\n[Step 2/4] Creating indexes...")
sys.stdout.flush()

indexes = [
    # Primary indexes
    ("Gene", "id"),
    ("Disease", "id"),
    ("Drug", "id"),
    ("BodyPart", "id"),
    ("Symptom", "id"),
    ("BiologicalProcess", "id"),
    ("MolecularFunction", "id"),
    ("CellularComponent", "id"),
    ("Pathway", "id"),
    ("SideEffect", "id"),
    ("Phenotype", "id"),
    ("GeneFamily", "id"),
    ("PharmacologicClass", "id"),
    ("Variant", "id"),
    ("TranscriptionFactor", "id"),
    ("ClinicalTrial", "id"),
    ("DrugLabel", "id"),

    # xref indexes for multi-property matching
    ("Gene", "geneId"),
    ("Gene", "geneSymbol"),
    ("Gene", "xrefEnsembl"),
    ("Gene", "xrefHGNC"),
    ("Disease", "xrefDiseaseOntology"),
    ("Disease", "xrefUmlsCUI"),
    ("Drug", "xrefDrugBank"),
    ("Drug", "xrefMeSH"),
    ("Drug", "xrefChEMBL"),
    ("BodyPart", "xrefUberon"),
    ("BodyPart", "xrefMeSH"),
    ("Symptom", "xrefMeSH"),
]

with driver.session() as session:
    for label, prop in indexes:
        try:
            session.run(f"CREATE INDEX ON :{label}({prop})")
        except Exception:
            pass  # Index may already exist
    print(f"  Created/verified {len(indexes)} indexes")

# ============================================================================
# Step 3: Load all nodes
# ============================================================================
print("\n[Step 3/4] Loading nodes...")
sys.stdout.flush()

node_files = sorted(OUT.glob("nodes_*.csv"))
total_nodes = 0

for nf in node_files:
    label = nf.stem.replace("nodes_", "")
    df = pd.read_csv(nf)

    if df.empty:
        continue

    # Get columns (excluding :LABEL)
    cols = [c for c in df.columns if c != ":LABEL"]

    # Prepare data for batch insert
    records = df.to_dict('records')

    # Batch load
    batch_size = 5000
    loaded = 0

    with driver.session() as session:
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]

            # Clean up None/NaN values
            clean_batch = []
            for rec in batch:
                clean_rec = {k: (v if pd.notna(v) else None) for k, v in rec.items() if k != ":LABEL"}
                clean_batch.append(clean_rec)

            query = f"""
            UNWIND $batch AS row
            CREATE (n:{label})
            SET n = row
            """
            try:
                result = session.run(query, batch=clean_batch)
                summary = result.consume()
                loaded += summary.counters.nodes_created
            except Exception as e:
                print(f"    Error loading {label}: {str(e)[:60]}")
                break

    total_nodes += loaded
    print(f"  {label}: {loaded:,} nodes")
    sys.stdout.flush()

print(f"  Total nodes loaded: {total_nodes:,}")

# ============================================================================
# Step 4: Load all edges from FIXED files
# ============================================================================
print("\n[Step 4/4] Loading edges from fixed CSVs...")
sys.stdout.flush()

# First verify we have fixed files
fixed_files = sorted(OUT.glob("fixed_edges_*.csv"))
if not fixed_files:
    print("  ERROR: No fixed_edges_*.csv files found!")
    print("  Run scripts/fix_edge_csvs.py first to generate fixed edge files.")
    sys.exit(1)

total_edges = 0
edge_stats = []

# Build node ID lookup for validation (optional)
print("  Building node ID set for validation...")
all_node_ids: Set[str] = set()
with driver.session() as session:
    for label in ["Gene", "Disease", "Drug", "BodyPart", "Symptom",
                  "BiologicalProcess", "MolecularFunction", "CellularComponent",
                  "Pathway", "SideEffect", "Phenotype", "GeneFamily",
                  "PharmacologicClass", "Variant", "TranscriptionFactor",
                  "ClinicalTrial", "DrugLabel"]:
        try:
            result = session.run(f"MATCH (n:{label}) RETURN n.id AS id")
            for rec in result:
                if rec["id"]:
                    all_node_ids.add(rec["id"])
        except:
            pass
print(f"  Found {len(all_node_ids):,} node IDs in graph")

for ef in fixed_files:
    rel_type = ef.stem.replace("fixed_edges_", "")
    df = pd.read_csv(ef)

    if df.empty or ":START_ID" not in df.columns:
        continue

    orig_count = len(df)

    # Validate edges against loaded nodes
    valid_edges = []
    invalid_start = 0
    invalid_end = 0

    for _, row in df.iterrows():
        start_id = str(row[":START_ID"])
        end_id = str(row[":END_ID"])

        if start_id not in all_node_ids:
            invalid_start += 1
            continue
        if end_id not in all_node_ids:
            invalid_end += 1
            continue

        valid_edges.append((start_id, end_id))

    if not valid_edges:
        print(f"  {rel_type}: 0/{orig_count:,} (no valid edges - {invalid_start} bad start, {invalid_end} bad end)")
        continue

    # Batch load edges
    batch_size = 5000
    loaded = 0

    with driver.session() as session:
        for i in range(0, len(valid_edges), batch_size):
            batch = valid_edges[i:i+batch_size]

            query = f"""
            UNWIND $edges AS edge
            MATCH (a {{id: edge[0]}})
            MATCH (b {{id: edge[1]}})
            CREATE (a)-[r:{rel_type}]->(b)
            """
            try:
                result = session.run(query, edges=batch)
                summary = result.consume()
                loaded += summary.counters.relationships_created
            except Exception as e:
                print(f"    Batch error for {rel_type}: {str(e)[:60]}")
                break

    total_edges += loaded
    pct = (loaded / orig_count * 100) if orig_count > 0 else 0
    status = "OK" if pct >= 99 else ("PARTIAL" if pct > 0 else "FAIL")
    print(f"  [{status}] {rel_type}: {loaded:,}/{orig_count:,} ({pct:.1f}%)")
    edge_stats.append((rel_type, loaded, orig_count))
    sys.stdout.flush()

# ============================================================================
# Final Summary
# ============================================================================
print("\n" + "=" * 70)
print("RELOAD COMPLETE")
print("=" * 70)

with driver.session() as session:
    final_nodes = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
    final_edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

    print(f"\nFinal Graph Stats:")
    print(f"  Nodes: {final_nodes:,}")
    print(f"  Relationships: {final_edges:,}")

    # Show counts by label
    print(f"\nNodes by type:")
    result = session.run("""
        CALL db.labels() YIELD label
        CALL {
            WITH label
            MATCH (n) WHERE label IN labels(n)
            RETURN count(n) as cnt
        }
        RETURN label, cnt
        ORDER BY cnt DESC
    """)
    for rec in result:
        print(f"  {rec['label']}: {rec['cnt']:,}")

    print(f"\nRelationships by type:")
    result = session.run("""
        MATCH ()-[r]->()
        RETURN type(r) as rel_type, count(r) as cnt
        ORDER BY cnt DESC
    """)
    for rec in result:
        print(f"  {rec['rel_type']}: {rec['cnt']:,}")

driver.close()
print("\nDone!")
