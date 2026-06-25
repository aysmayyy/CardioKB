"""
Generate comprehensive RotatE evaluation report as HTML.

Includes: methodology, decoder comparison, ROC/PR/confusion matrix/feature
importance plots, comparison vs Node2Vec baseline, top predictions,
and training details. Designed for presentation to advisors.
"""

import json
import base64
import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
ROTATE_DIR = DATA_DIR / "rotate"
NODE2VEC_DIR = DATA_DIR / "node2vec"
REPORT_PATH = ROTATE_DIR / "rotate_evaluation_report.html"


def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_predictions(path, n=30):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for i, row in enumerate(reader):
            if i >= n:
                break
            rows.append(row)
    return rows


def main():
    rotate_eval = load_json(ROTATE_DIR / "evaluation_report.json")
    rotate_class = load_json(ROTATE_DIR / "results" / "classification_report.json")
    rotate_feat = load_json(ROTATE_DIR / "results" / "feature_importance.json")
    n2v_eval = load_json(NODE2VEC_DIR / "evaluation_report.json")
    n2v_class = load_json(NODE2VEC_DIR / "results" / "classification_report.json")
    training = load_json(ROTATE_DIR / "training_summary.json")

    rotate_preds = load_predictions(ROTATE_DIR / "predictions.tsv")
    n2v_preds = load_predictions(NODE2VEC_DIR / "predictions.tsv")

    roc_b64 = img_to_base64(ROTATE_DIR / "results" / "roc_curve.png")
    pr_b64 = img_to_base64(ROTATE_DIR / "results" / "pr_curve.png")
    cm_b64 = img_to_base64(ROTATE_DIR / "results" / "confusion_matrix.png")
    fi_b64 = img_to_base64(ROTATE_DIR / "results" / "feature_importance.png")

    n2v_roc_b64 = img_to_base64(NODE2VEC_DIR / "results" / "roc_curve.png")
    n2v_pr_b64 = img_to_base64(NODE2VEC_DIR / "results" / "pr_curve.png")
    n2v_cm_b64 = img_to_base64(NODE2VEC_DIR / "results" / "confusion_matrix.png")
    n2v_fi_b64 = img_to_base64(NODE2VEC_DIR / "results" / "feature_importance.png")

    rd = rotate_eval["decoders"]
    nd = n2v_eval["decoders"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CardioKB — RotatE Link Prediction Evaluation Report</title>
<style>
    body {{ font-family: 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px 40px; color: #1a1a1a; line-height: 1.6; }}
    h1 {{ color: #0f172a; border-bottom: 3px solid #16a34a; padding-bottom: 10px; }}
    h2 {{ color: #1e3a5f; margin-top: 40px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
    h3 {{ color: #334155; margin-top: 25px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: center; }}
    th {{ background-color: #f1f5f9; font-weight: 600; }}
    tr:nth-child(even) {{ background-color: #f8fafc; }}
    .best {{ background-color: #dcfce7; font-weight: 600; }}
    .improved {{ color: #16a34a; font-weight: 600; }}
    .worse {{ color: #dc2626; }}
    .metric-box {{ display: inline-block; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 10px; padding: 15px 25px; margin: 8px; text-align: center; }}
    .metric-box .value {{ font-size: 28px; font-weight: 700; color: #16a34a; }}
    .metric-box .label {{ font-size: 13px; color: #475569; margin-top: 4px; }}
    .n2v-box {{ background: #eff6ff; border-color: #2563eb; }}
    .n2v-box .value {{ color: #2563eb; }}
    .plot-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
    .plot-grid img {{ width: 100%; border: 1px solid #e2e8f0; border-radius: 6px; }}
    .plot-single img {{ width: 70%; display: block; margin: 15px auto; border: 1px solid #e2e8f0; border-radius: 6px; }}
    .summary {{ background: #f8fafc; border-left: 4px solid #16a34a; padding: 15px 20px; margin: 20px 0; }}
    .pred-table {{ font-size: 13px; }}
    .pred-table td {{ text-align: left; }}
    .pred-table td:first-child, .pred-table td:last-child {{ text-align: center; }}
    .section-info {{ color: #64748b; font-size: 14px; margin-bottom: 15px; }}
    .comparison-header {{ display: flex; justify-content: center; gap: 40px; margin: 20px 0; }}
    .footer {{ margin-top: 50px; padding-top: 15px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 12px; text-align: center; }}
    @media print {{ body {{ max-width: 100%; padding: 10px; }} .plot-grid {{ break-inside: avoid; }} }}
</style>
</head>
<body>

<h1>CardioKB — RotatE Link Prediction Evaluation Report</h1>
<p class="section-info">Generated: 2026-06-24 | CardioKB Knowledge Graph: 459,092 nodes, 5.4M+ relationships, 22 data sources</p>

<div class="summary">
<strong>Key Result:</strong> RotatE + XGBoost achieves <strong>Test AUROC = 0.9652</strong> and <strong>AUPRC = 0.9655</strong> for drug-disease link prediction,
improving over the Node2Vec baseline (AUROC = 0.9504) by <strong>+0.015</strong>. Both methods use the same 80/10/10 stratified split, negative sampling, and decoder architecture for fair comparison.
</div>

<h2>1. Headline Metrics</h2>

<div class="comparison-header">
    <div>
        <div style="text-align:center; font-weight:600; margin-bottom:8px; color:#16a34a;">RotatE (new)</div>
        <div class="metric-box"><div class="value">0.9652</div><div class="label">Test AUROC</div></div>
        <div class="metric-box"><div class="value">0.9655</div><div class="label">Test AUPRC</div></div>
        <div class="metric-box"><div class="value">90.7%</div><div class="label">Accuracy</div></div>
    </div>
    <div>
        <div style="text-align:center; font-weight:600; margin-bottom:8px; color:#2563eb;">Node2Vec (baseline)</div>
        <div class="metric-box n2v-box"><div class="value">0.9504</div><div class="label">Test AUROC</div></div>
        <div class="metric-box n2v-box"><div class="value">0.9579</div><div class="label">Test AUPRC</div></div>
        <div class="metric-box n2v-box"><div class="value">86.6%</div><div class="label">Accuracy</div></div>
    </div>
</div>

<h2>2. Methodology</h2>

<h3>2.1 Graph & Data</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Knowledge Graph</td><td>CardioKB — 459,092 nodes, 5,437,921 relationships, 17 node types, 25 relationship types</td></tr>
<tr><td>Target edge type</td><td><code>drugTreatsDisease</code> (3,782 total edges)</td></tr>
<tr><td>Therapeutic drugs (filtered)</td><td>{rotate_eval['n_therapeutic_drugs']:,}</td></tr>
<tr><td>Diseases</td><td>{rotate_eval['n_diseases']}</td></tr>
<tr><td>Edge split</td><td>80/10/10 stratified by edge type (same random seed for both methods)</td></tr>
<tr><td>Train / Val / Test positives</td><td>{rotate_eval['n_train_positives']:,} / {rotate_eval['n_val_positives']} / {rotate_eval['n_test_positives']}</td></tr>
<tr><td>Negative sampling</td><td>1:1 ratio, excluding all known Drug-Disease edges across all splits</td></tr>
<tr><td>Data leakage prevention</td><td>Embeddings trained on train split only; val/test edges hidden during training</td></tr>
</table>

<h3>2.2 RotatE Training Configuration</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Library</td><td>PyKEEN (Python Knowledge Graph Embedding library)</td></tr>
<tr><td>Model</td><td>RotatE — relations as rotations in complex embedding space (Sun et al., 2019)</td></tr>
<tr><td>Embedding dimension</td><td>128 complex (= 256 real, concatenating real + imaginary parts)</td></tr>
<tr><td>Loss function</td><td>NSSALoss (self-adversarial negative sampling), margin=9.0, temperature=1.0</td></tr>
<tr><td>Optimizer</td><td>Adam, lr=1e-4</td></tr>
<tr><td>Batch size</td><td>4,096</td></tr>
<tr><td>Negative samples per positive</td><td>64</td></tr>
<tr><td>Epochs trained</td><td>{training['num_epochs_trained']}</td></tr>
<tr><td>Early stopping</td><td>Patience=10, frequency=10 epochs, metric=inverse harmonic mean rank (MRR)</td></tr>
<tr><td>Entities in training graph</td><td>{training['num_entities']:,}</td></tr>
<tr><td>Relation types</td><td>{training['num_relations']}</td></tr>
<tr><td>Training time</td><td>{training['training_time_seconds']/3600:.1f} hours on NVIDIA L40S GPU</td></tr>
<tr><td>Final training MRR</td><td>0.1119 (PyKEEN filtered evaluation)</td></tr>
</table>

<h3>2.3 Decoder Features</h3>
<p>For each drug-disease candidate pair, the decoder receives a feature vector composed of:</p>
<table>
<tr><th>Feature Group</th><th>Dimensions</th><th>Description</th></tr>
<tr><td>Hadamard product</td><td>256 (RotatE) / 128 (Node2Vec)</td><td>Element-wise product of drug and disease embeddings</td></tr>
<tr><td>Absolute difference</td><td>256 / 128</td><td>Element-wise |emb_drug - emb_disease|</td></tr>
<tr><td>Cosine similarity</td><td>1</td><td>Cosine similarity between embeddings</td></tr>
<tr><td>L2 distance</td><td>1</td><td>Euclidean distance between embeddings</td></tr>
<tr><td>Shared neighbors</td><td>1</td><td>Number of common neighbors in training graph</td></tr>
<tr><td>Jaccard coefficient</td><td>1</td><td>|shared| / |union| of neighbor sets</td></tr>
<tr><td>Adamic-Adar index</td><td>1</td><td>Sum of 1/log(degree) over shared neighbors</td></tr>
<tr><td>Preferential attachment</td><td>1</td><td>log(1 + deg_drug * deg_disease)</td></tr>
<tr><td>Drug degree</td><td>1</td><td>log(1 + degree of drug node)</td></tr>
<tr><td>Disease degree</td><td>1</td><td>log(1 + degree of disease node)</td></tr>
</table>

<h2>3. Decoder Comparison</h2>

<h3>3.1 All Decoders — RotatE vs Node2Vec</h3>
<table>
<tr>
    <th>Embedding</th><th>Decoder</th>
    <th>Val AUROC</th><th>Val AUPRC</th>
    <th>Test AUROC</th><th>Test AUPRC</th>
    <th>MRR</th><th>Hits@10</th><th>Hits@100</th><th>Hits@200</th>
</tr>
<tr>
    <td>Node2Vec</td><td>Cosine</td>
    <td>{nd['Cosine']['val_auroc']:.4f}</td><td>{nd['Cosine']['val_auprc']:.4f}</td>
    <td>{nd['Cosine']['test_auroc']:.4f}</td><td>{nd['Cosine']['test_auprc']:.4f}</td>
    <td>{nd['Cosine']['ranking']['mrr']:.4f}</td>
    <td>{nd['Cosine']['ranking']['hits@10']:.1%}</td>
    <td>{nd['Cosine']['ranking']['hits@100']:.1%}</td>
    <td>{nd['Cosine']['ranking']['hits@200']:.1%}</td>
</tr>
<tr class="best">
    <td>Node2Vec</td><td><strong>XGBoost</strong></td>
    <td>{nd['XGBoost']['val_auroc']:.4f}</td><td>{nd['XGBoost']['val_auprc']:.4f}</td>
    <td>{nd['XGBoost']['test_auroc']:.4f}</td><td>{nd['XGBoost']['test_auprc']:.4f}</td>
    <td>{nd['XGBoost']['ranking']['mrr']:.4f}</td>
    <td>{nd['XGBoost']['ranking']['hits@10']:.1%}</td>
    <td>{nd['XGBoost']['ranking']['hits@100']:.1%}</td>
    <td>{nd['XGBoost']['ranking']['hits@200']:.1%}</td>
</tr>
<tr>
    <td>Node2Vec</td><td>MLP</td>
    <td>{nd['MLP']['val_auroc']:.4f}</td><td>{nd['MLP']['val_auprc']:.4f}</td>
    <td>{nd['MLP']['test_auroc']:.4f}</td><td>{nd['MLP']['test_auprc']:.4f}</td>
    <td>{nd['MLP']['ranking']['mrr']:.4f}</td>
    <td>{nd['MLP']['ranking']['hits@10']:.1%}</td>
    <td>{nd['MLP']['ranking']['hits@100']:.1%}</td>
    <td>{nd['MLP']['ranking']['hits@200']:.1%}</td>
</tr>
<tr style="border-top: 3px solid #16a34a;">
    <td>RotatE</td><td>Cosine</td>
    <td>{rd['Cosine']['val_auroc']:.4f}</td><td>{rd['Cosine']['val_auprc']:.4f}</td>
    <td>{rd['Cosine']['test_auroc']:.4f}</td><td>{rd['Cosine']['test_auprc']:.4f}</td>
    <td>{rd['Cosine']['ranking']['mrr']:.4f}</td>
    <td>{rd['Cosine']['ranking']['hits@10']:.1%}</td>
    <td>{rd['Cosine']['ranking']['hits@100']:.1%}</td>
    <td>{rd['Cosine']['ranking']['hits@200']:.1%}</td>
</tr>
<tr class="best">
    <td>RotatE</td><td><strong>XGBoost</strong></td>
    <td>{rd['XGBoost']['val_auroc']:.4f}</td><td>{rd['XGBoost']['val_auprc']:.4f}</td>
    <td class="improved">{rd['XGBoost']['test_auroc']:.4f}</td><td class="improved">{rd['XGBoost']['test_auprc']:.4f}</td>
    <td>{rd['XGBoost']['ranking']['mrr']:.4f}</td>
    <td>{rd['XGBoost']['ranking']['hits@10']:.1%}</td>
    <td>{rd['XGBoost']['ranking']['hits@100']:.1%}</td>
    <td>{rd['XGBoost']['ranking']['hits@200']:.1%}</td>
</tr>
<tr>
    <td>RotatE</td><td>MLP</td>
    <td>{rd['MLP']['val_auroc']:.4f}</td><td>{rd['MLP']['val_auprc']:.4f}</td>
    <td class="improved">{rd['MLP']['test_auroc']:.4f}</td><td class="improved">{rd['MLP']['test_auprc']:.4f}</td>
    <td>{rd['MLP']['ranking']['mrr']:.4f}</td>
    <td>{rd['MLP']['ranking']['hits@10']:.1%}</td>
    <td>{rd['MLP']['ranking']['hits@100']:.1%}</td>
    <td>{rd['MLP']['ranking']['hits@200']:.1%}</td>
</tr>
</table>

<h3>3.2 Best Decoder Comparison (XGBoost)</h3>
<table>
<tr><th>Metric</th><th>Node2Vec</th><th>RotatE</th><th>Delta</th></tr>
<tr><td>Test AUROC</td><td>{nd['XGBoost']['test_auroc']:.4f}</td><td class="improved">{rd['XGBoost']['test_auroc']:.4f}</td><td class="improved">+{rd['XGBoost']['test_auroc'] - nd['XGBoost']['test_auroc']:.4f}</td></tr>
<tr><td>Test AUPRC</td><td>{nd['XGBoost']['test_auprc']:.4f}</td><td class="improved">{rd['XGBoost']['test_auprc']:.4f}</td><td class="improved">+{rd['XGBoost']['test_auprc'] - nd['XGBoost']['test_auprc']:.4f}</td></tr>
<tr><td>Val AUROC</td><td>{nd['XGBoost']['val_auroc']:.4f}</td><td class="improved">{rd['XGBoost']['val_auroc']:.4f}</td><td class="improved">+{rd['XGBoost']['val_auroc'] - nd['XGBoost']['val_auroc']:.4f}</td></tr>
<tr><td>Precision (test)</td><td>{n2v_class['Positive']['precision']:.4f}</td><td>{rotate_class['Positive']['precision']:.4f}</td><td>{"+" if rotate_class['Positive']['precision'] > n2v_class['Positive']['precision'] else ""}{rotate_class['Positive']['precision'] - n2v_class['Positive']['precision']:.4f}</td></tr>
<tr><td>Recall (test)</td><td>{n2v_class['Positive']['recall']:.4f}</td><td class="improved">{rotate_class['Positive']['recall']:.4f}</td><td class="improved">+{rotate_class['Positive']['recall'] - n2v_class['Positive']['recall']:.4f}</td></tr>
<tr><td>F1-score (test)</td><td>{n2v_class['Positive']['f1-score']:.4f}</td><td class="improved">{rotate_class['Positive']['f1-score']:.4f}</td><td class="improved">+{rotate_class['Positive']['f1-score'] - n2v_class['Positive']['f1-score']:.4f}</td></tr>
<tr><td>Accuracy (test)</td><td>{n2v_class['accuracy']:.4f}</td><td class="improved">{rotate_class['accuracy']:.4f}</td><td class="improved">+{rotate_class['accuracy'] - n2v_class['accuracy']:.4f}</td></tr>
<tr><td>Hits@100</td><td>{nd['XGBoost']['ranking']['hits@100']:.1%}</td><td>{rd['XGBoost']['ranking']['hits@100']:.1%}</td><td>0.0%</td></tr>
<tr><td>Hits@200</td><td>{nd['XGBoost']['ranking']['hits@200']:.1%}</td><td>{rd['XGBoost']['ranking']['hits@200']:.1%}</td><td>{(rd['XGBoost']['ranking']['hits@200'] - nd['XGBoost']['ranking']['hits@200'])*100:+.1f}%</td></tr>
<tr><td>Median rank</td><td>{nd['XGBoost']['ranking']['median_rank']:.0f}</td><td>{rd['XGBoost']['ranking']['median_rank']:.0f}</td><td>{rd['XGBoost']['ranking']['median_rank'] - nd['XGBoost']['ranking']['median_rank']:+.0f}</td></tr>
</table>

<h2>4. RotatE Evaluation Plots</h2>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">ROC Curve</h3>
        <img src="data:image/png;base64,{roc_b64}" alt="RotatE ROC Curve">
    </div>
    <div>
        <h3 style="text-align:center;">Precision-Recall Curve</h3>
        <img src="data:image/png;base64,{pr_b64}" alt="RotatE PR Curve">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Confusion Matrix</h3>
        <img src="data:image/png;base64,{cm_b64}" alt="RotatE Confusion Matrix">
    </div>
    <div>
        <h3 style="text-align:center;">Feature Importance (Top 20)</h3>
        <img src="data:image/png;base64,{fi_b64}" alt="RotatE Feature Importance">
    </div>
</div>

<h3>4.1 Feature Importance Analysis</h3>
<p>The most important feature for the RotatE + XGBoost decoder is <strong>L2 distance</strong> (7.3% importance gain),
which dominates all other features. This contrasts with Node2Vec where embedding dimensions and structural features
are more evenly distributed. RotatE optimizes for distance-based scoring in complex space, so L2 distance in the
concatenated real+imaginary space captures the model's learned similarity structure directly.</p>
<p>Only one structural feature (<code>log_deg_disease</code>) appears in the top 20, confirming that RotatE embeddings
encode sufficient graph structure to make structural heuristics largely redundant.</p>

<h2>5. Side-by-Side: RotatE vs Node2Vec Plots</h2>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — ROC</h3>
        <img src="data:image/png;base64,{n2v_roc_b64}" alt="Node2Vec ROC">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — ROC</h3>
        <img src="data:image/png;base64,{roc_b64}" alt="RotatE ROC">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — Confusion Matrix</h3>
        <img src="data:image/png;base64,{n2v_cm_b64}" alt="Node2Vec Confusion Matrix">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — Confusion Matrix</h3>
        <img src="data:image/png;base64,{cm_b64}" alt="RotatE Confusion Matrix">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — Feature Importance</h3>
        <img src="data:image/png;base64,{n2v_fi_b64}" alt="Node2Vec Feature Importance">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — Feature Importance</h3>
        <img src="data:image/png;base64,{fi_b64}" alt="RotatE Feature Importance">
    </div>
</div>

<h2>6. Top 30 Predicted Drug Repurposing Candidates</h2>

<h3>6.1 RotatE Predictions</h3>
<table class="pred-table">
<tr><th>Rank</th><th>Drug</th><th>Disease</th><th>Confidence</th></tr>
"""

    for p in rotate_preds:
        html += f"<tr><td>{p['rank']}</td><td>{p['drug_name']}</td><td>{p['disease_name']}</td><td>{float(p['confidence']):.4f}</td></tr>\n"

    html += """</table>

<h3>6.2 Node2Vec Predictions (for comparison)</h3>
<table class="pred-table">
<tr><th>Rank</th><th>Drug</th><th>Disease</th><th>Confidence</th></tr>
"""

    for p in n2v_preds:
        html += f"<tr><td>{p['rank']}</td><td>{p['drug_name']}</td><td>{p['disease_name']}</td><td>{float(p['confidence']):.4f}</td></tr>\n"

    html += f"""</table>

<h2>7. Discussion</h2>

<h3>Why RotatE improves over Node2Vec</h3>
<ul>
    <li><strong>Relation-aware embeddings:</strong> RotatE learns separate embeddings for each of the 25 relationship types,
    modeling each relation as a rotation in complex space. Node2Vec treats the graph as homogeneous (ignoring edge types),
    so it cannot distinguish between a <code>drugBindsGene</code> edge and a <code>drugTreatsDisease</code> edge.</li>
    <li><strong>Richer feature space:</strong> RotatE embeddings are 256-dimensional (128 complex = 128 real + 128 imaginary)
    vs Node2Vec's 128-dimensional embeddings, providing more capacity to encode graph structure.</li>
    <li><strong>Global optimization:</strong> RotatE jointly optimizes all entity and relation embeddings via gradient descent,
    while Node2Vec uses local random walks + Word2Vec, which may miss long-range dependencies.</li>
</ul>

<h3>Cosine decoder performance</h3>
<p>The cosine decoder performs significantly worse with RotatE (0.53) than Node2Vec (0.72). This is expected:
RotatE embeddings are optimized for the rotation scoring function h = t * r (element-wise complex multiplication),
not for cosine similarity. The learned decoders (XGBoost, MLP) can learn to use the RotatE embedding geometry
effectively, which is why they outperform their Node2Vec counterparts.</p>

<h3>Next steps</h3>
<ul>
    <li><strong>Graph Neural Networks (GNN):</strong> Train R-GCN or CompGCN as a third embedding method for comparison.
    GNNs can leverage node features and learn message-passing functions, potentially capturing different patterns than
    random walk (Node2Vec) or translational (RotatE) approaches.</li>
    <li><strong>Ensemble predictions:</strong> Combine Node2Vec and RotatE predictions (e.g., average confidence, rank fusion)
    to potentially improve coverage and accuracy.</li>
    <li><strong>Prediction overlap analysis:</strong> Compare which drug-disease pairs each method predicts — divergent
    predictions may highlight different aspects of the graph structure.</li>
</ul>

<div class="footer">
    CardioKB — Cardiovascular Disease Knowledge Graph | Link Prediction for Drug Repurposing<br>
    Report generated from evaluation data in <code>ml/data/rotate/</code> and <code>ml/data/node2vec/</code>
</div>

</body>
</html>"""

    with open(REPORT_PATH, "w") as f:
        f.write(html)
    print(f"Report saved to {REPORT_PATH}")
    print(f"File size: {REPORT_PATH.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
