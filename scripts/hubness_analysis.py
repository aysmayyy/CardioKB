"""Analyze top 100 RotatE + top 100 CompGCN predictions for hubness artifacts."""
import os, sys
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
driver = GraphDatabase.driver(
    os.getenv("MEMGRAPH_URI", "bolt://localhost:7687"),
    auth=(os.getenv("MEMGRAPH_USERNAME", ""), os.getenv("MEMGRAPH_PASSWORD", ""))
)

with driver.session() as s:
    preds = []
    for method in ["RotatE_LinkPrediction", "CompGCN_LinkPrediction"]:
        r = s.run(
            "MATCH (dr:Drug)-[r:predictedTreatsDisease]->(d:Disease) "
            "WHERE r.source = $method "
            "RETURN dr.commonName AS drug, d.diseaseName AS disease, "
            "       r.confidence AS confidence, r.source AS method, id(dr) AS drug_id "
            "ORDER BY r.confidence DESC LIMIT 100",
            method=method,
        )
        for rec in r:
            preds.append(dict(rec))
    print(f"Got {len(preds)} predictions", flush=True)

    drug_ids = list(set(p["drug_id"] for p in preds))
    degree_map = {}
    for did in drug_ids:
        r = s.run("MATCH (d)-[r]-() WHERE id(d) = $did RETURN count(r) AS deg", did=did)
        degree_map[did] = r.single()["deg"]

    curated = defaultdict(set)
    for did in drug_ids:
        r = s.run(
            "MATCH (dr:Drug)-[:drugTreatsDisease]->(d:Disease) "
            "WHERE id(dr) = $did RETURN d.diseaseName AS disease",
            did=did,
        )
        for rec in r:
            curated[did].add(rec["disease"].lower() if rec["disease"] else "")

driver.close()

CATEGORIES = {
    "heart": ["heart", "cardiac", "cardiomyopathy", "myocardial", "coronary", "angina", "ventricular"],
    "vascular": ["vascular", "atherosclerosis", "hypertension", "aneurysm", "peripheral arter", "aortic"],
    "cerebrovascular": ["stroke", "cerebral", "cerebrovascular", "intracranial"],
    "arrhythmia": ["arrhythmia", "atrial fibrillation", "atrial flutter", "tachycardia", "bradycardia", "long qt"],
    "thrombotic": ["thrombosis", "thromboembolism", "embolism", "coagulation"],
    "lipid": ["hypercholesterol", "dyslipidemia", "hyperlipid"],
    "ischemic": ["ischemi", "infarction"],
}

def get_category(name):
    nl = name.lower()
    for cat, terms in CATEGORIES.items():
        if any(t in nl for t in terms):
            return cat
    return "other"

rows = []
for p in preds:
    did = p["drug_id"]
    deg = degree_map.get(did, 0)
    pred_cat = get_category(p["disease"])
    curated_diseases = curated.get(did, set())
    curated_same_cat = any(get_category(cd) == pred_cat for cd in curated_diseases)
    curated_cats = sorted(set(get_category(cd) for cd in curated_diseases)) if curated_diseases else []

    rows.append({
        "drug": p["drug"],
        "disease": p["disease"],
        "method": p["method"].replace("_LinkPrediction", ""),
        "confidence": p["confidence"],
        "degree": deg,
        "curated_n": len(curated_diseases),
        "curated_same_cat": curated_same_cat,
        "curated_cats": ", ".join(curated_cats) if curated_cats else "none",
        "hub": deg > 200,
    })

rows.sort(key=lambda r: -r["degree"])

print(f"\n{'Drug':<35} {'Disease':<28} {'Meth':<7} {'Conf':>6} {'Deg':>5} {'Cur#':>4} {'SameCat':>7} {'Hub':>3} {'CuratedCats'}", flush=True)
print("-" * 150, flush=True)
for r in rows:
    print(f"{r['drug'][:34]:<35} {r['disease'][:27]:<28} {r['method']:<7} {r['confidence']:>6.4f} {r['degree']:>5} {r['curated_n']:>4} {'YES' if r['curated_same_cat'] else 'no':>7} {'***' if r['hub'] else '':>3} {r['curated_cats']}", flush=True)

total = len(rows)
hubs = sum(1 for r in rows if r["hub"])
no_cur = sum(1 for r in rows if r["curated_n"] == 0)
same = sum(1 for r in rows if r["curated_same_cat"])
print(f"\n{'='*60}", flush=True)
print(f"Total predictions analyzed: {total}", flush=True)
print(f"Hub drugs (>200 edges):     {hubs} ({100*hubs/total:.0f}%)", flush=True)
print(f"No curated treats at all:   {no_cur} ({100*no_cur/total:.0f}%)", flush=True)
print(f"Curated in same category:   {same} ({100*same/total:.0f}%)", flush=True)
print(f"Curated but diff category:  {total - no_cur - same}", flush=True)
print(f"\nDegree distribution:", flush=True)
for lo, hi, label in [(0,50,"0-50"), (51,100,"51-100"), (101,200,"101-200"), (201,500,"201-500"), (501,99999,"501+")]:
    ct = sum(1 for r in rows if lo <= r["degree"] <= hi)
    if ct:
        print(f"  Degree {label}: {ct} predictions", flush=True)

# Unique drug count and most frequent
from collections import Counter
drug_counts = Counter(r["drug"] for r in rows)
print(f"\nUnique drugs in top predictions: {len(drug_counts)}", flush=True)
print(f"Most predicted drugs:", flush=True)
for drug, cnt in drug_counts.most_common(10):
    deg = next(r["degree"] for r in rows if r["drug"] == drug)
    print(f"  {drug}: {cnt} predictions (degree {deg})", flush=True)
