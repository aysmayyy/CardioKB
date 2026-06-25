"""Generate self-contained HTML evaluation reports for all embedding methods."""

import json
import base64
import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
ROTATE_DIR = DATA_DIR / "rotate"
NODE2VEC_DIR = DATA_DIR / "node2vec"


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


def css():
    return """
    body { font-family: 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px 40px; color: #1a1a1a; line-height: 1.6; }
    h1 { border-bottom: 3px solid var(--accent); padding-bottom: 10px; }
    h2 { color: #1e3a5f; margin-top: 40px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }
    h3 { color: #334155; margin-top: 25px; }
    table { border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }
    th, td { border: 1px solid #cbd5e1; padding: 8px 12px; text-align: center; }
    th { background-color: #f1f5f9; font-weight: 600; }
    tr:nth-child(even) { background-color: #f8fafc; }
    .best { background-color: var(--best-bg); font-weight: 600; }
    .improved { color: var(--accent); font-weight: 600; }
    .metric-box { display: inline-block; background: var(--box-bg); border: 2px solid var(--accent); border-radius: 10px; padding: 15px 25px; margin: 8px; text-align: center; }
    .metric-box .value { font-size: 28px; font-weight: 700; color: var(--accent); }
    .metric-box .label { font-size: 13px; color: #475569; margin-top: 4px; }
    .plot-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
    .plot-grid img { width: 100%; border: 1px solid #e2e8f0; border-radius: 6px; }
    .summary { background: #f8fafc; border-left: 4px solid var(--accent); padding: 15px 20px; margin: 20px 0; }
    .pred-table { font-size: 13px; }
    .pred-table td { text-align: left; }
    .pred-table td:first-child, .pred-table td:last-child { text-align: center; }
    .section-info { color: #64748b; font-size: 14px; margin-bottom: 15px; }
    .footer { margin-top: 50px; padding-top: 15px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 12px; text-align: center; }
    @media print { body { max-width: 100%; padding: 10px; } .plot-grid { break-inside: avoid; } }
"""


def feature_table(feat_data):
    rows = ""
    for i, (name, imp) in enumerate(feat_data[:20], 1):
        rows += f"<tr><td>{i}</td><td><code>{name}</code></td><td>{imp:.4f}</td><td>{imp*100:.2f}%</td></tr>\n"
    return rows


def prediction_table(preds):
    rows = ""
    for p in preds:
        rows += f"<tr><td>{p['rank']}</td><td>{p['drug_name']}</td><td>{p['disease_name']}</td><td>{float(p['confidence']):.4f}</td></tr>\n"
    return rows


def generate_node2vec_report():
    ev = load_json(NODE2VEC_DIR / "evaluation_report.json")
    cl = load_json(NODE2VEC_DIR / "results" / "classification_report.json")
    feat = load_json(NODE2VEC_DIR / "results" / "feature_importance.json")
    preds = load_predictions(NODE2VEC_DIR / "predictions.tsv")
    d = ev["decoders"]

    roc = img_to_base64(NODE2VEC_DIR / "results" / "roc_curve.png")
    pr = img_to_base64(NODE2VEC_DIR / "results" / "pr_curve.png")
    cm = img_to_base64(NODE2VEC_DIR / "results" / "confusion_matrix.png")
    fi = img_to_base64(NODE2VEC_DIR / "results" / "feature_importance.png")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CardioKB — Node2Vec Link Prediction Evaluation Report</title>
<style>
    :root {{ --accent: #2563eb; --best-bg: #dbeafe; --box-bg: #eff6ff; }}
    {css()}
</style>
</head>
<body>

<h1 style="color: #0f172a;">CardioKB — Node2Vec Link Prediction Evaluation Report</h1>
<p class="section-info">Generated: 2026-06-24 | CardioKB Knowledge Graph: 459,092 nodes, 5.4M+ relationships, 22 data sources</p>

<div class="summary">
<strong>Key Result:</strong> Node2Vec + XGBoost achieves <strong>Test AUROC = {d['XGBoost']['test_auroc']:.4f}</strong> and
<strong>AUPRC = {d['XGBoost']['test_auprc']:.4f}</strong> for drug-disease link prediction on the CardioKB knowledge graph.
XGBoost outperforms both Cosine and MLP decoders.
</div>

<h2>1. Headline Metrics (XGBoost Decoder)</h2>
<div style="text-align:center;">
    <div class="metric-box"><div class="value">{d['XGBoost']['test_auroc']:.4f}</div><div class="label">Test AUROC</div></div>
    <div class="metric-box"><div class="value">{d['XGBoost']['test_auprc']:.4f}</div><div class="label">Test AUPRC</div></div>
    <div class="metric-box"><div class="value">{cl['accuracy']*100:.1f}%</div><div class="label">Accuracy</div></div>
    <div class="metric-box"><div class="value">{cl['Positive']['recall']*100:.1f}%</div><div class="label">Recall</div></div>
    <div class="metric-box"><div class="value">{cl['Positive']['precision']*100:.1f}%</div><div class="label">Precision</div></div>
</div>

<h2>2. Methodology</h2>

<h3>2.1 Knowledge Graph & Data</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Knowledge Graph</td><td>CardioKB — 459,092 nodes, 5,437,921 relationships, 17 node types, 25 relationship types</td></tr>
<tr><td>Target edge type</td><td><code>drugTreatsDisease</code> (3,782 total edges)</td></tr>
<tr><td>Therapeutic drugs (filtered)</td><td>{ev['n_therapeutic_drugs']:,}</td></tr>
<tr><td>Diseases</td><td>{ev['n_diseases']}</td></tr>
</table>

<h4>drugTreatsDisease Edge Breakdown by Source</h4>
<table>
<tr><th>Source</th><th>Count</th><th>Description</th></tr>
<tr><td>CTD</td><td>2,757</td><td>Curated chemical-disease therapeutic associations</td></tr>
<tr><td>ClinicalTrials.gov</td><td>868</td><td>Phase 3/4 clinical trial drug-disease pairs</td></tr>
<tr><td>DrugCentral</td><td>157</td><td>FDA-approved drug indications</td></tr>
<tr style="font-weight:600; background-color: #f1f5f9;"><td>Total</td><td>3,782</td><td></td></tr>
</table>

<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Edge split</td><td>80/10/10 stratified by edge type</td></tr>
<tr><td>Train / Val / Test positives</td><td>{ev['n_train_positives']:,} / {ev['n_val_positives']} / {ev['n_test_positives']}</td></tr>
<tr><td>Negative sampling</td><td>1:1 ratio, excluding all known Drug-Disease edges across all splits</td></tr>
<tr><td>Data leakage prevention</td><td>Embeddings trained on train split only; val/test edges hidden</td></tr>
</table>

<h3>2.2 Node2Vec Training Configuration</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Library</td><td>PecanPy</td></tr>
<tr><td>Model</td><td>Node2Vec (Grover & Leskovec, 2016) — biased random walks + Skip-gram</td></tr>
<tr><td>Embedding dimension</td><td>128</td></tr>
<tr><td>Walk length</td><td>80</td></tr>
<tr><td>Walks per node</td><td>10</td></tr>
<tr><td>Window size</td><td>10</td></tr>
<tr><td>p / q parameters</td><td>1.0 / 1.0 (DeepWalk-equivalent)</td></tr>
<tr><td>Edge type awareness</td><td>None (homogeneous random walks)</td></tr>
<tr><td>Hardware</td><td>ESPL HPC cluster (SLURM), CPU-based</td></tr>
</table>

<h3>2.3 Decoder Features</h3>
<p>For each drug-disease candidate pair, the decoder receives:</p>
<table>
<tr><th>Feature Group</th><th>Dimensions</th><th>Description</th></tr>
<tr><td>Hadamard product</td><td>128</td><td>Element-wise product of drug and disease embeddings</td></tr>
<tr><td>Absolute difference</td><td>128</td><td>Element-wise |emb_drug - emb_disease|</td></tr>
<tr><td>Cosine similarity</td><td>1</td><td>Cosine similarity between embeddings</td></tr>
<tr><td>L2 distance</td><td>1</td><td>Euclidean distance between embeddings</td></tr>
<tr><td>Shared neighbors</td><td>1</td><td>Common neighbors in training graph</td></tr>
<tr><td>Jaccard coefficient</td><td>1</td><td>|shared| / |union| of neighbor sets</td></tr>
<tr><td>Adamic-Adar index</td><td>1</td><td>Sum of 1/log(degree) over shared neighbors</td></tr>
<tr><td>Preferential attachment</td><td>1</td><td>log(1 + deg_drug * deg_disease)</td></tr>
<tr><td>Drug degree</td><td>1</td><td>log(1 + degree of drug node)</td></tr>
<tr><td>Disease degree</td><td>1</td><td>log(1 + degree of disease node)</td></tr>
</table>

<h2>3. Decoder Comparison</h2>
<table>
<tr>
    <th>Decoder</th>
    <th>Val AUROC</th><th>Val AUPRC</th>
    <th>Test AUROC</th><th>Test AUPRC</th>
    <th>MRR</th><th>Hits@10</th><th>Hits@100</th><th>Hits@200</th>
</tr>
<tr>
    <td>Cosine</td>
    <td>{d['Cosine']['val_auroc']:.4f}</td><td>{d['Cosine']['val_auprc']:.4f}</td>
    <td>{d['Cosine']['test_auroc']:.4f}</td><td>{d['Cosine']['test_auprc']:.4f}</td>
    <td>{d['Cosine']['ranking']['mrr']:.4f}</td>
    <td>{d['Cosine']['ranking']['hits@10']:.1%}</td>
    <td>{d['Cosine']['ranking']['hits@100']:.1%}</td>
    <td>{d['Cosine']['ranking']['hits@200']:.1%}</td>
</tr>
<tr class="best">
    <td><strong>XGBoost</strong></td>
    <td>{d['XGBoost']['val_auroc']:.4f}</td><td>{d['XGBoost']['val_auprc']:.4f}</td>
    <td>{d['XGBoost']['test_auroc']:.4f}</td><td>{d['XGBoost']['test_auprc']:.4f}</td>
    <td>{d['XGBoost']['ranking']['mrr']:.4f}</td>
    <td>{d['XGBoost']['ranking']['hits@10']:.1%}</td>
    <td>{d['XGBoost']['ranking']['hits@100']:.1%}</td>
    <td>{d['XGBoost']['ranking']['hits@200']:.1%}</td>
</tr>
<tr>
    <td>MLP</td>
    <td>{d['MLP']['val_auroc']:.4f}</td><td>{d['MLP']['val_auprc']:.4f}</td>
    <td>{d['MLP']['test_auroc']:.4f}</td><td>{d['MLP']['test_auprc']:.4f}</td>
    <td>{d['MLP']['ranking']['mrr']:.4f}</td>
    <td>{d['MLP']['ranking']['hits@10']:.1%}</td>
    <td>{d['MLP']['ranking']['hits@100']:.1%}</td>
    <td>{d['MLP']['ranking']['hits@200']:.1%}</td>
</tr>
</table>

<h3>3.1 Classification Report (XGBoost, test set)</h3>
<table>
<tr><th>Metric</th><th>Negative</th><th>Positive</th></tr>
<tr><td>Precision</td><td>{cl['Negative']['precision']:.4f}</td><td>{cl['Positive']['precision']:.4f}</td></tr>
<tr><td>Recall</td><td>{cl['Negative']['recall']:.4f}</td><td>{cl['Positive']['recall']:.4f}</td></tr>
<tr><td>F1-score</td><td>{cl['Negative']['f1-score']:.4f}</td><td>{cl['Positive']['f1-score']:.4f}</td></tr>
<tr><td>Support</td><td>{int(cl['Negative']['support'])}</td><td>{int(cl['Positive']['support'])}</td></tr>
</table>
<p><strong>Accuracy:</strong> {cl['accuracy']:.4f} | <strong>Test set size:</strong> {int(cl['Negative']['support'] + cl['Positive']['support'])} samples</p>

<h2>4. Evaluation Plots</h2>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">ROC Curve</h3>
        <img src="data:image/png;base64,{roc}" alt="ROC Curve">
    </div>
    <div>
        <h3 style="text-align:center;">Precision-Recall Curve</h3>
        <img src="data:image/png;base64,{pr}" alt="PR Curve">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Confusion Matrix</h3>
        <img src="data:image/png;base64,{cm}" alt="Confusion Matrix">
    </div>
    <div>
        <h3 style="text-align:center;">Feature Importance (Top 20)</h3>
        <img src="data:image/png;base64,{fi}" alt="Feature Importance">
    </div>
</div>

<h2>5. Feature Importance Analysis</h2>

<table>
<tr><th>Rank</th><th>Feature</th><th>Importance (gain)</th><th>Percentage</th></tr>
{feature_table(feat)}
</table>

<p><strong>Key observations:</strong></p>
<ul>
    <li><strong>L2 distance</strong> is the most important feature at 20.1% — far ahead of all others. This indicates embedding distance is a strong signal for drug-disease link prediction.</li>
    <li><strong>Structural features</strong> (preferential attachment, cosine, drug degree, Adamic-Adar, shared neighbors, disease degree) collectively play a significant role, occupying 6 of the top 10 positions. Node2Vec's homogeneous walks leave gaps that structural heuristics fill.</li>
    <li><strong>hadamard_120</strong> is the single most important embedding dimension at 6.9%, suggesting this dimension captures drug-disease affinity.</li>
</ul>

<h2>6. Top 30 Predicted Drug Repurposing Candidates</h2>

<table class="pred-table">
<tr><th>Rank</th><th>Drug</th><th>Disease</th><th>Confidence</th></tr>
{prediction_table(preds)}
</table>

<p><strong>Observations:</strong> Many top predictions are cardiovascularly relevant (Aspirin for arteriosclerotic CVD,
Diltiazem/Propranolol for MI, statins, ACE inhibitors). Confidence scores cluster around 0.9705, suggesting the model
has limited discriminative power in its ranking — many candidates receive near-identical scores.</p>

<h2>7. Predictions in the Knowledge Graph</h2>
<p>Top 500 predictions (confidence &ge; 0.5) are stored in Memgraph as <code>predictedTreatsDisease</code> edges
with <code>source: "Node2Vec_LinkPrediction"</code>. These appear in the CardioKB web UI as orange dashed lines
with a toggle to show/hide. Edge provenance shows confidence score, method, and a "not clinically validated" warning.</p>

<h2>8. Limitations</h2>
<ul>
    <li><strong>Edge-type agnostic:</strong> Node2Vec treats the graph as homogeneous — it cannot distinguish between different relationship types (e.g., <code>drugBindsGene</code> vs <code>drugTreatsDisease</code>).</li>
    <li><strong>MRR remains low</strong> (~0.02) due to the extreme candidate space (9,735 drugs &times; 457 diseases = 4.4M pairs).</li>
    <li><strong>No external validation</strong> — predictions have not been validated against independent clinical data or literature.</li>
    <li><strong>Single split</strong> — results are from one 80/10/10 split. Cross-validation would provide confidence intervals.</li>
</ul>

<div class="footer">
    CardioKB — Cardiovascular Disease Knowledge Graph | Node2Vec Link Prediction for Drug Repurposing<br>
    Report generated from evaluation data in <code>ml/data/node2vec/</code>
</div>

</body>
</html>"""

    out = REPORTS_DIR / "node2vec_evaluation_report.html"
    with open(out, "w") as f:
        f.write(html)
    print(f"Node2Vec report saved to {out} ({out.stat().st_size / 1e6:.1f} MB)")


def generate_rotate_report():
    rotate_eval = load_json(ROTATE_DIR / "evaluation_report.json")
    rotate_class = load_json(ROTATE_DIR / "results" / "classification_report.json")
    rotate_feat = load_json(ROTATE_DIR / "results" / "feature_importance.json")
    n2v_eval = load_json(NODE2VEC_DIR / "evaluation_report.json")
    n2v_class = load_json(NODE2VEC_DIR / "results" / "classification_report.json")
    training = load_json(ROTATE_DIR / "training_summary.json")

    rotate_preds = load_predictions(ROTATE_DIR / "predictions.tsv")
    n2v_preds = load_predictions(NODE2VEC_DIR / "predictions.tsv")

    roc = img_to_base64(ROTATE_DIR / "results" / "roc_curve.png")
    pr = img_to_base64(ROTATE_DIR / "results" / "pr_curve.png")
    cm = img_to_base64(ROTATE_DIR / "results" / "confusion_matrix.png")
    fi = img_to_base64(ROTATE_DIR / "results" / "feature_importance.png")

    n2v_roc = img_to_base64(NODE2VEC_DIR / "results" / "roc_curve.png")
    n2v_cm = img_to_base64(NODE2VEC_DIR / "results" / "confusion_matrix.png")
    n2v_fi = img_to_base64(NODE2VEC_DIR / "results" / "feature_importance.png")

    rd = rotate_eval["decoders"]
    nd = n2v_eval["decoders"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CardioKB — RotatE Link Prediction Evaluation Report</title>
<style>
    :root {{ --accent: #16a34a; --best-bg: #dcfce7; --box-bg: #f0fdf4; }}
    {css()}
    .n2v-box {{ background: #eff6ff; border-color: #2563eb; }}
    .n2v-box .value {{ color: #2563eb; }}
    .comparison-header {{ display: flex; justify-content: center; gap: 40px; margin: 20px 0; }}
</style>
</head>
<body>

<h1 style="color: #0f172a;">CardioKB — RotatE Link Prediction Evaluation Report</h1>
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
</table>

<h4>drugTreatsDisease Edge Breakdown by Source</h4>
<table>
<tr><th>Source</th><th>Count</th><th>Description</th></tr>
<tr><td>CTD</td><td>2,757</td><td>Curated chemical-disease therapeutic associations</td></tr>
<tr><td>ClinicalTrials.gov</td><td>868</td><td>Phase 3/4 clinical trial drug-disease pairs</td></tr>
<tr><td>DrugCentral</td><td>157</td><td>FDA-approved drug indications</td></tr>
<tr style="font-weight:600; background-color: #f1f5f9;"><td>Total</td><td>3,782</td><td></td></tr>
</table>

<table>
<tr><th>Parameter</th><th>Value</th></tr>
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
<tr><td>Precision (test)</td><td>{n2v_class['Positive']['precision']:.4f}</td><td>{rotate_class['Positive']['precision']:.4f}</td><td>{rotate_class['Positive']['precision'] - n2v_class['Positive']['precision']:+.4f}</td></tr>
<tr><td>Recall (test)</td><td>{n2v_class['Positive']['recall']:.4f}</td><td class="improved">{rotate_class['Positive']['recall']:.4f}</td><td class="improved">+{rotate_class['Positive']['recall'] - n2v_class['Positive']['recall']:.4f}</td></tr>
<tr><td>F1-score (test)</td><td>{n2v_class['Positive']['f1-score']:.4f}</td><td class="improved">{rotate_class['Positive']['f1-score']:.4f}</td><td class="improved">+{rotate_class['Positive']['f1-score'] - n2v_class['Positive']['f1-score']:.4f}</td></tr>
<tr><td>Accuracy (test)</td><td>{n2v_class['accuracy']:.4f}</td><td class="improved">{rotate_class['accuracy']:.4f}</td><td class="improved">+{rotate_class['accuracy'] - n2v_class['accuracy']:.4f}</td></tr>
</table>

<p><strong>Key takeaway:</strong> RotatE significantly improves recall (+8.7 percentage points) and F1-score (+4.9pp) while maintaining precision.
The AUROC/AUPRC improvements are consistent across validation and test sets, indicating no overfitting.</p>

<h2>4. RotatE Evaluation Plots</h2>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">ROC Curve</h3>
        <img src="data:image/png;base64,{roc}" alt="RotatE ROC Curve">
    </div>
    <div>
        <h3 style="text-align:center;">Precision-Recall Curve</h3>
        <img src="data:image/png;base64,{pr}" alt="RotatE PR Curve">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Confusion Matrix</h3>
        <img src="data:image/png;base64,{cm}" alt="RotatE Confusion Matrix">
    </div>
    <div>
        <h3 style="text-align:center;">Feature Importance (Top 20)</h3>
        <img src="data:image/png;base64,{fi}" alt="RotatE Feature Importance">
    </div>
</div>

<h2>5. Side-by-Side: RotatE vs Node2Vec Plots</h2>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — ROC</h3>
        <img src="data:image/png;base64,{n2v_roc}" alt="Node2Vec ROC">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — ROC</h3>
        <img src="data:image/png;base64,{roc}" alt="RotatE ROC">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — Confusion Matrix</h3>
        <img src="data:image/png;base64,{n2v_cm}" alt="Node2Vec Confusion Matrix">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — Confusion Matrix</h3>
        <img src="data:image/png;base64,{cm}" alt="RotatE Confusion Matrix">
    </div>
</div>

<div class="plot-grid">
    <div>
        <h3 style="text-align:center;">Node2Vec — Feature Importance</h3>
        <img src="data:image/png;base64,{n2v_fi}" alt="Node2Vec Feature Importance">
    </div>
    <div>
        <h3 style="text-align:center;">RotatE — Feature Importance</h3>
        <img src="data:image/png;base64,{fi}" alt="RotatE Feature Importance">
    </div>
</div>

<h2>6. Feature Importance Analysis</h2>

<table>
<tr><th>Rank</th><th>Feature</th><th>Importance (gain)</th><th>Percentage</th></tr>
{feature_table(rotate_feat)}
</table>

<p><strong>Key observations:</strong></p>
<ul>
    <li><strong>L2 distance dominates</strong> at 7.3% — over 6x more important than the next feature. RotatE optimizes for distance-based scoring in complex space, so L2 distance directly captures the learned similarity structure.</li>
    <li>Only <strong>1 structural feature</strong> (<code>log_deg_disease</code>) in the top 20 — RotatE embeddings encode enough graph structure to make structural heuristics largely redundant.</li>
    <li>This contrasts with Node2Vec, where structural features occupy 6 of the top 10 positions (L2 at 20.1%, then preferential attachment, cosine, drug degree, Adamic-Adar, shared neighbors).</li>
</ul>

<h2>7. Top 30 Predicted Drug Repurposing Candidates</h2>

<h3>7.1 RotatE Predictions</h3>
<table class="pred-table">
<tr><th>Rank</th><th>Drug</th><th>Disease</th><th>Confidence</th></tr>
{prediction_table(rotate_preds)}
</table>

<h3>7.2 Node2Vec Predictions (for comparison)</h3>
<table class="pred-table">
<tr><th>Rank</th><th>Drug</th><th>Disease</th><th>Confidence</th></tr>
{prediction_table(n2v_preds)}
</table>

<p><strong>Comparison:</strong> RotatE predictions show higher confidence (0.996 vs 0.971) and more differentiation between candidates.
Node2Vec has many predictions clustered at the same confidence (0.9705), indicating less discriminative ranking power.
Both methods surface cardiovascularly relevant drug-disease pairs.</p>

<h2>8. Discussion</h2>

<h3>Why RotatE improves over Node2Vec</h3>
<ul>
    <li><strong>Relation-aware embeddings:</strong> RotatE learns separate embeddings for each of the 25 relationship types, modeling each relation as a rotation in complex space. Node2Vec treats the graph as homogeneous.</li>
    <li><strong>Richer feature space:</strong> RotatE embeddings are 256-dimensional (128 complex) vs Node2Vec's 128 dimensions.</li>
    <li><strong>Global optimization:</strong> RotatE jointly optimizes all entity and relation embeddings via gradient descent, while Node2Vec uses local random walks + Word2Vec.</li>
    <li><strong>Improved recall:</strong> +8.7pp recall means RotatE finds 28 more true treatment relationships out of 322 test positives while adding only 2 false positives.</li>
</ul>

<h3>Why Cosine decoder fails with RotatE</h3>
<p>Cosine drops from 0.72 (Node2Vec) to 0.53 (RotatE, near-random). RotatE embeddings are optimized for rotation scoring
(<code>h = t * r</code>), not cosine similarity. Learned decoders (XGBoost, MLP) adapt to the geometry effectively.</p>

<h3>Limitations</h3>
<ul>
    <li><strong>MRR remains low</strong> (~0.02) due to extreme candidate space (9,735 drugs &times; 457 diseases = 4.4M pairs).</li>
    <li><strong>No external validation</strong> against independent clinical data or literature.</li>
    <li><strong>Single split</strong> — cross-validation would provide confidence intervals.</li>
</ul>

<h3>Next steps</h3>
<ul>
    <li><strong>Graph Neural Networks (GNN):</strong> Train R-GCN or CompGCN as a third embedding method.</li>
    <li><strong>Ensemble predictions:</strong> Combine methods via average confidence or rank fusion.</li>
    <li><strong>Prediction overlap analysis:</strong> Quantify shared vs unique predictions between methods.</li>
</ul>

<div class="footer">
    CardioKB — Cardiovascular Disease Knowledge Graph | Link Prediction for Drug Repurposing<br>
    Report generated from evaluation data in <code>ml/data/rotate/</code> and <code>ml/data/node2vec/</code>
</div>

</body>
</html>"""

    out = REPORTS_DIR / "rotate_evaluation_report.html"
    with open(out, "w") as f:
        f.write(html)
    print(f"RotatE report saved to {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    REPORTS_DIR.mkdir(exist_ok=True)
    generate_node2vec_report()
    generate_rotate_report()
    print("\nDone! Both reports in ml/reports/")
