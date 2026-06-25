"""Store CompGCN predictions in Memgraph alongside Node2Vec and RotatE predictions."""

import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
MEMGRAPH_USER = os.getenv("MEMGRAPH_USERNAME", "")
MEMGRAPH_PASS = os.getenv("MEMGRAPH_PASSWORD", "")

DATA_DIR = Path(__file__).resolve().parent / "data"
NODES_PATH = DATA_DIR / "nodes.tsv"
PREDICTIONS_PATH = DATA_DIR / "compgcn" / "predictions.tsv"


def main():
    meta = {}
    with open(NODES_PATH) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            meta[int(row["int_id"])] = int(row["memgraph_id"])

    predictions = []
    with open(PREDICTIONS_PATH) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            drug_id = int(row["drug_int_id"])
            disease_id = int(row["disease_int_id"])
            if drug_id in meta and disease_id in meta:
                predictions.append({
                    "drug_mgid": meta[drug_id],
                    "disease_mgid": meta[disease_id],
                    "confidence": float(row["confidence"]),
                })

    print(f"Loaded {len(predictions)} CompGCN predictions")

    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))
    try:
        with driver.session() as s:
            r = s.run("MATCH ()-[r:predictedTreatsDisease {source: 'CompGCN_LinkPrediction'}]->() DELETE r RETURN count(r)")
            deleted = r.single()[0]
            if deleted:
                print(f"Cleared {deleted} existing CompGCN predictions")

        total = 0
        for i in range(0, len(predictions), 500):
            chunk = predictions[i:i + 500]
            with driver.session() as s:
                result = s.run(
                    """
                    UNWIND $batch AS row
                    MATCH (d:Drug) WHERE id(d) = row.drug_mgid
                    MATCH (dis:Disease) WHERE id(dis) = row.disease_mgid
                    CREATE (d)-[:predictedTreatsDisease {
                        confidence: row.confidence,
                        source: "CompGCN_LinkPrediction"
                    }]->(dis)
                    RETURN count(*) AS created
                    """,
                    batch=chunk,
                )
                total += result.single()["created"]

        print(f"Stored {total} CompGCN predictedTreatsDisease edges in Memgraph")

        with driver.session() as s:
            r = s.run("""
                MATCH ()-[r:predictedTreatsDisease]->()
                RETURN r.source AS source, count(r) AS cnt
                ORDER BY source
            """)
            print("\nAll predictedTreatsDisease edges:")
            for record in r:
                print(f"  {record['source']}: {record['cnt']}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
