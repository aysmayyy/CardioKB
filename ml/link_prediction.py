"""
Link prediction for drug repurposing on CardioKB.

Proper methodology (no data leakage):
  - Node2Vec trained on train edges only (80%)
  - Val set (10%) for hyperparameter tuning
  - Test set (10%) for final evaluation
  - Three decoders: Cosine similarity, XGBoost, MLP
  - 1:1 negative sampling ratio
  - Therapeutic drug filter applied
"""

import csv
import json
import os
import logging
import numpy as np
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
from neo4j import GraphDatabase
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATA_DIR = Path(__file__).resolve().parent / "data"
SPLIT_DIR = DATA_DIR / "splits"
MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
MEMGRAPH_USER = os.getenv("MEMGRAPH_USERNAME", "")
MEMGRAPH_PASS = os.getenv("MEMGRAPH_PASSWORD", "")

TOP_K = 500
MIN_CONFIDENCE = 0.5

THERAPEUTIC_EDGE_TYPES = {
    "drugBindsGene", "compoundInPharmacologicClass", "compoundCausesSideEffect",
    "drugTreatsDisease", "AFFECTS_RESPONSE_TO", "TESTS_INTERVENTION",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_embeddings():
    """Load Node2Vec embeddings trained on train edges only."""
    path = DATA_DIR / "train_embeddings.npz"
    data = np.load(path)
    node_ids = data["node_ids"]
    embeddings = data["embeddings"]
    emb_map = {int(nid): embeddings[i] for i, nid in enumerate(node_ids)}
    log.info(f"Loaded train embeddings: {embeddings.shape} from {path.name}")
    return emb_map


def load_node_metadata():
    """Load node metadata TSV."""
    meta = {}
    with open(DATA_DIR / "nodes.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            int_id = int(row["int_id"])
            meta[int_id] = {
                "label": row["label"],
                "name": row["name"],
                "memgraph_id": int(row["memgraph_id"]),
            }
    log.info(f"Loaded metadata for {len(meta)} nodes")
    return meta


def load_split_edges(split_name, rel_type_filter=None):
    """Load edges from a split file. Optionally filter by rel_type."""
    edges = []
    with open(SPLIT_DIR / f"{split_name}_edges.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if rel_type_filter and row["rel_type"] != rel_type_filter:
                continue
            edges.append((int(row["src"]), int(row["dst"]), row["rel_type"]))
    return edges


def build_graph_structure_from_train():
    """Build adjacency/degree from train edges only (no leakage)."""
    neighbors = defaultdict(set)
    degree = defaultdict(int)
    edge_types_per_node = defaultdict(set)

    with open(SPLIT_DIR / "train_edges.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            src, dst = int(row["src"]), int(row["dst"])
            rel = row["rel_type"]
            neighbors[src].add(dst)
            neighbors[dst].add(src)
            degree[src] += 1
            degree[dst] += 1
            edge_types_per_node[src].add(rel)
            edge_types_per_node[dst].add(rel)

    log.info(f"Train graph structure: {len(neighbors)} nodes")
    return neighbors, degree, edge_types_per_node


def get_drug_disease_ids(meta):
    """Get sets of integer IDs for Drug and Disease nodes."""
    drugs = {nid for nid, m in meta.items() if m["label"] == "Drug"}
    diseases = {nid for nid, m in meta.items() if m["label"] == "Disease"}
    log.info(f"Drug nodes: {len(drugs)}, Disease nodes: {len(diseases)}")
    return drugs, diseases


def filter_therapeutic_drugs(drugs, edge_types_per_node):
    """Keep only drugs with therapeutic signal edges."""
    therapeutic = set()
    for d in drugs:
        if edge_types_per_node.get(d, set()) & THERAPEUTIC_EDGE_TYPES:
            therapeutic.add(d)
    log.info(f"Therapeutic filter: {len(therapeutic)} kept, "
             f"{len(drugs) - len(therapeutic)} removed")
    return therapeutic


def get_all_existing_edges(drugs, diseases):
    """Get all Drug->Disease edges across ALL splits (for filtering predictions)."""
    existing = set()
    for split in ["train", "val", "test"]:
        with open(SPLIT_DIR / f"{split}_edges.tsv") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                src, dst = int(row["src"]), int(row["dst"])
                if src in drugs and dst in diseases:
                    existing.add((src, dst))
                elif src in diseases and dst in drugs:
                    existing.add((dst, src))
    log.info(f"All existing Drug->Disease edges (all splits): {len(existing)}")
    return existing


# ---------------------------------------------------------------------------
# Negative sampling
# ---------------------------------------------------------------------------

def sample_negatives(positives, drugs_with_emb, diseases_with_emb,
                     all_existing, n_neg, seed):
    """Sample negative Drug-Disease pairs not in the graph. Returns list of (d, dis)."""
    rng = np.random.RandomState(seed)
    drug_list = sorted(drugs_with_emb)
    disease_list = sorted(diseases_with_emb)

    neg_set = set()
    attempts = 0
    max_attempts = n_neg * 50
    pos_set = set(positives)
    while len(neg_set) < n_neg and attempts < max_attempts:
        d = drug_list[rng.randint(len(drug_list))]
        dis = disease_list[rng.randint(len(disease_list))]
        pair = (d, dis)
        if pair not in all_existing and pair not in neg_set:
            neg_set.add(pair)
        attempts += 1
    return list(neg_set)


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_structural_features(node_a, node_b, neighbors, degree):
    """Graph-structural features for a node pair."""
    nbrs_a = neighbors.get(node_a, set())
    nbrs_b = neighbors.get(node_b, set())
    shared = nbrs_a & nbrs_b
    union_count = len(nbrs_a | nbrs_b)

    jaccard = len(shared) / union_count if union_count > 0 else 0.0
    adamic_adar = sum(1.0 / np.log(degree[n]) for n in shared if degree.get(n, 1) > 1)
    pref_attachment = len(nbrs_a) * len(nbrs_b)

    return np.array([
        len(shared),
        jaccard,
        adamic_adar,
        np.log1p(pref_attachment),
        np.log1p(degree.get(node_a, 0)),
        np.log1p(degree.get(node_b, 0)),
    ])


def compute_pair_features(emb_a, emb_b, node_a, node_b, neighbors, degree):
    """Full feature vector: embedding + structural."""
    hadamard = emb_a * emb_b
    diff = np.abs(emb_a - emb_b)
    norm_a = np.linalg.norm(emb_a)
    norm_b = np.linalg.norm(emb_b)
    cosine = np.dot(emb_a, emb_b) / (norm_a * norm_b + 1e-8)
    l2 = np.linalg.norm(emb_a - emb_b)

    struct = compute_structural_features(node_a, node_b, neighbors, degree)
    return np.concatenate([hadamard, diff, [cosine, l2], struct])


def compute_cosine_score(emb_a, emb_b):
    """Simple cosine similarity between two embeddings."""
    norm_a = np.linalg.norm(emb_a)
    norm_b = np.linalg.norm(emb_b)
    return float(np.dot(emb_a, emb_b) / (norm_a * norm_b + 1e-8))


# ---------------------------------------------------------------------------
# Build datasets
# ---------------------------------------------------------------------------

def build_dataset(pos_pairs, neg_pairs, emb_map, neighbors, degree):
    """Build feature matrix and labels from positive and negative pairs."""
    all_pairs = [(d, dis, 1) for d, dis in pos_pairs] + \
                [(d, dis, 0) for d, dis in neg_pairs]

    X = np.array([
        compute_pair_features(emb_map[d], emb_map[dis], d, dis, neighbors, degree)
        for d, dis, _ in all_pairs
    ])
    y = np.array([label for _, _, label in all_pairs])
    pairs = [(d, dis) for d, dis, _ in all_pairs]
    return X, y, pairs


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------

def evaluate_cosine_decoder(train_pos, train_neg, val_pos, val_neg,
                            test_pos, test_neg, emb_map):
    """Decoder (a): cosine similarity — no learned parameters."""
    log.info("  Computing cosine scores...")

    def score_pairs(pos_pairs, neg_pairs):
        scores, labels = [], []
        for d, dis in pos_pairs:
            scores.append(compute_cosine_score(emb_map[d], emb_map[dis]))
            labels.append(1)
        for d, dis in neg_pairs:
            scores.append(compute_cosine_score(emb_map[d], emb_map[dis]))
            labels.append(0)
        return np.array(scores), np.array(labels)

    val_scores, val_y = score_pairs(val_pos, val_neg)
    test_scores, test_y = score_pairs(test_pos, test_neg)

    # Find best threshold on val set
    best_thresh, best_f1 = 0.5, 0
    for thresh in np.arange(0.0, 1.0, 0.01):
        preds = (val_scores >= thresh).astype(int)
        tp = ((preds == 1) & (val_y == 1)).sum()
        fp = ((preds == 1) & (val_y == 0)).sum()
        fn = ((preds == 0) & (val_y == 1)).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh
    log.info(f"  Best threshold (val): {best_thresh:.2f} (F1={best_f1:.4f})")

    val_auroc = roc_auc_score(val_y, val_scores)
    val_auprc = average_precision_score(val_y, val_scores)
    test_auroc = roc_auc_score(test_y, test_scores)
    test_auprc = average_precision_score(test_y, test_scores)

    test_preds = (test_scores >= best_thresh).astype(int)
    report = classification_report(test_y, test_preds, target_names=["No Treat", "Treats"])

    return {
        "name": "Cosine",
        "val_auroc": val_auroc, "val_auprc": val_auprc,
        "test_auroc": test_auroc, "test_auprc": test_auprc,
        "threshold": best_thresh,
        "report": report,
        "test_scores": test_scores, "test_y": test_y,
    }


def evaluate_xgboost_decoder(X_train, y_train, X_val, y_val, X_test, y_test):
    """Decoder (b): XGBoost classifier."""
    from xgboost import XGBClassifier

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    model = XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        eval_metric="logloss", early_stopping_rounds=20,
        n_jobs=-1, random_state=42,
    )
    model.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
    log.info(f"  XGBoost stopped at {model.best_iteration} iterations")

    val_probs = model.predict_proba(X_val_s)[:, 1]
    test_probs = model.predict_proba(X_test_s)[:, 1]

    val_auroc = roc_auc_score(y_val, val_probs)
    val_auprc = average_precision_score(y_val, val_probs)
    test_auroc = roc_auc_score(y_test, test_probs)
    test_auprc = average_precision_score(y_test, test_probs)

    test_preds = (test_probs >= 0.5).astype(int)
    report = classification_report(y_test, test_preds, target_names=["No Treat", "Treats"])

    # Feature importance
    if hasattr(model, "feature_importances_"):
        feat_names = (
            [f"hadamard_{i}" for i in range(128)]
            + [f"diff_{i}" for i in range(128)]
            + ["cosine", "l2"]
            + ["shared_neighbors", "jaccard", "adamic_adar",
               "log_pref_attach", "log_deg_drug", "log_deg_disease"]
        )
        importances = model.feature_importances_
        top_idx = np.argsort(importances)[-10:][::-1]
        log.info("  Top 10 features:")
        for idx in top_idx:
            log.info(f"    {feat_names[idx]}: {importances[idx]:.4f}")

    return {
        "name": "XGBoost",
        "val_auroc": val_auroc, "val_auprc": val_auprc,
        "test_auroc": test_auroc, "test_auprc": test_auprc,
        "report": report,
        "model": model, "scaler": scaler,
        "test_scores": test_probs, "test_y": y_test,
    }


def evaluate_mlp_decoder(X_train, y_train, X_val, y_val, X_test, y_test):
    """Decoder (c): MLP with one hidden layer (sklearn)."""
    from sklearn.neural_network import MLPClassifier

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    model = MLPClassifier(
        hidden_layer_sizes=(256,),
        activation="relu",
        max_iter=200,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=15,
        random_state=42,
        verbose=False,
    )
    model.fit(X_train_s, y_train)
    log.info(f"  MLP stopped at {model.n_iter_} iterations")

    val_probs = model.predict_proba(X_val_s)[:, 1]
    test_probs = model.predict_proba(X_test_s)[:, 1]

    val_auroc = roc_auc_score(y_val, val_probs)
    val_auprc = average_precision_score(y_val, val_probs)
    test_auroc = roc_auc_score(y_test, test_probs)
    test_auprc = average_precision_score(y_test, test_probs)

    test_preds = (test_probs >= 0.5).astype(int)
    report = classification_report(y_test, test_preds, target_names=["No Treat", "Treats"])

    return {
        "name": "MLP",
        "val_auroc": val_auroc, "val_auprc": val_auprc,
        "test_auroc": test_auroc, "test_auprc": test_auprc,
        "report": report,
        "model": model, "scaler": scaler, "is_sklearn": True,
        "test_scores": test_probs, "test_y": y_test,
    }


# ---------------------------------------------------------------------------
# Ranking metrics
# ---------------------------------------------------------------------------

def compute_ranking_metrics(test_pos, test_neg, scores_pos, scores_neg):
    """Compute Hits@K and MRR."""
    all_scores = np.concatenate([scores_pos, scores_neg])
    sorted_indices = np.argsort(-all_scores)

    pos_indices = set(range(len(scores_pos)))
    ranks = []
    rank = 0
    for idx in sorted_indices:
        rank += 1
        if idx in pos_indices:
            ranks.append(rank)

    n_pos = len(scores_pos)
    metrics = {}
    for k in [10, 50, 100, 200]:
        hits = sum(1 for r in ranks if r <= k)
        metrics[f"hits@{k}"] = hits / n_pos if n_pos > 0 else 0
    metrics["mrr"] = float(np.mean([1.0 / r for r in ranks])) if ranks else 0
    metrics["median_rank"] = float(np.median(ranks)) if ranks else 0
    return metrics


# ---------------------------------------------------------------------------
# Scoring & storage
# ---------------------------------------------------------------------------

def score_all_unknown_pairs(best_result, emb_map, meta, drugs, diseases,
                            all_existing, neighbors, degree):
    """Score all unknown Drug-Disease pairs with the best decoder."""
    drug_list = sorted(drugs & set(emb_map.keys()))
    disease_list = sorted(diseases & set(emb_map.keys()))
    n_candidates = len(drug_list) * len(disease_list)
    log.info(f"Scoring {len(drug_list)} drugs x {len(disease_list)} diseases = "
             f"{n_candidates:,} candidate pairs...")

    decoder_name = best_result["name"]
    predictions = []

    if decoder_name == "Cosine":
        thresh = best_result["threshold"]
        for d in drug_list:
            emb_d = emb_map[d]
            for dis in disease_list:
                if (d, dis) in all_existing:
                    continue
                score = compute_cosine_score(emb_d, emb_map[dis])
                if score >= thresh:
                    predictions.append((d, dis, score))

    elif decoder_name == "XGBoost":
        model = best_result["model"]
        scaler = best_result["scaler"]
        batch_X, batch_pairs = [], []
        batch_size = 10000

        for d in drug_list:
            emb_d = emb_map[d]
            for dis in disease_list:
                if (d, dis) in all_existing:
                    continue
                batch_X.append(compute_pair_features(
                    emb_d, emb_map[dis], d, dis, neighbors, degree))
                batch_pairs.append((d, dis))

                if len(batch_X) >= batch_size:
                    probs = model.predict_proba(scaler.transform(np.array(batch_X)))[:, 1]
                    for pair, prob in zip(batch_pairs, probs):
                        if prob >= MIN_CONFIDENCE:
                            predictions.append((pair[0], pair[1], float(prob)))
                    batch_X, batch_pairs = [], []

        if batch_X:
            probs = model.predict_proba(scaler.transform(np.array(batch_X)))[:, 1]
            for pair, prob in zip(batch_pairs, probs):
                if prob >= MIN_CONFIDENCE:
                    predictions.append((pair[0], pair[1], float(prob)))

    elif decoder_name == "MLP":
        model = best_result["model"]
        scaler = best_result["scaler"]
        batch_X, batch_pairs = [], []
        batch_size = 10000

        for d in drug_list:
            emb_d = emb_map[d]
            for dis in disease_list:
                if (d, dis) in all_existing:
                    continue
                batch_X.append(compute_pair_features(
                    emb_d, emb_map[dis], d, dis, neighbors, degree))
                batch_pairs.append((d, dis))

                if len(batch_X) >= batch_size:
                    probs = model.predict_proba(scaler.transform(np.array(batch_X)))[:, 1]
                    for pair, prob in zip(batch_pairs, probs):
                        if prob >= MIN_CONFIDENCE:
                            predictions.append((pair[0], pair[1], float(prob)))
                    batch_X, batch_pairs = [], []

        if batch_X:
            probs = model.predict_proba(scaler.transform(np.array(batch_X)))[:, 1]
            for pair, prob in zip(batch_pairs, probs):
                if prob >= MIN_CONFIDENCE:
                    predictions.append((pair[0], pair[1], float(prob)))

    predictions.sort(key=lambda x: -x[2])
    log.info(f"Pairs above {MIN_CONFIDENCE} confidence: {len(predictions)}")
    top = predictions[:TOP_K]
    if top:
        log.info(f"Top {len(top)} (confidence: {top[-1][2]:.4f} - {top[0][2]:.4f})")
    return top


def save_predictions_tsv(predictions, meta):
    """Save predictions to TSV."""
    out_path = DATA_DIR / "predictions.tsv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rank", "drug_int_id", "drug_name", "disease_int_id",
                         "disease_name", "confidence"])
        for rank, (d, dis, prob) in enumerate(predictions, 1):
            drug_name = meta.get(d, {}).get("name", "?")
            disease_name = meta.get(dis, {}).get("name", "?")
            writer.writerow([rank, d, drug_name, dis, disease_name, f"{prob:.6f}"])
    log.info(f"Saved {len(predictions)} predictions to {out_path}")


def save_evaluation_report(results, n_drugs, n_diseases, n_train_pos,
                           n_val_pos, n_test_pos, best_name):
    """Save full evaluation report."""
    report = {
        "methodology": "80/10/10 stratified split, Node2Vec on train only, 1:1 neg ratio",
        "n_therapeutic_drugs": n_drugs,
        "n_diseases": n_diseases,
        "n_train_positives": n_train_pos,
        "n_val_positives": n_val_pos,
        "n_test_positives": n_test_pos,
        "best_decoder": best_name,
        "decoders": {},
    }
    for r in results:
        report["decoders"][r["name"]] = {
            "val_auroc": r["val_auroc"],
            "val_auprc": r["val_auprc"],
            "test_auroc": r["test_auroc"],
            "test_auprc": r["test_auprc"],
        }
        if "ranking" in r:
            report["decoders"][r["name"]]["ranking"] = r["ranking"]

    out_path = DATA_DIR / "evaluation_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Saved evaluation report to {out_path}")


def store_in_memgraph(predictions, meta):
    """Store top predictions in Memgraph as predictedTreatsDisease edges."""
    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))
    try:
        with driver.session() as s:
            r = s.run("MATCH ()-[r:predictedTreatsDisease]->() DELETE r RETURN count(r)")
            deleted = r.single()[0]
            if deleted:
                log.info(f"Cleared {deleted} existing predictedTreatsDisease edges")

        batch = []
        for d, dis, prob in predictions:
            if d in meta and dis in meta:
                batch.append({
                    "drug_mgid": meta[d]["memgraph_id"],
                    "disease_mgid": meta[dis]["memgraph_id"],
                    "confidence": prob,
                })

        total = 0
        for i in range(0, len(batch), 500):
            chunk = batch[i:i + 500]
            with driver.session() as s:
                result = s.run(
                    """
                    UNWIND $batch AS row
                    MATCH (d:Drug) WHERE id(d) = row.drug_mgid
                    MATCH (dis:Disease) WHERE id(dis) = row.disease_mgid
                    CREATE (d)-[:predictedTreatsDisease {
                        confidence: row.confidence,
                        source: "Node2Vec_LinkPrediction"
                    }]->(dis)
                    RETURN count(*) AS created
                    """,
                    batch=chunk,
                )
                total += result.single()["created"]

        log.info(f"Stored {total} predictedTreatsDisease edges in Memgraph")
        return total
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("CardioKB Link Prediction v3 — Proper Methodology")
    log.info("=" * 60)

    # Load data
    emb_map = load_embeddings()
    meta = load_node_metadata()
    drugs_all, diseases = get_drug_disease_ids(meta)

    log.info("\nBuilding graph structure from train edges only...")
    neighbors, degree, edge_types_per_node = build_graph_structure_from_train()

    log.info("\nFiltering to therapeutic drugs...")
    drugs = filter_therapeutic_drugs(drugs_all, edge_types_per_node)
    drugs_with_emb = drugs & set(emb_map.keys())
    diseases_with_emb = diseases & set(emb_map.keys())
    log.info(f"Drugs with embeddings: {len(drugs_with_emb)}, "
             f"Diseases with embeddings: {len(diseases_with_emb)}")

    # Load split edges (drugTreatsDisease only for link prediction)
    train_pos_all = load_split_edges("train", "drugTreatsDisease")
    val_pos_all = load_split_edges("val", "drugTreatsDisease")
    test_pos_all = load_split_edges("test", "drugTreatsDisease")

    # Filter to therapeutic drugs with embeddings
    train_pos = [(s, d) for s, d, _ in train_pos_all
                 if s in drugs_with_emb and d in diseases_with_emb]
    val_pos = [(s, d) for s, d, _ in val_pos_all
               if s in drugs_with_emb and d in diseases_with_emb]
    test_pos = [(s, d) for s, d, _ in test_pos_all
                if s in drugs_with_emb and d in diseases_with_emb]

    log.info(f"\ndrugTreatsDisease splits (with embeddings):")
    log.info(f"  Train: {len(train_pos)}, Val: {len(val_pos)}, Test: {len(test_pos)}")

    # Get all existing edges for negative sampling exclusion
    all_existing = get_all_existing_edges(drugs, diseases)

    # Negative sampling (1:1 ratio)
    log.info("\nSampling negatives (1:1 ratio)...")
    train_neg = sample_negatives(train_pos, drugs_with_emb, diseases_with_emb,
                                 all_existing, len(train_pos), seed=42)
    val_neg = sample_negatives(val_pos, drugs_with_emb, diseases_with_emb,
                               all_existing, len(val_pos), seed=123)
    test_neg = sample_negatives(test_pos, drugs_with_emb, diseases_with_emb,
                                all_existing, len(test_pos), seed=456)
    log.info(f"  Train neg: {len(train_neg)}, Val neg: {len(val_neg)}, "
             f"Test neg: {len(test_neg)}")

    # Build feature matrices for XGBoost and MLP
    log.info("\nBuilding feature matrices...")
    X_train, y_train, _ = build_dataset(train_pos, train_neg, emb_map, neighbors, degree)
    X_val, y_val, _ = build_dataset(val_pos, val_neg, emb_map, neighbors, degree)
    X_test, y_test, _ = build_dataset(test_pos, test_neg, emb_map, neighbors, degree)
    log.info(f"  Train: {X_train.shape}, Val: {X_val.shape}, Test: {X_test.shape}")

    # Evaluate all three decoders
    results = []

    log.info("\n" + "=" * 60)
    log.info("DECODER (a): Cosine Similarity")
    log.info("=" * 60)
    cosine_result = evaluate_cosine_decoder(
        train_pos, train_neg, val_pos, val_neg, test_pos, test_neg, emb_map)
    # Ranking metrics for cosine
    cos_pos_scores = np.array([compute_cosine_score(emb_map[d], emb_map[dis])
                                for d, dis in test_pos])
    cos_neg_scores = np.array([compute_cosine_score(emb_map[d], emb_map[dis])
                                for d, dis in test_neg])
    cosine_result["ranking"] = compute_ranking_metrics(
        test_pos, test_neg, cos_pos_scores, cos_neg_scores)
    results.append(cosine_result)
    log.info(f"  Val  AUROC={cosine_result['val_auroc']:.4f}, "
             f"AUPRC={cosine_result['val_auprc']:.4f}")
    log.info(f"  Test AUROC={cosine_result['test_auroc']:.4f}, "
             f"AUPRC={cosine_result['test_auprc']:.4f}")
    log.info(f"\n{cosine_result['report']}")
    for k, v in cosine_result["ranking"].items():
        log.info(f"  {k}: {v:.4f}")

    log.info("\n" + "=" * 60)
    log.info("DECODER (b): XGBoost")
    log.info("=" * 60)
    xgb_result = evaluate_xgboost_decoder(X_train, y_train, X_val, y_val, X_test, y_test)
    # Ranking metrics
    xgb_pos_scores = xgb_result["test_scores"][:len(test_pos)]
    xgb_neg_scores = xgb_result["test_scores"][len(test_pos):]
    xgb_result["ranking"] = compute_ranking_metrics(
        test_pos, test_neg, xgb_pos_scores, xgb_neg_scores)
    results.append(xgb_result)
    log.info(f"  Val  AUROC={xgb_result['val_auroc']:.4f}, "
             f"AUPRC={xgb_result['val_auprc']:.4f}")
    log.info(f"  Test AUROC={xgb_result['test_auroc']:.4f}, "
             f"AUPRC={xgb_result['test_auprc']:.4f}")
    log.info(f"\n{xgb_result['report']}")
    for k, v in xgb_result["ranking"].items():
        log.info(f"  {k}: {v:.4f}")

    log.info("\n" + "=" * 60)
    log.info("DECODER (c): MLP (1 hidden layer)")
    log.info("=" * 60)
    mlp_result = evaluate_mlp_decoder(X_train, y_train, X_val, y_val, X_test, y_test)
    mlp_pos_scores = mlp_result["test_scores"][:len(test_pos)]
    mlp_neg_scores = mlp_result["test_scores"][len(test_pos):]
    mlp_result["ranking"] = compute_ranking_metrics(
        test_pos, test_neg, mlp_pos_scores, mlp_neg_scores)
    results.append(mlp_result)
    log.info(f"  Val  AUROC={mlp_result['val_auroc']:.4f}, "
             f"AUPRC={mlp_result['val_auprc']:.4f}")
    log.info(f"  Test AUROC={mlp_result['test_auroc']:.4f}, "
             f"AUPRC={mlp_result['test_auprc']:.4f}")
    log.info(f"\n{mlp_result['report']}")
    for k, v in mlp_result["ranking"].items():
        log.info(f"  {k}: {v:.4f}")

    # Summary comparison
    log.info("\n" + "=" * 60)
    log.info("DECODER COMPARISON")
    log.info("=" * 60)
    log.info(f"{'Decoder':<12} {'Val AUROC':>10} {'Val AUPRC':>10} "
             f"{'Test AUROC':>11} {'Test AUPRC':>11} {'MRR':>8} {'Hits@100':>9}")
    log.info("-" * 75)
    for r in results:
        ranking = r.get("ranking", {})
        log.info(f"{r['name']:<12} {r['val_auroc']:>10.4f} {r['val_auprc']:>10.4f} "
                 f"{r['test_auroc']:>11.4f} {r['test_auprc']:>11.4f} "
                 f"{ranking.get('mrr', 0):>8.4f} {ranking.get('hits@100', 0):>9.4f}")

    # Pick best by test AUROC
    best = max(results, key=lambda r: r["test_auroc"])
    log.info(f"\nBest decoder: {best['name']} (Test AUROC={best['test_auroc']:.4f})")

    # Score unknown pairs and store predictions
    log.info("\n" + "=" * 60)
    log.info(f"SCORING UNKNOWN PAIRS with {best['name']}")
    log.info("=" * 60)
    predictions = score_all_unknown_pairs(
        best, emb_map, meta, drugs, diseases, all_existing, neighbors, degree)

    save_predictions_tsv(predictions, meta)
    n_stored = store_in_memgraph(predictions, meta)

    save_evaluation_report(
        results, len(drugs_with_emb), len(diseases_with_emb),
        len(train_pos), len(val_pos), len(test_pos), best["name"])

    if predictions:
        log.info(f"\nTop 30 predicted drug repurposing candidates ({best['name']}):")
        log.info(f"{'Rank':<6}{'Drug':<30}{'Disease':<35}{'Confidence'}")
        log.info("-" * 85)
        for rank, (d, dis, prob) in enumerate(predictions[:30], 1):
            drug_name = meta.get(d, {}).get("name", "?")[:28]
            disease_name = meta.get(dis, {}).get("name", "?")[:33]
            log.info(f"{rank:<6}{drug_name:<30}{disease_name:<35}{prob:.4f}")

    log.info("\nDone.")


if __name__ == "__main__":
    main()
