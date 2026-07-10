"""API stats verification + disease-specific duplicate checks."""
import json, os, urllib.request, urllib.parse, sys
from collections import Counter
from dotenv import load_dotenv
from pathlib import Path
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
USER = os.getenv("MEMGRAPH_USERNAME", "")
PASS = os.getenv("MEMGRAPH_PASSWORD", "")

sys.stdout.reconfigure(line_buffering=True)

print("Connecting to", URI)
driver = GraphDatabase.driver(URI, auth=(USER, PASS))

print("=" * 70)
print("  PART 1: DB vs API /graph-stats COMPARISON")
print("=" * 70)

with driver.session() as s:
    db_nodes = {}
    for rec in s.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"):
        db_nodes[rec["label"]] = rec["cnt"]
    db_rels = {}
    for rec in s.run("MATCH ()-[r]->() RETURN type(r) AS rt, count(r) AS cnt"):
        db_rels[rec["rt"]] = rec["cnt"]

print(f"DB: {sum(db_nodes.values())} nodes ({len(db_nodes)} types), {sum(db_rels.values())} rels ({len(db_rels)} types)")

api_resp = urllib.request.urlopen("http://localhost:5050/api/graph-stats")
api = json.loads(api_resp.read())
print(f"API: {api['total_nodes']} nodes ({api['node_types']} types), {api['total_relationships']} rels ({api['rel_types']} types)")

mismatches = 0
for label, cnt in db_nodes.items():
    if label and label != "_Metadata":
        api_cnt = api["node_counts"].get(label, 0)
        if cnt != api_cnt:
            print(f"  MISMATCH Node {label}: DB={cnt} API={api_cnt}")
            mismatches += 1
for rt, cnt in db_rels.items():
    api_cnt = api["rel_counts"].get(rt, 0)
    if cnt != api_cnt:
        print(f"  MISMATCH Rel {rt}: DB={cnt} API={api_cnt}")
        mismatches += 1
if mismatches == 0:
    print("PASS: All DB counts match API /graph-stats exactly.")

print()
print("=" * 70)
print("  PART 2: DISEASE-SPECIFIC CHECKS (6 diseases)")
print("=" * 70)

diseases = [
    "atrial fibrillation", "heart failure", "hypertension",
    "arrhythmia", "coronary artery disease", "cardiomyopathy",
]

for disease in diseases:
    url = "http://localhost:5050/api/graph?search=" + urllib.parse.quote(disease) + "&limit=200"
    resp = urllib.request.urlopen(url)
    data = json.loads(resp.read())

    edges = data["edges"]
    predicted = [e for e in edges if e["label"] == "predictedTreatsDisease"]
    core = [e for e in edges if e["label"] != "predictedTreatsDisease"]

    edge_keys = [(e["from"], e["to"], e["label"], e.get("source", "")) for e in edges]
    dupes = [(k, c) for k, c in Counter(edge_keys).items() if c > 1]

    pred_keys = [(e["from"], e["to"], e.get("source", "")) for e in predicted]
    pred_dupes = [(k, c) for k, c in Counter(pred_keys).items() if c > 1]

    core_ids = set()
    for e in core:
        core_ids.add(e["from"])
        core_ids.add(e["to"])
    pred_drugs = set(e["from"] for e in predicted)
    overlap = pred_drugs & core_ids

    ok = "PASS" if not dupes and not pred_dupes else "FAIL"
    print(f"\n  {disease.upper()} -- {ok}")
    print(f"    Nodes: {len(data['nodes'])}, Edges: {len(edges)}, Predicted: {len(predicted)}, Core: {len(core)}")
    print(f"    Duplicate edges (any type): {len(dupes)}")
    print(f"    Duplicate predicted pairs: {len(pred_dupes)}")
    print(f"    Pred drugs also in core graph: {len(overlap)}/{len(pred_drugs)}")
    for k, c in dupes[:3]:
        print(f"      DUP: from={k[0]} to={k[1]} label={k[2]} source={k[3]} x{c}")

print()
print("=" * 70)
print("  PART 3: DUPLICATE drugTreatsDisease EDGES IN GRAPH")
print("=" * 70)

with driver.session() as s:
    r = s.run(
        "MATCH (d:Drug)-[r:drugTreatsDisease]->(dis:Disease) "
        "WITH d, dis, r.source AS src, count(r) AS cnt "
        "WHERE cnt > 1 "
        "RETURN d.commonName AS drug, dis.diseaseName AS disease, src, cnt "
        "ORDER BY cnt DESC LIMIT 20"
    )
    rows = list(r)
    if rows:
        print(f"  Found {len(rows)} duplicate drugTreatsDisease pairs:")
        for row in rows:
            print(f"    {row['drug']} -> {row['disease']} (source: {row['src']}) x{row['cnt']}")
    else:
        print("  PASS: No duplicate drugTreatsDisease edges.")

driver.close()
print()
print("=" * 70)
print("  AUDIT COMPLETE")
print("=" * 70)
