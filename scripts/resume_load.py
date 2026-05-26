#!/usr/bin/env python3
"""Resume loading: finish Variant nodes + load all edges."""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys

OUT = Path(__file__).parent.parent / "data" / "output"
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))

print("=" * 70)
print("Resume Loading - Finish Variants + Load All Edges")
print("=" * 70)

# Check current state
with driver.session() as s:
    current_nodes = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
    current_variants = s.run("MATCH (n:Variant) RETURN count(n) as c").single()["c"]
    current_edges = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

print(f"Current: {current_nodes:,} nodes ({current_variants:,} Variants), {current_edges:,} edges")

# ============================================================================
# Step 1: Load remaining Variant nodes
# ============================================================================
df_variant = pd.read_csv(OUT / "nodes_Variant.csv")
total_variants = len(df_variant)
print(f"\nVariant CSV has {total_variants:,} nodes, Memgraph has {current_variants:,}")

if current_variants < total_variants:
    print(f"\n[Step 1] Loading remaining {total_variants - current_variants:,} Variant nodes...")

    # Get existing variant IDs
    existing_ids = set()
    with driver.session() as s:
        result = s.run("MATCH (n:Variant) RETURN n.id AS id")
        for rec in result:
            if rec["id"]:
                existing_ids.add(rec["id"])

    # Filter to only missing variants
    missing = df_variant[~df_variant["id"].isin(existing_ids)]
    print(f"  Found {len(missing):,} missing Variant nodes to load")

    if len(missing) > 0:
        records = missing.to_dict('records')
        batch_size = 2000  # Smaller batches
        loaded = 0

        with driver.session() as session:
            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]
                clean_batch = []
                for rec in batch:
                    clean_rec = {k: (v if pd.notna(v) else None) for k, v in rec.items() if k != ":LABEL"}
                    clean_batch.append(clean_rec)

                try:
                    result = session.run("""
                        UNWIND $batch AS row
                        CREATE (n:Variant)
                        SET n = row
                    """, batch=clean_batch)
                    summary = result.consume()
                    loaded += summary.counters.nodes_created

                    if (i // batch_size) % 50 == 0:
                        print(f"    Progress: {loaded:,}/{len(missing):,}")
                        sys.stdout.flush()
                except Exception as e:
                    print(f"    Error at batch {i}: {str(e)[:80]}")
                    break

        print(f"  Loaded {loaded:,} Variant nodes")
else:
    print("  All Variant nodes already loaded")

# ============================================================================
# Step 2: Build node ID set
# ============================================================================
print("\n[Step 2] Building node ID lookup...")
all_node_ids = set()

with driver.session() as s:
    result = s.run("MATCH (n) RETURN n.id AS id")
    for rec in result:
        if rec["id"]:
            all_node_ids.add(rec["id"])

print(f"  Found {len(all_node_ids):,} node IDs")

# ============================================================================
# Step 3: Load all edges
# ============================================================================
print("\n[Step 3] Loading edges from fixed CSVs...")
sys.stdout.flush()

total_edges_loaded = 0

for ef in sorted(OUT.glob("fixed_edges_*.csv")):
    rel_type = ef.stem.replace("fixed_edges_", "")
    df = pd.read_csv(ef)

    if df.empty or ":START_ID" not in df.columns:
        continue

    orig_count = len(df)

    # Filter to valid edges
    valid_edges = []
    for _, row in df.iterrows():
        start_id = str(row[":START_ID"])
        end_id = str(row[":END_ID"])
        if start_id in all_node_ids and end_id in all_node_ids:
            valid_edges.append((start_id, end_id))

    if not valid_edges:
        print(f"  {rel_type}: 0/{orig_count:,} - no valid edges")
        continue

    # Batch load
    batch_size = 5000
    loaded = 0

    with driver.session() as session:
        for i in range(0, len(valid_edges), batch_size):
            batch = valid_edges[i:i+batch_size]
            try:
                result = session.run(f"""
                    UNWIND $edges AS edge
                    MATCH (a {{id: edge[0]}})
                    MATCH (b {{id: edge[1]}})
                    CREATE (a)-[r:{rel_type}]->(b)
                """, edges=batch)
                summary = result.consume()
                loaded += summary.counters.relationships_created
            except Exception as e:
                print(f"    Error: {str(e)[:60]}")
                break

    total_edges_loaded += loaded
    pct = (loaded / orig_count * 100) if orig_count > 0 else 0
    print(f"  {rel_type}: {loaded:,}/{orig_count:,} ({pct:.1f}%)")
    sys.stdout.flush()

# ============================================================================
# Final Summary
# ============================================================================
print("\n" + "=" * 70)
with driver.session() as s:
    final_nodes = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
    final_edges = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

print(f"Final: {final_nodes:,} nodes, {final_edges:,} edges")
print("=" * 70)

driver.close()
