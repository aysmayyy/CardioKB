#!/usr/bin/env python3
"""
Robust edge loader - uses small batches and retries to handle memory pressure.
"""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys
import time

OUT = Path(__file__).parent.parent / "data" / "output"
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))

print("=" * 70)
print("Robust Edge Loader")
print("=" * 70)

# Check current state
with driver.session() as s:
    current_nodes = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
    current_edges = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
print(f"Current: {current_nodes:,} nodes, {current_edges:,} edges\n")

# Build node ID set
print("Building node ID lookup...")
all_node_ids = set()
with driver.session() as s:
    result = s.run("MATCH (n) RETURN n.id AS id")
    for rec in result:
        if rec["id"]:
            all_node_ids.add(rec["id"])
print(f"Found {len(all_node_ids):,} node IDs\n")

# Get existing edges by type to skip already-loaded
print("Checking existing edges by type...")
existing_by_type = {}
with driver.session() as s:
    result = s.run("MATCH ()-[r]->() RETURN type(r) as t, count(r) as c")
    for rec in result:
        existing_by_type[rec["t"]] = rec["c"]
print(f"Found {len(existing_by_type)} relationship types already loaded\n")

# Process each edge file
print("Loading edges...")
total_loaded = 0

for ef in sorted(OUT.glob("fixed_edges_*.csv")):
    rel_type = ef.stem.replace("fixed_edges_", "")

    # Skip if already loaded
    if rel_type in existing_by_type and existing_by_type[rel_type] > 0:
        print(f"  [SKIP] {rel_type}: already has {existing_by_type[rel_type]:,} edges")
        continue

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
            valid_edges.append([start_id, end_id])

    if not valid_edges:
        print(f"  [FAIL] {rel_type}: 0/{orig_count:,} - no valid edges")
        continue

    # Load in very small batches with retries
    batch_size = 1000  # Small batches
    loaded = 0
    failed_batches = 0
    max_retries = 3

    for i in range(0, len(valid_edges), batch_size):
        batch = valid_edges[i:i+batch_size]

        for retry in range(max_retries):
            try:
                with driver.session() as session:
                    result = session.run(f"""
                        UNWIND $edges AS edge
                        MATCH (a {{id: edge[0]}})
                        MATCH (b {{id: edge[1]}})
                        CREATE (a)-[r:{rel_type}]->(b)
                    """, edges=batch)
                    summary = result.consume()
                    loaded += summary.counters.relationships_created
                break  # Success
            except Exception as e:
                if retry < max_retries - 1:
                    time.sleep(1)  # Brief pause before retry
                else:
                    failed_batches += 1
                    # Skip this batch after max retries

        # Progress update every 50 batches
        if (i // batch_size) % 50 == 0 and i > 0:
            print(f"    {rel_type}: {loaded:,}/{len(valid_edges):,}...")
            sys.stdout.flush()

    total_loaded += loaded
    pct = (loaded / orig_count * 100) if orig_count > 0 else 0
    status = "OK" if loaded == len(valid_edges) else "PARTIAL"

    extra = ""
    if failed_batches > 0:
        extra = f" ({failed_batches} batches failed)"

    print(f"  [{status}] {rel_type}: {loaded:,}/{orig_count:,} ({pct:.1f}%){extra}")
    sys.stdout.flush()

# Final summary
print("\n" + "=" * 70)
with driver.session() as s:
    final_nodes = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
    final_edges = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

print(f"Final: {final_nodes:,} nodes, {final_edges:,} edges")
print(f"Loaded this run: {total_loaded:,} edges")
print("=" * 70)

driver.close()
