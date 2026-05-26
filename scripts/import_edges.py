#!/usr/bin/env python3
"""
Batch import edges into Memgraph from CSV files.

Uses the neo4j driver with batch commits to avoid transaction timeouts.
"""

import csv
import logging
import os
from pathlib import Path
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BATCH_SIZE = 10000
MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
MEMGRAPH_USER = os.getenv("MEMGRAPH_USERNAME", "")
MEMGRAPH_PASS = os.getenv("MEMGRAPH_PASSWORD", "")


def import_edge_file(driver, csv_path: Path, rel_type: str) -> int:
    """Import edges from a CSV file in batches."""
    total = 0
    batch = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_id = row.get(':START_ID', '')
            end_id = row.get(':END_ID', '')
            if start_id and end_id:
                batch.append((start_id, end_id))

            if len(batch) >= BATCH_SIZE:
                total += execute_batch(driver, batch, rel_type)
                batch = []

    if batch:
        total += execute_batch(driver, batch, rel_type)

    return total


def execute_batch(driver, batch, rel_type: str) -> int:
    """Execute a batch of edge inserts."""
    query = f"""
    UNWIND $edges AS edge
    MATCH (start {{id: edge[0]}})
    MATCH (end {{id: edge[1]}})
    CREATE (start)-[r:{rel_type}]->(end)
    """
    with driver.session() as session:
        result = session.run(query, edges=batch)
        summary = result.consume()
        return summary.counters.relationships_created


def main():
    output_dir = Path("data/output")
    edge_files = sorted(output_dir.glob("edges_*.csv"), key=lambda p: p.stat().st_size)

    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS) if MEMGRAPH_USER else None)

    try:
        for csv_path in edge_files:
            rel_type = csv_path.stem.replace("edges_", "")
            logger.info(f"Importing {csv_path.name}...")
            count = import_edge_file(driver, csv_path, rel_type)
            logger.info(f"  Created {count} {rel_type} edges")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
