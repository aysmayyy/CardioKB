#!/usr/bin/env python3
"""Simple edge loader - one file at a time, small batches."""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys

OUT = Path(__file__).parent.parent / "data" / "output"
BATCH_SIZE = 500  # Very small batches

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))

# Get current edge counts
existing = {}
with driver.session() as s:
    result = s.run("MATCH ()-[r]->() RETURN type(r) as t, count(r) as c")
    for rec in result:
        existing[rec["t"]] = rec["c"]
    print(f"Current edges by type: {sum(existing.values()):,} total")

# Process each fixed edge file
for ef in sorted(OUT.glob("fixed_edges_*.csv")):
    rel_type = ef.stem.replace("fixed_edges_", "")

    # Skip if already loaded
    if existing.get(rel_type, 0) > 0:
        print(f"  SKIP {rel_type}: {existing[rel_type]:,} already loaded")
        continue

    df = pd.read_csv(ef)
    total = len(df)
    if total == 0:
        continue

    print(f"  {rel_type}: {total:,} edges...", end=" ", flush=True)

    loaded = 0
    for i in range(0, total, BATCH_SIZE):
        batch = df.iloc[i:i+BATCH_SIZE]
        edges = [[str(r[':START_ID']), str(r[':END_ID'])] for _, r in batch.iterrows()]

        try:
            with driver.session() as s:
                result = s.run(f"""
                    UNWIND $edges AS e
                    MATCH (a {{id: e[0]}})
                    MATCH (b {{id: e[1]}})
                    CREATE (a)-[r:{rel_type}]->(b)
                """, edges=edges)
                summary = result.consume()
                loaded += summary.counters.relationships_created
        except Exception as e:
            print(f"Error at batch {i}: {str(e)[:50]}")
            break

    pct = (loaded / total * 100) if total > 0 else 0
    print(f"{loaded:,} ({pct:.0f}%)")
    sys.stdout.flush()

# Final count
with driver.session() as s:
    total_edges = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    print(f"\nTotal edges in graph: {total_edges:,}")

driver.close()
