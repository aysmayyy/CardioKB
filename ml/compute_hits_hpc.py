"""
Compute Hits@1, Hits@3, Hits@10 (and all ranking metrics) for the paper.
Vectorized: builds disease embedding matrix and scores all diseases per drug
in one batch. Runs each method separately to keep peak memory low.

HPC layout: ~/cardiokb_score/data/

Run:  sbatch --mem=32G --time=04:00:00 --job-name=hits_k --output=hits_k_%j.out \
        --wrap="conda run -n cardiokb_ml python ~/compute_hits_hpc.py"
"""
import csv, gc, pickle, sys, logging, time, json, os
import numpy as np
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    stream=sys.stdout)
sys.stdout.reconfigure(line_buffering=True)
log = logging.getLogger(__name__)

HOME = Path(os.path.expanduser("~"))
SCORE_DIR = HOME / "cardiokb_score" / "data"
SPLIT_DIR = SCORE_DIR / "splits"


def mem_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 0


# ── Load node metadata (labels only, not names) ──
log.info("Loading node metadata...")
node_labels = {}
with open(SCORE_DIR / "nodes.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        node_labels[int(row["int_id"])] = row["label"]

drugs = {nid for nid, l in node_labels.items() if l == "Drug"}
diseases = {nid for nid, l in node_labels.items() if l == "Disease"}
log.info(f"{len(drugs)} drugs, {len(diseases)} diseases [{mem_mb()} MB]")
del node_labels
gc.collect()

# ── Graph topology (degrees + neighbor counts for graph features) ──
log.info("Building graph topology...")
degree = defaultdict(int)
neighbor_count = {}
drug_disease_relevant = drugs | diseases

nb_sets = defaultdict(set)
with open(SPLIT_DIR / "train_edges.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        s, d = int(row["src"]), int(row["dst"])
        degree[s] += 1
        degree[d] += 1
        if s in drug_disease_relevant:
            nb_sets[s].add(d)
        if d in drug_disease_relevant:
            nb_sets[d].add(s)

# Pre-compute shared neighbor counts and Adamic-Adar for all drug-disease pairs
# is too expensive. Instead, keep neighbor sets only for drugs in test set and
# compute on the fly — but vectorize the embedding part.
log.info(f"Graph built: {len(degree)} nodes with degree [{mem_mb()} MB]")

# ── Existing drug-disease edges ──
all_existing = set()
for split in ["train", "val", "test"]:
    with open(SPLIT_DIR / f"{split}_edges.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            s, d = int(row["src"]), int(row["dst"])
            if s in drugs and d in diseases:
                all_existing.add((s, d))
            elif s in diseases and d in drugs:
                all_existing.add((d, s))

# Per-drug existing diseases (for fast filtering)
drug_existing = defaultdict(set)
for dr, di in all_existing:
    drug_existing[dr].add(di)

# ── Test positives ──
test_pos = []
with open(SPLIT_DIR / "test_edges.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        if row["rel_type"] == "drugTreatsDisease":
            s, d = int(row["src"]), int(row["dst"])
            if s in drugs and d in diseases:
                test_pos.append((s, d))
            elif s in diseases and d in drugs:
                test_pos.append((d, s))

log.info(f"Test pairs: {len(test_pos)}, existing edges: {len(all_existing)} [{mem_mb()} MB]")


def compute_graph_features(na, nb):
    """Compute the 8 graph-structural features for a pair."""
    na_set = nb_sets.get(na, set())
    nb_set = nb_sets.get(nb, set())
    shared = na_set & nb_set
    union_sz = len(na_set | nb_set)
    jaccard = len(shared) / union_sz if union_sz > 0 else 0.0
    aa = sum(1.0 / np.log(degree[n]) for n in shared if degree.get(n, 1) > 1)
    pa = len(na_set) * len(nb_set)
    return np.array([len(shared), jaccard, aa, np.log1p(pa),
                     np.log1p(degree.get(na, 0)), np.log1p(degree.get(nb, 0))],
                    dtype=np.float32)


def compute_embedding_features_batch(drug_emb, disease_emb_matrix):
    """Vectorized embedding features: drug (dim,) vs diseases (N, dim) -> (N, 2*dim+2)."""
    drug_row = drug_emb.reshape(1, -1)  # (1, dim)
    hadamard = drug_row * disease_emb_matrix  # (N, dim)
    diff = np.abs(drug_row - disease_emb_matrix)  # (N, dim)
    dot = np.sum(drug_row * disease_emb_matrix, axis=1)  # (N,)
    norm_a = np.linalg.norm(drug_emb) + 1e-8
    norms_b = np.linalg.norm(disease_emb_matrix, axis=1) + 1e-8  # (N,)
    cosine = dot / (norm_a * norms_b)  # (N,)
    l2 = np.linalg.norm(drug_row - disease_emb_matrix, axis=1)  # (N,)
    return np.hstack([hadamard, diff, cosine.reshape(-1, 1), l2.reshape(-1, 1)])  # (N, 2*dim+2)


def run(name, emb_file, model_path):
    log.info(f"\n{'='*60}")
    log.info(f"{name}: loading embeddings from {emb_file}")
    data = np.load(emb_file)
    node_ids = data["node_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    em = {int(node_ids[i]): embeddings[i] for i in range(len(node_ids))}
    del data, node_ids, embeddings
    gc.collect()

    log.info(f"{name}: loading model from {model_path}")
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    scaler_path = model_path.parent / "xgboost_scaler.pkl"
    log.info(f"{name}: loading scaler from {scaler_path}")
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    # Build disease embedding matrix
    disease_list = sorted(diseases & set(em.keys()))
    disease_idx = {d: i for i, d in enumerate(disease_list)}
    dim = len(next(iter(em.values())))
    disease_matrix = np.zeros((len(disease_list), dim), dtype=np.float32)
    for i, d in enumerate(disease_list):
        disease_matrix[i] = em[d]

    # Pre-compute graph features for all diseases (drug-side features added per drug)
    disease_degree_features = np.array(
        [np.log1p(degree.get(d, 0)) for d in disease_list], dtype=np.float32)

    log.info(f"{name}: {len(em)} embeddings, {len(disease_list)} candidate diseases, dim={dim} [{mem_mb()} MB]")

    # Feature dimension: 2*dim (hadamard+diff) + 2 (cosine+l2) + 6 (graph features)
    feat_dim = 2 * dim + 2 + 6

    t0 = time.time()
    ranks = []
    skipped = 0
    for idx, (dr, td) in enumerate(test_pos):
        if dr not in em or td not in em:
            skipped += 1
            continue

        drug_emb = em[dr]
        existing_for_drug = drug_existing.get(dr, set())

        # Candidate mask: exclude true disease and existing edges
        mask = np.ones(len(disease_list), dtype=bool)
        td_idx_val = disease_idx.get(td)
        if td_idx_val is not None:
            mask[td_idx_val] = False
        for ex_d in existing_for_drug:
            ex_idx = disease_idx.get(ex_d)
            if ex_idx is not None:
                mask[ex_idx] = False

        candidate_ids = [disease_list[i] for i in range(len(disease_list)) if mask[i]]
        candidate_matrix = disease_matrix[mask]

        if len(candidate_ids) == 0:
            ranks.append(1)
            continue

        # Score true pair
        true_emb_feats = compute_embedding_features_batch(drug_emb, em[td].reshape(1, -1))
        true_graph_feats = compute_graph_features(dr, td).reshape(1, -1)
        true_feat = np.hstack([true_emb_feats, true_graph_feats]).astype(np.float32)
        true_score = model.predict_proba(scaler.transform(true_feat))[0][1]

        # Score all candidates in batches (vectorized embedding features)
        emb_feats = compute_embedding_features_batch(drug_emb, candidate_matrix)

        # Graph features per candidate (not vectorizable, but fast with simple lookups)
        drug_nb = nb_sets.get(dr, set())
        drug_deg = np.log1p(degree.get(dr, 0))
        drug_nb_sz = len(drug_nb)

        r = 1
        batch_size = 2000
        for start in range(0, len(candidate_ids), batch_size):
            end = min(start + batch_size, len(candidate_ids))
            batch_emb = emb_feats[start:end]

            graph_feats = np.zeros((end - start, 6), dtype=np.float32)
            for j, ci in enumerate(candidate_ids[start:end]):
                ci_nb = nb_sets.get(ci, set())
                shared = drug_nb & ci_nb
                union_sz = drug_nb_sz + len(ci_nb) - len(shared)
                graph_feats[j, 0] = len(shared)
                graph_feats[j, 1] = len(shared) / union_sz if union_sz > 0 else 0.0
                graph_feats[j, 2] = sum(1.0 / np.log(degree[n]) for n in shared
                                        if degree.get(n, 1) > 1)
                graph_feats[j, 3] = np.log1p(drug_nb_sz * len(ci_nb))
                graph_feats[j, 4] = drug_deg
                graph_feats[j, 5] = np.log1p(degree.get(ci, 0))

            batch_feat = np.hstack([batch_emb, graph_feats]).astype(np.float32)
            scores = model.predict_proba(scaler.transform(batch_feat))[:, 1]
            r += int(np.sum(scores > true_score))

        ranks.append(r)
        if (idx + 1) % 25 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (idx + 1 - skipped) * (len(test_pos) - idx - 1) if (idx + 1 - skipped) > 0 else 0
            log.info(f"  {idx+1}/{len(test_pos)} rank={r} ({elapsed:.0f}s, ETA {eta:.0f}s) [{mem_mb()} MB]")

    n = len(ranks)
    results = {}
    log.info(f"\n=== {name} + XGBoost (n={n}, skipped={skipped}) ===")
    for k in [1, 3, 10, 50, 100, 200]:
        h = sum(1 for r in ranks if r <= k)
        pct = h / n if n > 0 else 0
        results[f"hits@{k}"] = pct
        log.info(f"  Hits@{k}: {pct:.4f} ({h}/{n})")
    if n > 0:
        results["mrr"] = float(np.mean([1.0 / r for r in ranks]))
        results["median_rank"] = float(np.median(ranks))
    else:
        results["mrr"] = 0.0
        results["median_rank"] = 0.0
    log.info(f"  MRR: {results['mrr']:.4f}")
    log.info(f"  MedRank: {results['median_rank']:.1f}")

    del em, disease_matrix, emb_feats
    gc.collect()
    return results


# Run CompGCN first (smaller embeddings = less memory)
compgcn = run("CompGCN",
              SCORE_DIR / "compgcn/compgcn_embeddings.npz",
              SCORE_DIR / "compgcn/models/xgboost_model.pkl")

gc.collect()

rotate = run("RotatE",
             HOME / "rotate_embeddings.npz",
             SCORE_DIR / "rotate/models/xgboost_model.pkl")

out = {"CompGCN_XGBoost": compgcn, "RotatE_XGBoost": rotate}
outfile = HOME / "paper_hits_at_k.json"
with open(outfile, "w") as f:
    json.dump(out, f, indent=2)
log.info(f"\nSaved to {outfile}")
