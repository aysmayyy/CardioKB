"""
Quick script to compute Hits@1 and Hits@3 for the paper.
Run on HPC (needs ~16GB RAM for graph structure):
    conda run -n cardiokb python ml/compute_hits_1_3.py
"""
import csv, pickle, numpy as np, time, json
from pathlib import Path
from collections import defaultdict

ML_DIR = Path(__file__).parent / "data"

meta = {}
with open(ML_DIR / "nodes.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        meta[int(row["int_id"])] = {"label": row["label"], "name": row["name"]}

drugs = {nid for nid, m in meta.items() if m["label"] == "Drug"}
diseases = {nid for nid, m in meta.items() if m["label"] == "Disease"}

neighbors = defaultdict(set)
degree = defaultdict(int)
with open(ML_DIR / "splits/train_edges.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        s, t = int(row["src"]), int(row["dst"])
        neighbors[s].add(t); neighbors[t].add(s)
        degree[s] += 1; degree[t] += 1

all_existing = set()
for split in ["train", "val", "test"]:
    with open(ML_DIR / f"splits/{split}_edges.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            s, t = int(row["src"]), int(row["dst"])
            if s in drugs and t in diseases: all_existing.add((s, t))
            elif s in diseases and t in drugs: all_existing.add((t, s))

test_pos = []
with open(ML_DIR / "splits/test_edges.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        if row["rel_type"] == "drugTreatsDisease":
            s, t = int(row["src"]), int(row["dst"])
            if s in drugs and t in diseases: test_pos.append((s, t))
            elif s in diseases and t in drugs: test_pos.append((t, s))

print(f"Test pairs: {len(test_pos)}")


def pair_feat(emb_a, emb_b, na, nb):
    h = emb_a * emb_b
    d = np.abs(emb_a - emb_b)
    c = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b) + 1e-8)
    l = np.linalg.norm(emb_a - emb_b)
    na_ = neighbors.get(na, set()); nb_ = neighbors.get(nb, set())
    sh = na_ & nb_; un = len(na_ | nb_)
    j = len(sh) / un if un else 0
    aa = sum(1.0 / np.log(degree[n]) for n in sh if degree.get(n, 1) > 1)
    pa = len(na_) * len(nb_)
    return np.concatenate([h, d, [c, l, len(sh), j, aa, np.log1p(pa),
                           np.log1p(degree.get(na, 0)), np.log1p(degree.get(nb, 0))]])


def run(name, emb_file, model_path):
    data = np.load(emb_file)
    em = {int(data["node_ids"][i]): data["embeddings"][i]
          for i in range(len(data["node_ids"]))}
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    dl = sorted(diseases & set(em.keys()))
    print(f"{name}: {len(dl)} candidate diseases")

    t0 = time.time()
    ranks = []
    for idx, (dr, td) in enumerate(test_pos):
        if dr not in em or td not in em:
            continue
        ts = model.predict_proba(pair_feat(em[dr], em[td], dr, td).reshape(1, -1))[0][1]
        r = 1
        b = []
        for di in dl:
            if di == td or (dr, di) in all_existing:
                continue
            b.append(pair_feat(em[dr], em[di], dr, di))
            if len(b) >= 500:
                r += int(np.sum(model.predict_proba(np.array(b))[:, 1] > ts))
                b = []
        if b:
            r += int(np.sum(model.predict_proba(np.array(b))[:, 1] > ts))
        ranks.append(r)
        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  {idx+1}/{len(test_pos)} ({elapsed:.0f}s)")

    n = len(ranks)
    results = {}
    print(f"\n=== {name} + XGBoost (n={n}) ===")
    for k in [1, 3, 10, 50, 100, 200]:
        h = sum(1 for r in ranks if r <= k)
        results[f"hits@{k}"] = h / n
        print(f"  Hits@{k}: {h/n:.4f} ({h}/{n})")
    results["mrr"] = float(np.mean([1.0 / r for r in ranks]))
    results["median_rank"] = float(np.median(ranks))
    print(f"  MRR: {results['mrr']:.4f}")
    print(f"  MedRank: {results['median_rank']:.1f}")
    return results


compgcn = run("CompGCN",
              ML_DIR / "compgcn/compgcn_embeddings.npz",
              ML_DIR / "compgcn/models/xgboost_model.pkl")
rotate = run("RotatE",
             ML_DIR / "rotate/rotate_embeddings.npz",
             ML_DIR / "rotate/models/xgboost_model.pkl")

out = {"CompGCN_XGBoost": compgcn, "RotatE_XGBoost": rotate}
with open(ML_DIR / "paper_hits_at_k.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\nSaved to {ML_DIR / 'paper_hits_at_k.json'}")
