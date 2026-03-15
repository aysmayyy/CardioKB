"""
Compute disease-specificity scores for all nodes in Neo4j.

For each node, specificityScore = 1.0 / (number of distinct Disease nodes it connects to).
A gene connecting to 5 diseases scores 0.2; one connecting to 20,000 scores 0.00005.
Nodes with no Disease connections get a score of 1.0 (maximally specific).
Disease nodes themselves get a score of 0.0 (they ARE diseases, not specific to one).

Runs in batches by node label to stay within Neo4j memory limits.
Called automatically at the end of the main pipeline.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

load_dotenv()

logger = logging.getLogger(__name__)


def compute_specificity(uri=None, username=None, password=None):
    """Compute and store specificityScore on all non-Disease nodes."""
    from datetime import datetime, timezone

    from neo4j import GraphDatabase

    uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = username or os.getenv('NEO4J_USERNAME', 'neo4j')
    password = password or os.getenv('NEO4J_PASSWORD', '')

    if not password:
        logger.error("NEO4J_PASSWORD not set — cannot compute specificity scores")
        return

    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        with driver.session(database='neo4j') as session:
            # Get all node labels
            result = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [r['label'] for r in result]
            logger.info(f"Computing specificityScore for {len(labels)} node labels")

            total_updated = 0

            for label in labels:
                if label == 'Disease':
                    # Disease nodes get 0 — they are diseases, not specific to one
                    res = session.run(
                        f"MATCH (n:`{label}`) "
                        "SET n.specificityScore = 0.0 "
                        "RETURN count(n) AS cnt"
                    )
                    cnt = res.single()['cnt']
                    logger.info(f"  {label}: {cnt} nodes set to 0.0 (self-type)")
                    total_updated += cnt
                    continue

                # For all other labels: batch compute in chunks using APOC-free approach
                # Count disease neighbors per node and set score
                res = session.run(
                    f"MATCH (n:`{label}`) "
                    "OPTIONAL MATCH (n)--(d:Disease) "
                    "WITH n, count(DISTINCT d) AS dc "
                    "SET n.specificityScore = CASE WHEN dc > 0 THEN 1.0 / dc ELSE 1.0 END "
                    "RETURN count(n) AS cnt, "
                    "       avg(CASE WHEN dc > 0 THEN 1.0 / dc ELSE 1.0 END) AS avg_score",
                )
                row = res.single()
                cnt = row['cnt']
                avg = row['avg_score']
                avg_str = f"{avg:.6f}" if avg is not None else "N/A"
                logger.info(f"  {label}: {cnt} nodes, avg specificity {avg_str}")
                total_updated += cnt

            logger.info(f"Specificity scores computed for {total_updated} total nodes")

            # Create index for fast lookups
            try:
                session.run(
                    "CREATE INDEX node_specificity IF NOT EXISTS "
                    "FOR (n:Gene) ON (n.specificityScore)"
                )
            except Exception:
                pass  # Index may already exist or label may not support it

            # Store computation timestamp as metadata node
            timestamp = datetime.now(timezone.utc).isoformat()
            session.run(
                "MERGE (m:_Metadata {key: 'specificityScoreComputed'}) "
                "SET m.timestamp = $ts, m.totalNodes = $total",
                ts=timestamp, total=total_updated,
            )
            logger.info(f"Stored specificity computation timestamp: {timestamp}")

    finally:
        driver.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    )
    compute_specificity()
