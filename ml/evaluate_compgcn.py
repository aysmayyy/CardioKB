"""
Generate full evaluation report for the CompGCN + XGBoost link prediction decoder.

Same evaluation pipeline as Node2Vec and RotatE but using CompGCN embeddings.
Produces:
  1. Classification report (text + JSON)
  2. Confusion matrix
  3. ROC curve plot
  4. Precision-Recall curve plot
  5. Feature importance plot (top 20)

All outputs saved to ml/data/compgcn/results/.
"""

import json
import pickle
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.metrics import (
    classification_report, confusion_matrix, ConfusionMatrixDisplay,
    roc_curve, auc, precision_recall_curve, average_precision_score,
    roc_auc_score,
)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_prediction_compgcn import (
    load_embeddings, load_node_metadata, get_drug_disease_ids,
    build_graph_structure_from_train, filter_therapeutic_drugs,
    load_split_edges, sample_negatives, get_all_existing_edges,
    build_dataset,
)

RESULTS_DIR = Path(__file__).resolve().parent / "data" / "compgcn" / "results"
MODELS_DIR = Path(__file__).resolve().parent / "data" / "compgcn" / "models"


def train_xgboost(X_train, y_train, X_val, y_val):
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)

    model = XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        eval_metric="logloss", early_stopping_rounds=20,
        n_jobs=-1, random_state=42,
    )
    model.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
    print(f"XGBoost stopped at iteration {model.best_iteration}")
    return model, scaler


def get_feature_names(emb_dim):
    return (
        [f"hadamard_{i}" for i in range(emb_dim)]
        + [f"diff_{i}" for i in range(emb_dim)]
        + ["cosine", "l2"]
        + ["shared_neighbors", "jaccard", "adamic_adar",
           "log_pref_attach", "log_deg_drug", "log_deg_disease"]
    )


def save_classification_report(y_true, y_pred, y_prob):
    report_text = classification_report(
        y_true, y_pred, target_names=["Negative (no edge)", "Positive (treats)"]
    )
    report_dict = classification_report(
        y_true, y_pred, target_names=["Negative", "Positive"], output_dict=True
    )
    report_dict["auroc"] = float(roc_auc_score(y_true, y_prob))
    report_dict["auprc"] = float(average_precision_score(y_true, y_prob))

    print("\n=== Classification Report (Test Set) ===")
    print(report_text)
    print(f"AUROC: {report_dict['auroc']:.4f}")
    print(f"AUPRC: {report_dict['auprc']:.4f}")

    with open(RESULTS_DIR / "classification_report.json", "w") as f:
        json.dump(report_dict, f, indent=2)
    with open(RESULTS_DIR / "classification_report.txt", "w") as f:
        f.write("CompGCN + XGBoost Link Prediction — Test Set Classification Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(report_text)
        f.write(f"\nAUROC: {report_dict['auroc']:.4f}\n")
        f.write(f"AUPRC: {report_dict['auprc']:.4f}\n")
    print("Saved classification_report.json and .txt")


def save_confusion_matrix(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred)
    print(f"\nConfusion Matrix:\n{cm}")

    fig, ax = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(cm, display_labels=["Negative", "Positive"])
    disp.plot(ax=ax, cmap="Purples", values_format="d")
    ax.set_title("CompGCN + XGBoost Link Prediction — Confusion Matrix (Test Set)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "confusion_matrix.png", dpi=150)
    plt.close(fig)
    print("Saved confusion_matrix.png")


def save_roc_curve(y_true, y_prob):
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    roc_auc = auc(fpr, tpr)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(fpr, tpr, color="#7c3aed", lw=2,
            label=f"CompGCN + XGBoost (AUROC = {roc_auc:.4f})")
    ax.plot([0, 1], [0, 1], color="gray", lw=1, linestyle="--", label="Random")
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("ROC Curve — CompGCN + XGBoost Drug–Disease Link Prediction", fontsize=13)
    ax.legend(loc="lower right", fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "roc_curve.png", dpi=150)
    plt.close(fig)
    print(f"Saved roc_curve.png (AUROC = {roc_auc:.4f})")


def save_pr_curve(y_true, y_prob):
    precision, recall, _ = precision_recall_curve(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    baseline = y_true.sum() / len(y_true)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(recall, precision, color="#dc2626", lw=2,
            label=f"CompGCN + XGBoost (AUPRC = {ap:.4f})")
    ax.axhline(y=baseline, color="gray", lw=1, linestyle="--",
               label=f"Baseline ({baseline:.2f})")
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.set_xlabel("Recall", fontsize=12)
    ax.set_ylabel("Precision", fontsize=12)
    ax.set_title("Precision-Recall Curve — CompGCN + XGBoost Drug–Disease Link Prediction",
                 fontsize=13)
    ax.legend(loc="lower left", fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "pr_curve.png", dpi=150)
    plt.close(fig)
    print(f"Saved pr_curve.png (AUPRC = {ap:.4f})")


def save_feature_importance(model, emb_dim, top_n=20):
    feat_names = get_feature_names(emb_dim)
    importances = model.feature_importances_
    top_idx = np.argsort(importances)[-top_n:]
    top_names = [feat_names[i] if i < len(feat_names) else f"feat_{i}" for i in top_idx]
    top_vals = importances[top_idx]

    fig, ax = plt.subplots(figsize=(8, 7))
    colors = ["#7c3aed" if not n.startswith(("shared", "jaccard", "adamic", "log_", "cosine", "l2"))
              else "#dc2626" for n in top_names]
    bars = ax.barh(range(top_n), top_vals, color=colors)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(top_names, fontsize=10)
    ax.set_xlabel("Feature Importance (gain)", fontsize=12)
    ax.set_title(f"Top {top_n} Feature Importances — CompGCN + XGBoost Decoder", fontsize=13)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#7c3aed", label="Embedding features"),
        Patch(facecolor="#dc2626", label="Structural features"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=10)
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "feature_importance.png", dpi=150)
    plt.close(fig)
    print(f"Saved feature_importance.png (top {top_n})")

    feat_importance_data = sorted(
        zip(feat_names, importances.tolist()), key=lambda x: -x[1]
    )
    with open(RESULTS_DIR / "feature_importance.json", "w") as f:
        json.dump(feat_importance_data[:top_n], f, indent=2)


def save_models(model, scaler, emb_map):
    MODELS_DIR.mkdir(exist_ok=True)
    with open(MODELS_DIR / "xgboost_model.pkl", "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)
    print(f"Saved xgboost_model.pkl ({(MODELS_DIR / 'xgboost_model.pkl').stat().st_size / 1e6:.1f} MB)")


def main():
    print("Loading CompGCN embeddings and metadata...")
    emb_map = load_embeddings()
    emb_dim = len(next(iter(emb_map.values())))
    print(f"Embedding dimension: {emb_dim}")

    meta = load_node_metadata()
    drugs_all, diseases = get_drug_disease_ids(meta)

    print("Building graph structure from train edges...")
    neighbors, degree, edge_types_per_node = build_graph_structure_from_train()

    drugs = filter_therapeutic_drugs(drugs_all, edge_types_per_node)
    drugs_with_emb = drugs & set(emb_map.keys())
    diseases_with_emb = diseases & set(emb_map.keys())

    train_pos = [(s, d) for s, d, _ in load_split_edges("train", "drugTreatsDisease")
                 if s in drugs_with_emb and d in diseases_with_emb]
    val_pos = [(s, d) for s, d, _ in load_split_edges("val", "drugTreatsDisease")
               if s in drugs_with_emb and d in diseases_with_emb]
    test_pos = [(s, d) for s, d, _ in load_split_edges("test", "drugTreatsDisease")
                if s in drugs_with_emb and d in diseases_with_emb]

    print(f"Splits — Train: {len(train_pos)}, Val: {len(val_pos)}, Test: {len(test_pos)}")

    all_existing = get_all_existing_edges(drugs, diseases)

    train_neg = sample_negatives(train_pos, drugs_with_emb, diseases_with_emb,
                                 all_existing, len(train_pos), seed=42)
    val_neg = sample_negatives(val_pos, drugs_with_emb, diseases_with_emb,
                               all_existing, len(val_pos), seed=123)
    test_neg = sample_negatives(test_pos, drugs_with_emb, diseases_with_emb,
                                all_existing, len(test_pos), seed=456)

    print("Building feature matrices...")
    X_train, y_train, _ = build_dataset(train_pos, train_neg, emb_map, neighbors, degree)
    X_val, y_val, _ = build_dataset(val_pos, val_neg, emb_map, neighbors, degree)
    X_test, y_test, _ = build_dataset(test_pos, test_neg, emb_map, neighbors, degree)
    print(f"Test set: {X_test.shape[0]} samples ({int(y_test.sum())} pos, {int((1-y_test).sum())} neg)")

    print("\nTraining XGBoost (same hyperparams as other methods)...")
    model, scaler = train_xgboost(X_train, y_train, X_val, y_val)

    X_test_s = scaler.transform(X_test)
    y_prob = model.predict_proba(X_test_s)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("GENERATING EVALUATION REPORT (CompGCN)")
    print("=" * 60)

    save_classification_report(y_test, y_pred, y_prob)
    save_confusion_matrix(y_test, y_pred)
    save_roc_curve(y_test, y_prob)
    save_pr_curve(y_test, y_prob)
    save_feature_importance(model, emb_dim)
    save_models(model, scaler, emb_map)

    print(f"\nAll results saved to {RESULTS_DIR}/ and {MODELS_DIR}/")


if __name__ == "__main__":
    main()
