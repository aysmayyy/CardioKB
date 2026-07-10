"""
Score-only script: retrain XGBoost, score all unknown pairs, save top 10K + full archive.
Skips the expensive Hits@K ranking loop (already validated on this data).
Memory-optimized: numpy arrays instead of dicts, float32 throughout.
"""
import csv, gc, gzip, json, os, sys, pickle, logging, heapq
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATA_DIR = Path(__file__).resolve().parent / "data"
SPLIT_DIR = DATA_DIR / "splits"
TOP_K = 10000
MIN_CONFIDENCE = 0.5

THERAPEUTIC_EDGE_TYPES = {
    "drugBindsGene", "compoundInPharmacologicClass", "compoundCausesSideEffect",
    "drugTreatsDisease", "AFFECTS_RESPONSE_TO", "TESTS_INTERVENTION",
}


def mem_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 0


def load_node_metadata():
    labels, names = {}, {}
    with open(DATA_DIR / "nodes.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            nid = int(row["int_id"])
            labels[nid] = row["label"]
            names[nid] = row["name"]
    log.info(f"Loaded metadata for {len(labels)} nodes [{mem_mb()} MB RSS]")
    return labels, names


def load_embeddings(method, max_node_id):
    if method == "compgcn":
        path = DATA_DIR / "compgcn" / "compgcn_embeddings.npz"
    else:
        path = DATA_DIR / "rotate" / "rotate_embeddings.npz"
    data = np.load(path)
    node_ids = data["node_ids"].astype(np.int64)
    raw_emb = data["embeddings"]
    dim = raw_emb.shape[1]
    emb = np.zeros((max_node_id + 1, dim), dtype=np.float32)
    emb[node_ids] = raw_emb.astype(np.float32)
    has_emb = np.zeros(max_node_id + 1, dtype=bool)
    has_emb[node_ids] = True
    del data, raw_emb, node_ids
    gc.collect()
    log.info(f"Loaded {method} embeddings: dim={dim}, nodes={has_emb.sum()} [{mem_mb()} MB RSS]")
    return emb, has_emb, dim


def build_graph_structure():
    degree = {}
    edge_type_sets = {}
    neighbor_lists = {}
    with open(SPLIT_DIR / "train_edges.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            s, d = int(row["src"]), int(row["dst"])
            rt = row["rel_type"]
            degree[s] = degree.get(s, 0) + 1
            degree[d] = degree.get(d, 0) + 1
            if s not in neighbor_lists:
                neighbor_lists[s] = []
                edge_type_sets[s] = set()
            if d not in neighbor_lists:
                neighbor_lists[d] = []
                edge_type_sets[d] = set()
            neighbor_lists[s].append(d)
            neighbor_lists[d].append(s)
            edge_type_sets[s].add(rt)
            edge_type_sets[d].add(rt)
    # Convert neighbor lists to frozensets for O(1) intersection
    neighbors = {n: frozenset(nbs) for n, nbs in neighbor_lists.items()}
    del neighbor_lists
    gc.collect()
    log.info(f"Train graph: {len(neighbors)} nodes [{mem_mb()} MB RSS]")
    return neighbors, degree, edge_type_sets


def get_sets(labels, has_emb, edge_type_sets):
    drugs = {n for n, l in labels.items() if l == "Drug"}
    diseases = {n for n, l in labels.items() if l == "Disease"}
    therapeutic = {d for d in drugs if edge_type_sets.get(d, set()) & THERAPEUTIC_EDGE_TYPES}
    drugs_e = sorted(d for d in therapeutic if has_emb[d])
    diseases_e = sorted(d for d in diseases if has_emb[d])
    log.info(f"Therapeutic drugs w/ emb: {len(drugs_e)}, diseases w/ emb: {len(diseases_e)}")
    return drugs_e, diseases_e, drugs, diseases


def get_existing_edges(drugs_set, diseases_set):
    existing = set()
    for split in ["train", "val", "test"]:
        with open(SPLIT_DIR / f"{split}_edges.tsv") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                s, d = int(row["src"]), int(row["dst"])
                if s in drugs_set and d in diseases_set:
                    existing.add((s, d))
                elif s in diseases_set and d in drugs_set:
                    existing.add((d, s))
    log.info(f"Existing drug->disease edges: {len(existing)}")
    return existing


def compute_pair_features(emb, na, nb, neighbors, degree):
    ea, eb = emb[na], emb[nb]
    hadamard = ea * eb
    diff = np.abs(ea - eb)
    dot = np.dot(ea, eb)
    norm_a, norm_b = np.linalg.norm(ea), np.linalg.norm(eb)
    cosine = dot / (norm_a * norm_b + 1e-8)
    l2 = np.linalg.norm(ea - eb)
    na_set = neighbors.get(na, frozenset())
    nb_set = neighbors.get(nb, frozenset())
    shared = na_set & nb_set
    union = len(na_set | nb_set)
    jaccard = len(shared) / union if union > 0 else 0.0
    aa = sum(1.0 / np.log(degree[n]) for n in shared if degree.get(n, 1) > 1)
    pa = len(na_set) * len(nb_set)
    return np.concatenate([hadamard, diff, [cosine, l2, len(shared), jaccard, aa,
                                            np.log1p(pa), np.log1p(degree.get(na, 0)),
                                            np.log1p(degree.get(nb, 0))]])


def sample_negatives(positives, drugs, diseases, existing, n, seed):
    rng = np.random.RandomState(seed)
    dl, dsl = list(drugs), list(diseases)
    neg, pos_set = set(), set(positives)
    for _ in range(n * 50):
        if len(neg) >= n:
            break
        pair = (dl[rng.randint(len(dl))], dsl[rng.randint(len(dsl))])
        if pair not in existing and pair not in neg:
            neg.add(pair)
    return list(neg)


def build_dataset(pos, neg, emb, neighbors, degree):
    pairs = [(d, s, 1) for d, s in pos] + [(d, s, 0) for d, s in neg]
    X = np.array([compute_pair_features(emb, d, s, neighbors, degree) for d, s, _ in pairs],
                 dtype=np.float32)
    y = np.array([l for _, _, l in pairs], dtype=np.float32)
    return X, y


def run(method):
    log.info(f"{'='*60}")
    log.info(f"SCORE-ONLY: {method.upper()}")
    log.info(f"{'='*60}")

    out_dir = DATA_DIR / method
    models_dir = out_dir / "models"
    models_dir.mkdir(exist_ok=True)

    labels, names = load_node_metadata()
    max_node_id = max(labels.keys())
    emb, has_emb, emb_dim = load_embeddings(method, max_node_id)
    neighbors, degree, edge_type_sets = build_graph_structure()
    drugs_e, diseases_e, drugs_all, diseases_all = get_sets(labels, has_emb, edge_type_sets)
    del edge_type_sets
    gc.collect()
    log.info(f"After setup: {mem_mb()} MB RSS")

    existing = get_existing_edges(drugs_all | set(drugs_e), diseases_all | set(diseases_e))

    def load_split(name):
        pairs = []
        drugs_set, diseases_set = set(drugs_e), set(diseases_e)
        with open(SPLIT_DIR / f"{name}_edges.tsv") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row["rel_type"] != "drugTreatsDisease":
                    continue
                s, d = int(row["src"]), int(row["dst"])
                if s in drugs_set and d in diseases_set:
                    pairs.append((s, d))
        return pairs

    train_pos = load_split("train")
    val_pos = load_split("val")
    test_pos = load_split("test")
    log.info(f"Splits: train={len(train_pos)}, val={len(val_pos)}, test={len(test_pos)}")

    train_neg = sample_negatives(train_pos, drugs_e, diseases_e, existing, len(train_pos), 42)
    val_neg = sample_negatives(val_pos, drugs_e, diseases_e, existing, len(val_pos), 123)

    log.info("Building feature matrices...")
    X_train, y_train = build_dataset(train_pos, train_neg, emb, neighbors, degree)
    X_val, y_val = build_dataset(val_pos, val_neg, emb, neighbors, degree)
    log.info(f"Train: {X_train.shape}, Val: {X_val.shape}")

    log.info("Training XGBoost...")
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)

    model = XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                          eval_metric="logloss", early_stopping_rounds=20,
                          n_jobs=-1, random_state=42)
    model.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
    log.info(f"XGBoost stopped at {model.best_iteration} iterations")

    with open(models_dir / "xgboost_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open(models_dir / "xgboost_scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)
    log.info(f"Saved model + scaler to {models_dir}/")

    del X_train, y_train, X_train_s, X_val, y_val, X_val_s
    del train_pos, val_pos, test_pos, train_neg, val_neg
    gc.collect()
    log.info(f"After XGBoost train: {mem_mb()} MB RSS")

    # Score all unknown pairs
    total = len(drugs_e) * len(diseases_e)
    log.info(f"Scoring {len(drugs_e)} drugs x {len(diseases_e)} diseases = {total:,} pairs...")

    archive = out_dir / "all_predictions_above_threshold.tsv.gz"
    archive_f = gzip.open(archive, "wt", newline="")
    archive_w = csv.writer(archive_f, delimiter="\t")
    archive_w.writerow(["rank", "drug_int_id", "drug_name", "disease_int_id", "disease_name", "confidence"])

    top_heap = []
    batch_X, batch_pairs = [], []
    batch_size = 25000
    scored = 0
    above_threshold = 0

    for d in drugs_e:
        for dis in diseases_e:
            if (d, dis) in existing:
                continue
            batch_X.append(compute_pair_features(emb, d, dis, neighbors, degree))
            batch_pairs.append((d, dis))
            if len(batch_X) >= batch_size:
                X_batch = np.array(batch_X, dtype=np.float32)
                probs = model.predict_proba(scaler.transform(X_batch))[:, 1]
                for pair, prob in zip(batch_pairs, probs):
                    if prob >= MIN_CONFIDENCE:
                        above_threshold += 1
                        archive_w.writerow(["", pair[0], names[pair[0]],
                                            pair[1], names[pair[1]], f"{prob:.6f}"])
                        if len(top_heap) < TOP_K:
                            heapq.heappush(top_heap, (prob, pair[0], pair[1]))
                        elif prob > top_heap[0][0]:
                            heapq.heapreplace(top_heap, (prob, pair[0], pair[1]))
                scored += len(batch_X)
                if scored % 500000 < batch_size:
                    log.info(f"  Scored {scored:,}/{total:,} ({scored/total*100:.1f}%), "
                             f"{above_threshold:,} above threshold [{mem_mb()} MB]")
                batch_X, batch_pairs = [], []
                del X_batch

    if batch_X:
        X_batch = np.array(batch_X, dtype=np.float32)
        probs = model.predict_proba(scaler.transform(X_batch))[:, 1]
        for pair, prob in zip(batch_pairs, probs):
            if prob >= MIN_CONFIDENCE:
                above_threshold += 1
                archive_w.writerow(["", pair[0], names[pair[0]],
                                    pair[1], names[pair[1]], f"{prob:.6f}"])
                if len(top_heap) < TOP_K:
                    heapq.heappush(top_heap, (prob, pair[0], pair[1]))
                elif prob > top_heap[0][0]:
                    heapq.heapreplace(top_heap, (prob, pair[0], pair[1]))
        scored += len(batch_X)

    archive_f.close()
    log.info(f"Scoring complete: {scored:,} pairs scored")
    log.info(f"Total predictions >= {MIN_CONFIDENCE}: {above_threshold:,}")
    log.info(f"Archived to {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")

    top = sorted(top_heap, key=lambda x: -x[0])

    with open(out_dir / "predictions.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["rank", "drug_int_id", "drug_name", "disease_int_id", "disease_name", "confidence"])
        for rank, (prob, d, dis) in enumerate(top, 1):
            w.writerow([rank, d, names[d], dis, names[dis], f"{prob:.6f}"])
    log.info(f"Saved top {len(top)} to {out_dir}/predictions.tsv")

    if top:
        log.info(f"Top: {names[top[0][1]]} -> {names[top[0][2]]} ({top[0][0]:.6f})")
        log.info(f"#10K: {names[top[-1][1]]} -> {names[top[-1][2]]} ({top[-1][0]:.6f})")

    log.info("Done.")
    return above_threshold, len(top)


if __name__ == "__main__":
    method = sys.argv[1] if len(sys.argv) > 1 else "compgcn"
    run(method)
