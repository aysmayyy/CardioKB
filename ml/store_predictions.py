"""Store CompGCN and RotatE top-10K predictions in Memgraph as predictedTreatsDisease edges."""

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

METHODS = [
    {"name": "CompGCN_XGBoost", "source": "CompGCN_LinkPrediction", "path": DATA_DIR / "compgcn" / "predictions.tsv"},
    {"name": "RotatE_XGBoost", "source": "RotatE_LinkPrediction", "path": DATA_DIR / "rotate" / "predictions.tsv"},
]


def main():
    node_names = {}
    with open(NODES_PATH) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            node_names[int(row["int_id"])] = {"name": row["name"], "label": row["label"]}
    print(f"Loaded node metadata: {len(node_names)} nodes")

    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))
    try:
        # Build name-to-memgraph_id lookup from live graph
        drug_name_to_id = {}
        disease_name_to_id = {}
        with driver.session() as s:
            for rec in s.run("MATCH (d:Drug) RETURN id(d) AS mgid, d.commonName AS name"):
                if rec["name"]:
                    drug_name_to_id[rec["name"]] = rec["mgid"]
            for rec in s.run("MATCH (d:Disease) RETURN id(d) AS mgid, d.diseaseName AS name"):
                if rec["name"]:
                    disease_name_to_id[rec["name"]] = rec["mgid"]
        print(f"Live graph: {len(drug_name_to_id)} Drug nodes, {len(disease_name_to_id)} Disease nodes")

        # Step 1: Check and clear ALL existing predicted edges
        with driver.session() as s:
            r = s.run("""
                MATCH ()-[r:predictedTreatsDisease]->()
                RETURN r.source AS source, count(r) AS cnt
                ORDER BY source
            """)
            records = list(r)
            if records:
                print("\nExisting predictedTreatsDisease edges:")
                for rec in records:
                    print(f"  {rec['source']}: {rec['cnt']}")
            else:
                print("\nNo existing predictedTreatsDisease edges (clean slate)")

        with driver.session() as s:
            r = s.run("MATCH ()-[r:predictedTreatsDisease]->() DELETE r RETURN count(r)")
            deleted = r.single()[0]
            print(f"Cleared {deleted} old predicted edges")

        # Step 2: Load predictions for each method
        for method in METHODS:
            predictions = []
            skipped_drug = set()
            skipped_disease = set()
            with open(method["path"]) as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    drug_name = row["drug_name"]
                    disease_name = row["disease_name"]
                    drug_mgid = drug_name_to_id.get(drug_name)
                    disease_mgid = disease_name_to_id.get(disease_name)
                    if drug_mgid is not None and disease_mgid is not None:
                        predictions.append({
                            "drug_mgid": drug_mgid,
                            "disease_mgid": disease_mgid,
                            "confidence": float(row["confidence"]),
                        })
                    else:
                        if drug_mgid is None:
                            skipped_drug.add(drug_name)
                        if disease_mgid is None:
                            skipped_disease.add(disease_name)

            print(f"\n{method['name']}: {len(predictions)} predictions resolved by name")
            if skipped_drug:
                print(f"  Skipped {len(skipped_drug)} unresolved drugs (e.g. {list(skipped_drug)[:3]})")
            if skipped_disease:
                print(f"  Skipped {len(skipped_disease)} unresolved diseases (e.g. {list(skipped_disease)[:3]})")

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
                            source: $source
                        }]->(dis)
                        RETURN count(*) AS created
                        """,
                        batch=chunk,
                        source=method["source"],
                    )
                    total += result.single()["created"]
                if (i + 500) % 2000 == 0:
                    print(f"  ... {min(i + 500, len(predictions))}/{len(predictions)}")

            print(f"  Stored {total} {method['name']} edges")

        # Step 3: Report final counts
        print("\n" + "=" * 60)
        print("FINAL COUNTS")
        print("=" * 60)

        with driver.session() as s:
            r = s.run("""
                MATCH ()-[r:predictedTreatsDisease]->()
                RETURN r.source AS source, count(r) AS cnt
                ORDER BY source
            """)
            total_pred = 0
            for rec in r:
                print(f"  {rec['source']}: {rec['cnt']}")
                total_pred += rec['cnt']
            print(f"  TOTAL predictedTreatsDisease: {total_pred}")

        with driver.session() as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
            edges = s.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]
            print(f"\n  Total graph nodes: {nodes:,}")
            print(f"  Total graph edges: {edges:,}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
